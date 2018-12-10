#!/usr/bin/env python3
# Python 3.6

# Import the Halite SDK, which will let you interact with the game.
import hlt
import time

# This library contains constant values.
from hlt import constants
import numpy as np

# This library contains direction metadata to better interface with the game.
from hlt.positionals import Direction, Position

# This library allows you to generate random numbers.
import random

# Logging allows you to save messages for yourself. This is required because the regular STDOUT
#   (print statements) are reserved for the engine-bot communication.
import logging

""" <<<Game Begin>>> """
# This game object contains the initial game state.
game = hlt.Game()
# At this point "game" variable is populated with initial map data.
# This is a good place to do computationally expensive start-up pre-processing.
opponent_shipyards = []
sniped_shipyards = []
opponents = []
for playerid in game.players:
    if game.players[playerid] == game.me:
        continue
    opp = game.players[playerid]
    opponents.append(opp)
    opponent_shipyards.append(opp.shipyard)

logging.info("Playing against {} opponents".format(len(opponents)))
disable_sniping = False if len(opponents) == 1 else True

logging.info("Starting amount of halite: {}".format(
    game.game_map.total_halite))

# Now that your bot is initialized, save a message to yourself in the log file with some important information.
#   Here, you log here your id, which you can always fetch from the game object by using my_id.
# logging.info("Successfully created bot! My Player ID is {}.".format(game.my_id))

""" <<<Game Loop>>> """

# Holds targets for ships
# Keep these outside the loop...
ship_targets = []
ship_info = {}
my_ships = []

global sniper_check
global being_sniped
sniper_check = None
being_sniped = False

command_queue = []
drop_off_points = [game.me.shipyard.position]
ships_moved_this_turn = []
most_valueable_cells = []
most_valueable_cells_cache = {}

intended_moves = {}

me = None
game_map = game.game_map
# As soon as you call "ready" function below, the 2 second per turn timer
# will start.
game.ready("ChaosBot")

cache_drop_offs = {}


def determin_sniper():
    if disable_sniping:
        return
    # if len(sniped_shipyards) == len(opponent_shipyards):
    #     # Snipped all shipyards, nothing to do
    #     return
    snipers = [k for (k, v) in ship_info.items() if v[
        'sniper'] == True]
    if len(my_ships) - len(snipers) <= 4:
        # Have 4 collecting at all times!
        return
    # if len(snipers) >= len(opponents):
    #     return

    max_opp_ships = 0
    target_opp = None
    target = None
    for player in opponents:
        if player.shipyard.position in sniped_shipyards:
            continue
        if len(player.get_ships()) > max_opp_ships:
            max_opp_ships = len(player.get_ships())
            target_opp = player

    if target_opp:
        logging.info("Opponent {} has more ships than us({})!".format(
            target_opp, max_opp_ships))
        target = target_opp.shipyard.position
    elif len(my_ships) <= 10:
        return

    most_empty = sorted([me.get_ship(k) for (
        k, v) in ship_info.items()], key=lambda k: k.halite_amount)[0]
    closest = 99

    if target is None:
        for shipyard in opponent_shipyards:
            if shipyard.position in sniped_shipyards:
                continue
            distance = game_map.calculate_distance(
                most_empty.position, shipyard.position)
            if distance < closest:
                target = shipyard.position
                closest = distance
    if target:
        ship_info[most_empty.id]['sniper'] = True
        ship_info[most_empty.id]['total_miner'] = False
        logging.info("Elected {} to snipe {}".format(most_empty, target))
        ship_info[most_empty.id]['target_position'] = target
        sniped_shipyards.append(target)


def move_sniper(ship):
    moving_costs = game_map[ship.position].cost

    if ship.halite_amount < moving_costs:
        logging.warning("Can't move sniper! It would cost {} and we have {}".format(
            moving_costs, ship.halite_amount))
        # Can't move even if we wanted to!!
        ship_info[ship.id]["state"] = "sniper_collecting"
        command_queue.append(ship.stay_still())
        ships_moved_this_turn.append(ship)
        return
    else:
        if ship.position == ship_info[ship.id]['target_position']:
            logging.info("Sniper arrived, staying still")
            ship_info[ship.id]["state"] = "sniping"
            command_queue.append(ship.stay_still())
            ships_moved_this_turn.append(ship)
            return
        else:
            ship_info[ship.id]["state"] = "sniper_enroute"
            target = ship_info[ship.id]['target_position']
            distance = game_map.calculate_distance(ship.position, target)
            logging.info("Sniper {} enroute to {} ({})".format(
                ship.position, target, distance))
            if distance == 1 and game_map[target].is_occupied:
                move = ship.stay_still()
            else:
                move = ship.move(game_map.naive_navigate(ship, target))
            command_queue.append(move)
            ships_moved_this_turn.append(ship)
            return


def mark_area_unsafe(ship):
    # center_pos = ship.position
    game_map[ship.position].ship = ship
    all_directions = [Direction.North, Direction.East,
                      Direction.South, Direction.West]
    for direction in all_directions:
        position = ship.position.directional_offset(direction)
        game_map[position].ship = ship


def unmark_area_unsafe(position):
    all_directions = [Direction.North, Direction.East,
                      Direction.South, Direction.West]
    for direction in all_directions:
        pos = position.directional_offset(direction)
        game_map[pos].ship = None


# def closest_dropoff_point(ship):
#     closest_drop = 0
#     dist_to_drop_off = game_map.height
#     for drop in drop_off_points:
#         distance = game_map.calculate_distance(ship.position, drop)
#         if distance < dist_to_drop_off:
#             dist_to_drop_off = distance

#     return dist_to_drop_off


def closest_dropoff_point(ship):
    if ship.id in cache_drop_offs:
        return cache_drop_offs[ship.id]
    closest_drop_off = None
    dist_to_drop_off = game_map.height
    for drop in drop_off_points:
        distance = game_map.calculate_distance(ship.position, drop)
        if distance < dist_to_drop_off:
            dist_to_drop_off = distance
            closest_drop_off = drop
    # Cache dropoff distances
    cache_drop_offs[ship.id] = [dist_to_drop_off, closest_drop_off]
    return [dist_to_drop_off, closest_drop_off]


def check_for_drop(ship):
    if ship_info[ship.id]["state"] == "returning":
        # No need to check.
        return
    #  = closest_dropoff_point(ship)[0]
    closest_drop, closest_drop_off = closest_dropoff_point(ship)

    # Check for end game
    # and ship.percentage_filled > closest_drop:
    if ship_info[ship.id]["state"] != "returning" and ship.halite_amount > 0 and game.turn_number > constants.MAX_TURNS * 0.97 - closest_drop:
        ship_info[ship.id]["target_position"] = closest_drop_off
        ship_info[ship.id]["state"] = "returning"
        return

    if game.turn_number < game_map.height * 2:
        if closest_drop < 5:
            if game_map[ship.position].halite_amount < 10 and ship.halite_amount > 100:
                # logging.info("Ship needs to return! {}".format(ship))
                ship_info[ship.id]["target_position"] = closest_drop_off
                ship_info[ship.id]["state"] = "returning"
                return

    if ship_info[ship.id]["target_position"] and ship.position == ship_info[ship.id]["target_position"] and not ship.is_full:
        # No need to return yet, ship is filling up
        return

    if ship.is_full_enough:
        # logging.info("Ship needs to return! {}".format(ship))
        ship_info[ship.id]["target_position"] = closest_drop_off
        ship_info[ship.id]["state"] = "returning"
    elif game.turn_number > constants.MAX_TURNS * 0.2 and ship.percentage_filled >= closest_drop * 10:  # ship.percentage_filled > 20 and
        # logging.info("Closest drop: {} Percentage full: {}".format(closest_drop, ship.percentage_filled))
        ship_info[ship.id]["target_position"] = closest_drop_off
        ship_info[ship.id]["state"] = "returning"


def create_drop():
    if game.turn_number <= 100:
        return
    if me.halite_amount < constants.SHIP_COST:
        return
    if len(drop_off_points) > 2:
        return
    if game.turn_number > constants.MAX_TURNS * 0.9:
        return

    max_halite_found = 0
    max_ships_found = 0
    best_ship = None
    # we_can_pay = False
    for ship in my_ships:
        if ship.id not in ship_info:
            continue
        # Don't use ships that are total mining
        if ship_info[ship.id]["total_miner"] == True:
            continue

        dist_to_drop_off = game_map.height
        for drop in drop_off_points:
            distance = game_map.calculate_distance(ship.position, drop)
            if distance < dist_to_drop_off:
                dist_to_drop_off = distance

        if dist_to_drop_off <= game_map.height / 3:
            continue

        if game_map[ship.position].has_structure:
            continue

        center_pos = ship.position
        total_halite = 0
        own_ships = 0
        for x in range(-5, 5):
            for y in range(-5, 5):
                test_position = game_map[
                    Position(center_pos.x + x, center_pos.y + y)]
                if test_position.ship in my_ships:
                    own_ships += 1
                total_halite += test_position.halite_amount

        if total_halite > max_halite_found and own_ships > max_ships_found:
            max_ships_found = own_ships
            max_halite_found = total_halite
            best_ship = ship
            cost = 4000 - \
                game_map[best_ship.position].halite_amount - \
                best_ship.halite_amount
            # if cost < me.halite_amount:
            #     we_can_pay = True

    if best_ship and max_ships_found > 2 \
            and max_halite_found >= constants.MAX_HALITE * 5:
        cost = 4000 - \
            game_map[best_ship.position].halite_amount - \
            best_ship.halite_amount
        if cost < me.halite_amount:
            me.halite_amount -= cost
            drop_off_points.append(best_ship.position)
            command_queue.append(best_ship.make_dropoff())
            ships_moved_this_turn.append(best_ship)
            del ship_info[best_ship.id]


def closest_valueable_cell(center_pos):
    halite_amount = 0
    scan_range = 0
    target = None
    while halite_amount == 0:
        scan_range += 1
        for x in range(-scan_range, scan_range):
            for y in range(-scan_range, scan_range):
                test_position = game_map.normalize(
                    Position(center_pos.x + x, center_pos.y + y))
                possible_target = game_map[test_position]
                if possible_target.is_occupied:
                    continue
                current_amount = possible_target.halite_amount
                if current_amount >= halite_amount:
                    halite_amount = current_amount
                    target = test_position
    return target


def determin_target(ship):
    start_targetting = time.process_time()
    target = None
    # Choose the closest most valueable
    closest = None
    if most_valueable_cells:
        for pos in most_valueable_cells:
            distance = game_map.calculate_distance(ship.position, pos)
            if closest is None or distance < closest:
                if pos in ship_targets:
                    continue
                closest = distance
                target = pos
    if ship_info[ship.id]["target_position"] \
            and ship_info[ship.id]["target_position"] in ship_targets:
        logging.info("Removing old target from ship targets....")
        idx = ship_targets.index(ship_info[ship.id]["target_position"])
        del ship_targets[idx]

    if target:
        logging.info("Targeting closest most valueable...")
        ship_info[ship.id]["target_position"] = target
        ship_targets.append(target)
        logging.info("targetting time: {}".format(time.process_time() - start_targetting))
    else:
        halite_amount = 0
        ship_amount = 0
        center_pos = ship.position
        for x in range(-2, 2):
            for y in range(-2, 2):
                test_position = game_map.normalize(
                    Position(center_pos.x + x, center_pos.y + y))
                # logging.info("ship_targets: {}".format(ship_targets))
                if game_map[test_position].ship:
                    ship_amount += 1
                possible_target = game_map[test_position]
                if test_position in ship_targets:
                    continue
                current_amount = possible_target.halite_amount
                if current_amount > halite_amount:
                    halite_amount = current_amount
                    target = test_position

        if most_valueable_cells:
            if ship_amount > 3:
                # Time to look else where:
                logging.info("Need to look elsewhere, too busy...")
                halite_amount = 0
                center_pos = random.choice(most_valueable_cells)
                for x in range(-3, 3):
                    for y in range(-3, 3):
                        test_position = game_map.normalize(
                            Position(center_pos.x + x, center_pos.y + y))
                        possible_target = game_map[test_position]
                        current_amount = possible_target.halite_amount
                        if current_amount > halite_amount:
                            halite_amount = current_amount
                            target = test_position
            elif target is None:
                logging.warning("Select random most valueable cell!!")
                target = random.choice(most_valueable_cells)

        if target is None:
            logging.info("Elected nearest valueable cell")
            target = closest_valueable_cell(ship.position)
        ship_targets.append(target)
        ship_info[ship.id]["target_position"] = target
        logging.info("Elected target {} for {}".format(target, ship))
        logging.info("targetting time: {}".format(time.process_time() - start_targetting))


def prevent_bounce_move(ship):
    if ship_info[ship.id]["target_position"] is None:
        determin_target(ship)

    if ship not in my_ships:
        logging.info("Ordering NON EXISTING ship!! {}".format(ship))
        return
    # intended_dir = game_map.naive_navigate(ship, ship_info[ship.id]["target_position"])
    intended_dir = game_map.a_star_navigate(
        ship, ship_info[ship.id]["target_position"])

    intended_position = ship.position.directional_offset(intended_dir)
    if len(ship_info[ship.id]["previous_pos"]) == 3:
        if intended_position == ship_info[ship.id]["previous_pos"][1]\
                and ship_info[ship.id]["previous_pos"][0] == ship_info[ship.id]["previous_pos"][2]:
            logging.warning("Ship is bouncing? {}".format(
                ship_info[ship.id]["previous_pos"]))
            intended_dir = game_map.naive_navigate(
                ship, ship_info[ship.id]["target_position"], intended_dir)
            # intended_dir = game_map.a_star_navigate(
            # ship, ship_info[ship.id]["target_position"], intended_position)
    return ship.move(intended_dir)


def move_ship(ship, force_move=False):
    if ship in ships_moved_this_turn:
        # logging.warning("I already moved this turn!!! {}".format(ship))
        return
    if ship not in my_ships:
        return

    end_game = game.turn_number > constants.MAX_TURNS * 0.97\
        - closest_dropoff_point(ship)[0]

    if end_game:
        closest_drop_off = closest_dropoff_point(ship)[1]
        distance = closest_dropoff_point(ship)[0]
        if distance > 1:
            move = ship.move(game_map.naive_navigate(
                ship, closest_drop_off))
        elif distance == 1:
            direction = game_map.get_unsafe_moves(
                ship.position, closest_drop_off)[0]
            move = ship.move(direction)
        else:
            move = ship.stay_still()

        command_queue.append(move)
        ships_moved_this_turn.append(ship)
        return

    ship_count = len(my_ships)

    if ship.id not in ship_info:
        ship_info[ship.id] = {
            'state': "exploring",
            'target_position': None,
            'total_miner': True if ship_count % 3 == 0 else False,
            'previous_pos': []
        }

    if ship.position in ship_targets:
        ship_targets.remove(ship.position)

    # logging.info("Initial state: {}".format(ship_info[ship.id]))
    ship_info[ship.id]['previous_pos'].append(ship.position)

    if len(ship_info[ship.id]['previous_pos']) > 3:
        del ship_info[ship.id]['previous_pos'][0]

    if ship_info[ship.id]["target_position"]\
            and ship_info[ship.id]["target_position"] == ship.position:
        # logging.info("Ship arrived at target.")
        ship_info[ship.id]["target_position"] = None

    if ship_info[ship.id]['total_miner']\
            and ship_info[ship.id]["state"] != "returning":
        closest_drop = closest_dropoff_point(ship)[0]

        if ship.percentage_filled >= closest_drop * 10:
            closest_drop_off = closest_dropoff_point(ship)[1]
            ship_info[ship.id]["state"] = "returning"
            move = ship.move(game_map.naive_navigate(ship, closest_drop_off))
            command_queue.append(move)
            ships_moved_this_turn.append(ship)
            return

        # Check for end game
        # and ship.percentage_filled > closest_drop:
        if end_game:
            closest_drop_off = closest_dropoff_point(ship)[1]
            # logging.info(
            #     "End game is near, total miner returning {}".format(ship.id))
            ship_info[ship.id]["target_position"] = closest_drop_off
            target = closest_drop_off
            ship_info[ship.id]["state"] = "returning"
            move = ship.move(game_map.naive_navigate(ship, target))
            logging.info("Target: {} Move: {}".format(target, move))
            command_queue.append(move)
            ships_moved_this_turn.append(ship)
            return

        if not ship.is_full:
            moving_costs = game_map[ship.position].cost
            if moving_costs > 5 or ship.halite_amount < moving_costs:
                ship_info[ship.id]['state'] = "collecting"
                game_map[ship.position].ship = ship
                command_queue.append(ship.stay_still())
                ships_moved_this_turn.append(ship)
                return
            else:
                ship_info[ship.id]['state'] = "exploring"
                target = closest_valueable_cell(ship.position)
                move = ship.move(game_map.naive_navigate(ship, target))
                command_queue.append(move)
                ships_moved_this_turn.append(ship)
                return

    moving_costs = game_map[ship.position].cost
    if ship.halite_amount < moving_costs:
        # Can't move even if we wanted to!!
        ship_info[ship.id]["state"] = "collecting"
        command_queue.append(ship.stay_still())
        ships_moved_this_turn.append(ship)
        return

    # check if ship is full enough to return
    check_for_drop(ship)

    if ship_info[ship.id]["state"] == "returning":
        # check if the ship is back yet
        if ship.halite_amount == 0 and not end_game:
            logging.info(
                "{} returned, setting to exploring again.".format(ship))
            ship_info[ship.id]["state"] = "exploring"
            ship_info[ship.id]["target_position"] = None
            # logging.info("Dropped off resource: {}".format(ship))
        elif ship.halite_amount == 0 and\
                game.turn_number >= constants.MAX_TURNS * 0.95:
            pass  # stay here
        else:
            if ship.is_full is False and\
                    moving_costs > ship.halite_amount * 0.1:
                command_queue.append(ship.stay_still())
                ships_moved_this_turn.append(ship)
                return
            if ship_info[ship.id]["target_position"] is None:
                ship_info[ship.id][
                    "target_position"] = closest_dropoff_point(ship)[1]
            distance = game_map.calculate_distance(
                ship.position, ship_info[ship.id]["target_position"])
            # Not dropped off yet, keep moving toward the shipyard
            global being_sniped
            target = ship_info[ship.id]["target_position"]
            if being_sniped and target == me.shipyard.position:
                if distance < 4:
                    # logging.info("Being sniped, force moving returning ship!")
                    direction = game_map.get_unsafe_moves(
                        ship.position, target)[0]
                    command_queue.append(ship.move(direction))
                    ships_moved_this_turn.append(ship)
                    return

            if distance == 1:
                # Check if there is a ship on the dropoff/shipyard
                if game_map[target].is_occupied and ship != game_map[target].ship:
                    if being_sniped:
                        direction = game_map.get_unsafe_moves(
                            ship.position, target)[0]
                        command_queue.append(ship.move(direction))
                        ships_moved_this_turn.append(ship)
                        being_sniped = False
                        return

                    # check if that shi has moved this turn:
                    occupier = game_map[
                        ship_info[ship.id]["target_position"]].ship
                    if game.turn_number > constants.MAX_TURNS * 0.95:
                        # Move anyway!!
                        direction = game_map.get_unsafe_moves(
                            ship.position, target)[0]
                        command_queue.append(ship.move(direction))
                        ships_moved_this_turn.append(ship)
                        return

                    if occupier.halite_amount > ship.halite_amount:
                        command_queue.append(ship.stay_still())
                        ships_moved_this_turn.append(ship)
                        return

                    if force_move or occupier in ships_moved_this_turn:
                        # Ship moved there before us, wait out turn
                        command_queue.append(ship.stay_still())
                        ships_moved_this_turn.append(ship)
                        return
                    else:
                        move_ship(occupier, True)

                        command_queue.append(prevent_bounce_move(ship))
                        ships_moved_this_turn.append(ship)
                        return

            command_queue.append(prevent_bounce_move(ship))
            ships_moved_this_turn.append(ship)
            return

    if ship_info[ship.id]["state"] == "collecting":
        if game_map.average_halite < 40 and\
                game_map[ship.position].halite_amount > 0 and not ship.is_full:
            logging.info("Map mined out, total mine!")
            ship_info[ship.id]["state"] = "collecting"
            command_queue.append(ship.stay_still())
            ships_moved_this_turn.append(ship)
            return

        if game.turn_number <= 30:
            if not ship.is_full_enough and moving_costs > 3:
                # Stay collecting
                ship_info[ship.id]["state"] = "collecting"
                command_queue.append(ship.stay_still())
                ships_moved_this_turn.append(ship)
                return
            elif game_map[ship.position].halite_amount == 0:
                ship_info[ship.id]["state"] = "returning"
                ship_info[ship.id][
                    "target_position"] = closest_dropoff_point(ship)[1]
                command_queue.append(prevent_bounce_move(ship))
                ships_moved_this_turn.append(ship)
                return

        # and game.turn_number <= 50:
        if closest_dropoff_point(ship)[0] < 10 and ship_count < 5:
            if game_map[ship.position].halite_amount > (constants.MAX_HALITE - 100 * closest_dropoff_point(ship)[0]) and not ship.is_full:
                # Stay collecting
                ship_info[ship.id]["state"] = "collecting"
                command_queue.append(ship.stay_still())
                ships_moved_this_turn.append(ship)
                return
            elif ship.is_full_enough:
                ship_info[ship.id]["state"] = "returning"
                ship_info[ship.id][
                    "target_position"] = closest_dropoff_point(ship)[1]
                command_queue.append(prevent_bounce_move(ship))
                ships_moved_this_turn.append(ship)
                return

        if closest_dropoff_point(ship)[0] > 10 and not ship.is_full_enough and moving_costs > 5:
            # Stay collecting
            ship_info[ship.id]["state"] = "collecting"
            command_queue.append(ship.stay_still())
            ships_moved_this_turn.append(ship)
            return

        if game_map[ship.position].halite_amount == 0 and not ship.is_full_enough:
            determin_target(ship)
            ship_info[ship.id]["state"] = "exploring"

        if not ship.is_full and game_map[ship.position].halite_amount >= game_map.average_halite:
            logging.info("More than the average on the map, keep collecting")
            ship_info[ship.id]["state"] = "collecting"
            command_queue.append(ship.stay_still())
            ships_moved_this_turn.append(ship)
            return

        if not ship.is_full and game_map[ship.position].halite_amount > constants.MAX_HALITE / 2:
            # logging.info("Collecting Halite. Amount in ship: {} Amount left: {}".format(ship.halite_amount, game_map[ship.position].halite_amount))
            ship_info[ship.id]["state"] = "collecting"
            command_queue.append(ship.stay_still())
            ships_moved_this_turn.append(ship)
            return
        else:
            check_for_drop(ship)

    # if ship_info[ship.id]["state"] == "exploring" and ship_info[ship.id]["target_position"]:
        # distance = game_map.calculate_distance(ship.position, ship_info[ship.id]["target_position"])
        # Check the position, is it ocupied?
        # if distance < 2 and game_map[ship_info[ship.id]["target_position"]].is_occupied:
        #     ship_info[ship.id]["target_position"] = None
        #     determin_target(ship)

    # For each of your ships, move if the ship is on a low halite location.
    #   Else, collect halite.
    # ship.halite_amount > constants.MAX_HALITE * 0.7 and
    if ship_info[ship.id]["target_position"] is None:
        logging.info("Determin new target for ship {}".format(ship))
        determin_target(ship)
        logging.info("New target? {}".format(
            ship_info[ship.id]['target_position']))
    distance = closest_dropoff_point(ship)[0]
    if ship_info[ship.id]["state"] == "exploring" and distance <= 2 and ship.halite_amount > 100:
        closest_drop_off = closest_dropoff_point(ship)[1]
        if game_map[closest_drop_off].is_occupied and distance == 1:
            move = ship.stay_still()
        else:
            move = ship.move(game_map.naive_navigate(ship, closest_drop_off))
        command_queue.append(move)
        ships_moved_this_turn.append(ship)
        return

    if moving_costs < ship.halite_amount * 0.05:
        # ship_info[ship.id]["state"] = "exploring"
        command_queue.append(prevent_bounce_move(ship))
        ships_moved_this_turn.append(ship)
    elif game_map[ship.position].halite_amount <= 100:
        command_queue.append(prevent_bounce_move(ship))
        ships_moved_this_turn.append(ship)
    else:
        # logging.info("Ordering ship to stay put: {}".format(ship))
        ship_info[ship.id]["state"] = "collecting"

        command_queue.append(ship.stay_still())
        ships_moved_this_turn.append(ship)


def cache_most_valueable(cells):
    check_cache_most_valueable()
    global most_valueable_cells_cache

    for pos in cells:
        if pos not in most_valueable_cells_cache:
            most_valueable_cells_cache[pos] = {
                'halite_amount': game_map[pos].halite_amount,
                'turn_added': game.turn_number
            }
        else:
            most_valueable_cells_cache[pos][
                'halite_amount'] = game_map[pos].halite_amount
            most_valueable_cells_cache[pos][
                'turn_added'] = game.turn_number


def check_cache_most_valueable():
    to_del = []
    for pos in most_valueable_cells_cache:
        if most_valueable_cells_cache[pos]['halite_amount'] > game_map[pos].halite_amount:
            to_del.append(pos)
        elif most_valueable_cells_cache[pos]['turn_added'] < game.turn_number - 20:
            to_del.append(pos)
    for pos in to_del:
        del most_valueable_cells_cache[pos]


def scan_drop_of_values():
    highest_amount_found = 100
    scan_range = 10

    if game.turn_number <= 30:
        highest_amount_found = 20
        scan_range = 5
    ship_count = len(my_ships)
    for center_pos in drop_off_points:
        for x in range(-scan_range, scan_range):
            for y in range(-scan_range, scan_range):
                test_position = game_map[
                    Position(center_pos.x + x, center_pos.y + y)]
                if test_position.is_occupied:
                    continue
                if test_position.halite_amount >= highest_amount_found:
                    if ship_count > 2 and len(most_valueable_cells) > ship_count - 2:
                        del most_valueable_cells[0]
                        # del most_values[0]
                    most_valueable_cells.append(test_position.position)
                    # most_values.append(test_position.halite_amount)
                    highest_amount_found = test_position.halite_amount

    if ship_count < 6:
        logging.info(
            "Low amount of ship ({}) returning cells".format(ship_count))
        cache_most_valueable(most_valueable_cells)
        return most_valueable_cells

    if ship_count > 4 and len(most_valueable_cells) > ship_count - 2:
        # No need to check the entire map!
        logging.info("No need for map scan. Highest: {} positions: {}".format(
            highest_amount_found, most_valueable_cells))
        cache_most_valueable(most_valueable_cells)
        return most_valueable_cells
    if game.turn_number > constants.MAX_TURNS * 0.75:
        cache_most_valueable(most_valueable_cells)
        return most_valueable_cells
    # highest_amount_found = 0

def determin_most_valueable():
    if game.turn_number > constants.MAX_TURNS * 0.9:
        return list(most_valueable_cells_cache.keys())
    most_valueable_cells = []
    # most_values = []
    check_cache_most_valueable()
    cache_keys = len(most_valueable_cells_cache.keys())
    if cache_keys > 0:
        cells = sorted(most_valueable_cells_cache, key=lambda c: most_valueable_cells_cache[
                       c]['halite_amount'], reverse=True)
        return cells  # list(most_valueable_cells_cache.keys())

    logging.info("Scanning map for valueable fields...")
    # Find the highest amounts of halite on the map
    most_valueable_cells = game_map.most_valueable_cells()
    logging.info("Highest amount found: {}".format(most_valueable_cells[0].halite_amount))
    most_valueable_cells = list(map(lambda c: c.position, most_valueable_cells))

    cache_most_valueable(most_valueable_cells)
    return most_valueable_cells

while True:
    start_time = time.process_time()
    # This loop handles each turn of the game. The game object changes every turn, and you refresh that state by
    #   running update_frame().
    game.update_frame()
    # You extract player metadata and the updated map metadata here for
    # convenience.
    me = game.me
    game_map = game.game_map
    my_ships = me.get_ships()
    logging.info("Ship count: {} Halite: {} Map (tot/avg): {}/{}".format(
        len(my_ships), me.halite_amount, game_map.total_halite, game_map.average_halite))
    ship_targets = []
    cache_drop_offs = {}
    # Determin the place of enemy ships
    for player in opponents:
        for ship in player.get_ships():
            mark_area_unsafe(ship)

    most_valueable_cells = determin_most_valueable()

    dropoff_count = len(drop_off_points)
    ship_count = len(my_ships)

    created_drop_off = False

    if game_map[me.shipyard].is_occupied and not game_map[me.shipyard].ship in my_ships:
        logging.info("Snipercheck: {} being_sniped: {}".format(
            sniper_check, being_sniped))
        logging.info("Ship detected on shipyard.")
        if sniper_check is None:
            sniper_check = game_map[me.shipyard].ship
        elif sniper_check.id == game_map[me.shipyard].ship.id:
            being_sniped = True
        else:
            sniper_check = game_map[me.shipyard].ship
    else:
        sniper_check = None
        being_sniped = False

    if being_sniped:
        logging.info("Enemy on our shipyard! We're being sniped!!!")
        unmark_area_unsafe(me.shipyard.position)

    # logging.info("Most valueable cells: {} Max: {}".format(# most_values,
    # highest_amount_found))

    # A command queue holds all the commands you will run this turn. You build this list up and submit it at the
    #   end of the turn.
    command_queue = []
    ships_moved_this_turn = []

    ship_ids = []

    for ship in my_ships:
        ship_ids.append(ship.id)
        # Dont!!! Mark the position of the ship on the map
        # game_map[ship.position].ship = ship
        if ship.id not in ship_info:
            ship_info[ship.id] = {
                'state': "exploring",
                'target_position': None,
                'total_miner': ship_count % 2 == 0,
                'sniper': False,
                'previous_pos': []
            }

    for key in ship_info.keys() - ship_ids:
        logging.warning("We lost ship {} -> {}".format(key, ship_info[key]))
        del ship_info[key]

    create_drop()
    determin_sniper()

    snipers = [me.get_ship(k)
               for (k, v) in ship_info.items() if v['sniper']]
    returning = np.array([me.get_ship(k) for (k, v) in ship_info.items() if v[
                       'state'] == 'returning'])
    returning = sorted(returning, key=lambda k: k.halite_amount, reverse=True)
    logging.info("returning: {}".format(returning))
    collecting = np.array([me.get_ship(k) for (k, v) in ship_info.items() if v[
                        'state'] == 'collecting'])
    collecting = sorted(collecting, key=lambda k: k.halite_amount, reverse=True)
    exploring = np.array([me.get_ship(k) for (k, v) in ship_info.items() if v[
                        'state'] == 'exploring'])
    exploring = sorted(exploring, key=lambda k: k.halite_amount, reverse=True)

    # logging.info("Retuning ships: {}".format(returning))

    empty_returning = [ship for ship in returning if ship.halite_amount == 0]
    other_returning = [ship for ship in returning if ship.halite_amount > 0]

    for ship in snipers:
        if ship in ships_moved_this_turn:
            continue
        if time.process_time() - start_time > 1.5:
            logging.info("Taking too long! snipers")
        move_sniper(ship)

    for ship in empty_returning:
        if ship in ships_moved_this_turn:
            continue
        if time.process_time() - start_time > 1.5:
            logging.info("Taking too long! empty_returning")
        move_ship(ship)

    for ship in other_returning:
        if ship in ships_moved_this_turn:
            continue
        if time.process_time() - start_time > 1.5:
            logging.info("Taking too long! other_returning")
        move_ship(ship)

    for ship in exploring:
        if ship in ships_moved_this_turn:
            continue
        if time.process_time() - start_time > 1.5:
            logging.info("Taking too long! exploring")
        move_ship(ship)

    for ship in collecting:
        if ship in ships_moved_this_turn:
            continue
        if time.process_time() - start_time > 1.5:
            logging.info("Taking too long! collecting")
        move_ship(ship)

    # If the game is in the first 200 turns and you have enough halite, spawn a ship.
    # Don't spawn a ship if you currently have a ship at port, though - the ships will collide.
    # if game.turn_number <= 200 and me.halite_amount >= constants.SHIP_COST
    # and not game_map[me.shipyard].is_occupied:

    if game.turn_number <= constants.MAX_TURNS * 0.55:
        all_ocupied = True
        returning = False
        for pos in me.shipyard.position.neighbors():
            if game_map[pos].ship is None:
                all_ocupied = False
            else:
                ship = game_map[pos].ship
                if ship in my_ships and ship_info[ship.id]['state'] == 'returning':
                    returning = True

        # cutt_off_point = constants.SHIP_COST * \
        #     (1.0 + (game.turn_number / constants.MAX_TURNS))
        # logging.info("Cutt off: {}".format(cutt_off_point))

        if not returning and not all_ocupied and me.halite_amount >= constants.SHIP_COST:
            if game_map[me.shipyard].is_occupied:
                ship = game_map[me.shipyard].ship
                if ship in my_ships:
                    if ship_info[ship.id]['state'] == 'exploring' \
                            and ship.position == me.shipyard.position \
                            and ship in ships_moved_this_turn:
                        command_queue.append(me.shipyard.spawn())
                        logging.info(
                            "{} moving away, spawning new ship!".format(ship))
                else:
                    logging.info("Shipyard occupied, not spawning.")
            else:
                command_queue.append(me.shipyard.spawn())
                logging.info("Spawning new ship!")

    # Send your moves back to the game environment, ending this turn.
    end_time = time.process_time()
    game.end_turn(command_queue)
    logging.info("Turn time: {}".format(end_time - start_time))
