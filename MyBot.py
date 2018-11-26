#!/usr/bin/env python3
# Python 3.6

# Import the Halite SDK, which will let you interact with the game.
import hlt

# This library contains constant values.
from hlt import constants

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

# Now that your bot is initialized, save a message to yourself in the log file with some important information.
#   Here, you log here your id, which you can always fetch from the game object by using my_id.
# logging.info("Successfully created bot! My Player ID is {}.".format(game.my_id))

""" <<<Game Loop>>> """

# Holds targets for ships
# Keep these outside the loop...
ship_targets = []
ship_info = {}

command_queue = []
ships_moved_this_turn = []
most_valueable_cells = []

intended_moves = {}

me = None
game_map = game.game_map
# As soon as you call "ready" function below, the 2 second per turn timer will start.
game.ready("ChaosBot")

def mark_area_unsafe(ship):
    # center_pos = ship.position
    game_map[ship.position].ship = ship
    all_directions = [Direction.North, Direction.East, Direction.South, Direction.West]
    for direction in all_directions:
        position = ship.position.directional_offset(direction)
        game_map[position].ship = ship
    # for x in range(-1, 1):
    #     for y in range(-1, 1):
            # game_map[Position(center_pos.x + x, center_pos.y + y)].ship = ship

def distance_to_closest_drop(ship):
    dist_to_shipyard = game_map.calculate_distance(ship.position, me.shipyard.position)
    closest_drop = 0
    closest_drop_off = None
    dist_to_drop_off = game_map.height
    for drop in me.get_dropoffs():
        if game_map.calculate_distance(ship.position, drop.position) < dist_to_drop_off:
            dist_to_drop_off = game_map.calculate_distance(ship.position, drop.position)
            closest_drop_off = drop.position

    return dist_to_shipyard if dist_to_shipyard < dist_to_drop_off else dist_to_drop_off

def closest_dropoff_point(ship):
    dist_to_shipyard = game_map.calculate_distance(ship.position, me.shipyard.position)
    closest_drop = 0
    closest_drop_off = None
    dist_to_drop_off = game_map.height
    for drop in me.get_dropoffs():
        if game_map.calculate_distance(ship.position, drop.position) < dist_to_drop_off:
            dist_to_drop_off = game_map.calculate_distance(ship.position, drop.position)
            closest_drop_off = drop.position
    return me.shipyard.position if dist_to_shipyard < dist_to_drop_off else closest_drop_off


def check_for_drop(ship):
    closest_drop = distance_to_closest_drop(ship)
    closest_drop_off = closest_dropoff_point(ship)

    # Check for end game
    if game.turn_number > constants.MAX_TURNS * 0.95 - closest_drop: # and ship.percentage_filled > closest_drop:
        logging.info("End game is near, returning {}".format(ship))
        ship_info[ship.id]["target_position"] = closest_drop_off
        ship_info[ship.id]["state"] = "returning"
        return

    if game.turn_number < game_map.height * 2:
        if closest_drop < 5:
            if game_map[ship.position].halite_amount < 50:
                logging.info("Ship needs to return! {}".format(ship))
                ship_info[ship.id]["target_position"] = closest_drop_off
                ship_info[ship.id]["state"] = "returning"

    if ship.is_full_enough:
        logging.info("Ship needs to return! {}".format(ship))
        ship_info[ship.id]["target_position"] = closest_drop_off
        ship_info[ship.id]["state"] = "returning"
    elif game.turn_number > constants.MAX_TURNS * 0.2 and ship.percentage_filled >= closest_drop * 10: # ship.percentage_filled > 20 and
        logging.info("Closest drop: {} Percentage full: {}".format(closest_drop, ship.percentage_filled))
        ship_info[ship.id]["target_position"] = closest_drop_off
        ship_info[ship.id]["state"] = "returning"
   

def create_drop():
    if game.turn_number > constants.MAX_TURNS * 0.8:
        return
    # if me.halite_amount < constants.DROPOFF_COST + constants.SHIP_COST:
    #     return
    if len(me.get_dropoffs()) > ship_count / 10 + 1:
        return

    max_halite_found = 0
    max_ships_found = 0
    best_ship = None
    # we_can_pay = False
    for ship in me.get_ships():
        if not ship.id in ship_info:
            continue
        # Don't use ships that are returning to a base
        # if ship_info[ship.id]["state"] == "returning":
        #     continue
        
        dist_to_shipyard = game_map.calculate_distance(ship.position, me.shipyard.position)
        if dist_to_shipyard <= 10:
            continue

        dist_to_drop_off = game_map.height
        for drop in me.get_dropoffs():
            if game_map.calculate_distance(ship.position, drop.position) < dist_to_drop_off:
                dist_to_drop_off = game_map.calculate_distance(ship.position, drop.position)

        if dist_to_drop_off <= 10:
            continue

        if game_map[ship.position].has_structure:
            continue

        center_pos = ship.position
        total_halite = 0
        own_ships = 0
        for x in range(-5, 5):
            for y in range(-5, 5):
                test_position = game_map[Position(center_pos.x + x, center_pos.y + y)]
                if test_position.ship in me.get_ships():
                    own_ships += 1
                total_halite += test_position.halite_amount

        if total_halite > max_halite_found and own_ships > max_ships_found:
            max_ships_found = own_ships
            max_halite_found = total_halite
            best_ship = ship
            cost = 4000 - game_map[best_ship.position].halite_amount - best_ship.halite_amount
            # if cost < me.halite_amount:
            #     we_can_pay = True


    if best_ship and max_ships_found > 2 and max_halite_found >= constants.MAX_HALITE * 5:
        cost = 4000 - game_map[best_ship.position].halite_amount - best_ship.halite_amount
        if cost < me.halite_amount:
            logging.info("In a 10x10 we found {} halite with {} ships. Creating drop point from {} for {}!".format(max_halite_found, max_ships_found, ship, cost))
            me.halite_amount -= cost
            command_queue.append(best_ship.make_dropoff())
            ships_moved_this_turn.append(best_ship)
            del ship_info[best_ship.id]

def determin_target(ship):
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
    if ship_info[ship.id]["target_position"] and ship_info[ship.id]["target_position"] in ship_targets:
        logging.info("Removing old target from ship targets....")
        idx = ship_targets.index(ship_info[ship.id]["target_position"])
        del ship_targets[idx]

    if target:
        logging.info("Targeting closest most valueable...")
        ship_info[ship.id]["target_position"] = target
        ship_targets.append(target)
    else:
        halite_amount = 0
        ship_amount = 0
        center_pos = ship.position
        for x in range(-2, 2):
            for y in range(-2, 2):
                test_position = game_map.normalize(Position(center_pos.x + x, center_pos.y + y))
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
                        test_position = game_map.normalize(Position(center_pos.x + x, center_pos.y + y))
                        possible_target = game_map[test_position]
                        current_amount = possible_target.halite_amount
                        if current_amount > halite_amount:
                            halite_amount = current_amount
                            target = test_position
            elif target is None:
                logging.warning("Select random most valueable cell!!")
                target = random.choice(most_valueable_cells)

        ship_targets.append(target)
        ship_info[ship.id]["target_position"] = target
        logging.info("Elected target {} for {}".format(target, ship))
        
def prevent_bounce_move(ship):
    if ship_info[ship.id]["target_position"] is None:
        determin_target(ship)
    if ship not in me.get_ships():

        logging.info("Ordering NON EXISTING ship!! {}".format(ship))
        return
    intended_dir = game_map.naive_navigate(ship, ship_info[ship.id]["target_position"], me)

    intended_position = ship.position.directional_offset(intended_dir)
    if len(ship_info[ship.id]["previous_pos"]) == 3:
        if intended_position == ship_info[ship.id]["previous_pos"][1] and ship_info[ship.id]["previous_pos"][0] == ship_info[ship.id]["previous_pos"][2]:
            logging.warning("Ship is bouncing? {}".format(ship_info[ship.id]["previous_pos"]))
            intended_dir = game_map.naive_navigate(ship, ship_info[ship.id]["target_position"], me, intended_dir)

    return ship.move(intended_dir)

def move_ship(ship, force_move=False, stay_near=False):
    if ship in ships_moved_this_turn:
        # logging.warning("I already moved this turn!!! {}".format(ship))
        return
    if ship not in me.get_ships():
        return

    if ship.id not in ship_info:
        ship_info[ship.id] = {
            'state': "exploring",
            'target_position': None,
            'previous_pos': []
        }

    dropoff_count = len(me.get_dropoffs())
    ship_count = len(me.get_ships())
    created_drop_off = False

    if ship.position in ship_targets:
        ship_targets.remove(ship.position)

    # logging.info("Initial state: {}".format(ship_info[ship.id]))
    ship_info[ship.id]['previous_pos'].append(ship.position)

    if len(ship_info[ship.id]['previous_pos']) > 3:
        del ship_info[ship.id]['previous_pos'][0]

    if ship_info[ship.id]["target_position"] and ship_info[ship.id]["target_position"] == ship.position:
        # logging.info("Ship arrived at target.")
        ship_info[ship.id]["target_position"] = None

    moving_costs = game_map[ship.position].halite_amount / constants.MOVE_COST_RATIO
    if ship.halite_amount < moving_costs:
        logging.warning("Can't move ship! It would cost {} and we have {}".format(moving_costs, ship.halite_amount))
        # Can't move even if we wanted to!!
        ship_info[ship.id]["state"] = "collecting"
        command_queue.append(ship.stay_still())
        ships_moved_this_turn.append(ship)
        return

    # check if ship is full enough to return
    check_for_drop(ship)

    if ship_info[ship.id]["state"] == "returning":
        # check if the ship is back yet
        if ship.halite_amount == 0 and game.turn_number < constants.MAX_TURNS * 0.95:
            ship_info[ship.id]["state"] = "exploring"
            ship_info[ship.id]["target_position"] = None
            # logging.info("Dropped off resource: {}".format(ship))
        elif ship.halite_amount == 0 and game.turn_number >= constants.MAX_TURNS * 0.95:
            pass # stay here
        else:
            if ship.is_full == False and moving_costs > ship.halite_amount * 0.1:
                logging.info("It would cost too much halite to move! Cost: {} Max: {}".format(moving_costs, ship.halite_amount * 0.1))
                command_queue.append(ship.stay_still())
                ships_moved_this_turn.append(ship)
                return
            distance = game_map.calculate_distance(ship.position, ship_info[ship.id]["target_position"])
            # Not dropped off yet, keep moving toward the shipyard
            # logging.info("Ship returning: {} distance: {}".format(ship, distance))
            if distance == 1:
                # Check if there is a ship on the dropoff/shipyard
                if game_map[ship_info[ship.id]["target_position"]].is_occupied and ship != game_map[ship_info[ship.id]["target_position"]].ship:
                    # check if that shi has moved this turn:
                    occupier = game_map[ship_info[ship.id]["target_position"]].ship
                    if game.turn_number > constants.MAX_TURNS * 0.95:
                        # Move anyway!!
                        direction = game_map.get_unsafe_moves(ship.position, ship_info[ship.id]["target_position"])[0]
                        command_queue.append(ship.move(direction))
                        ships_moved_this_turn.append(ship)
                        return

                    if occupier.halite_amount > ship.halite_amount:
                        command_queue.append(ship.stay_still())
                        ships_moved_this_turn.append(ship)
                        return

                    if force_move or occupier in ships_moved_this_turn:
                        # Ship moved there before us, wait out turn
                        logging.info("There is a ship in the way({}), staying still. {}".format(occupier, ship))
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
        # if ship.halite_amount > moving_costs and moving_costs < ship.halite_amount / 5:
        #     # logging.info("We can move from here! Amount in ship: {} Amount left: {}".format(ship.halite_amount, game_map[ship.position].halite_amount))
        #     ship_info[ship.id]["state"] = "exploring"
        if game.turn_number <= 30:
            if not ship.is_full_enough and game_map[ship.position].halite_amount > 0:
                # Stay collecting
                ship_info[ship.id]["state"] = "collecting"
                command_queue.append(ship.stay_still())
                ships_moved_this_turn.append(ship)
                return
            elif game_map[ship.position].halite_amount == 0:
                ship_info[ship.id]["state"] = "returning"
                ship_info[ship.id]["target_position"] = closest_dropoff_point(ship)
                command_queue.append(prevent_bounce_move(ship))
                ships_moved_this_turn.append(ship)
                return

        if distance_to_closest_drop(ship) < 10 and ship_count < 5: # and game.turn_number <= 50:
            if game_map[ship.position].halite_amount > (constants.MAX_HALITE - 100 * distance_to_closest_drop(ship)) and not ship.is_full:
                # Stay collecting
                ship_info[ship.id]["state"] = "collecting"
                command_queue.append(ship.stay_still())
                ships_moved_this_turn.append(ship)
                return
            else:
                ship_info[ship.id]["state"] = "returning"
                ship_info[ship.id]["target_position"] = closest_dropoff_point(ship)
                command_queue.append(prevent_bounce_move(ship))
                ships_moved_this_turn.append(ship)
                return

        if distance_to_closest_drop(ship) > 10 and not ship.is_full_enough and game_map[ship.position].halite_amount > 0:
            # Stay collecting
            ship_info[ship.id]["state"] = "collecting"
            command_queue.append(ship.stay_still())
            ships_moved_this_turn.append(ship)
            return

        if game_map[ship.position].halite_amount == 0 and not ship.is_full_enough:
            determin_target(ship)
            ship_info[ship.id]["state"] = "exploring"


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
        logging.info("New target? {}".format(ship_info[ship.id]['target_position']))

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


def determin_most_valueable():
    most_valueable_cells = []
    most_values = []
    highest_amount_found = 200
    ship_count = len(me.get_ships())

    scan_centers = [me.shipyard.position]
    for drop in me.get_dropoffs():
        scan_centers.append(drop.position)

    for center_pos in scan_centers:
        for x in range(-5, 5):
            for y in range(-5, 5):
                test_position = game_map[Position(center_pos.x + x, center_pos.y + y)]
                if test_position.is_occupied:
                    continue
                if test_position.halite_amount >= highest_amount_found:
                    if ship_count > 2 and len(most_valueable_cells) > ship_count - 2:
                        del most_valueable_cells[0]
                        del most_values[0]
                    most_valueable_cells.append(test_position.position)
                    most_values.append(test_position.halite_amount)
                    highest_amount_found = test_position.halite_amount

    if ship_count > 4 and len(most_valueable_cells) > ship_count - 2:
        # No need to check the entire map!
        logging.info("No need for map scan. Highest: {} positions: {}".format(highest_amount_found, most_valueable_cells))
        return most_valueable_cells

    # highest_amount_found = 0
    logging.info("Scanning map for valueable fields...")
    # Find the highest amounts of halite on the map
    for x in range(game_map.height):
        for y in range(game_map.width):
            # Check the mapcells
            current_amount = game_map[Position(x, y)].halite_amount
            if game_map[Position(x, y)].is_occupied:
                continue
            if current_amount >= highest_amount_found:
                if ship_count > 2 and len(most_valueable_cells) > ship_count - 2:
                    del most_valueable_cells[0]
                    del most_values[0]
                most_valueable_cells.append(Position(x, y))
                most_values.append(current_amount)
                highest_amount_found = current_amount

    logging.info("Highest amount found: {}".format(highest_amount_found))
    return most_valueable_cells

while True:
    # This loop handles each turn of the game. The game object changes every turn, and you refresh that state by
    #   running update_frame().
    game.update_frame()
    # You extract player metadata and the updated map metadata here for convenience.
    me = game.me
    opponents = []
    ship_targets = []
    for playerid in game.players:
        if game.players[playerid] == me:
            continue
        opponents.append(game.players[playerid])

    game_map = game.game_map
    # Determin the place of enemy ships
    for player in opponents:
        for ship in player.get_ships():
            mark_area_unsafe(ship)

    most_valueable_cells = determin_most_valueable()
    logging.info("Most valueable cells: {}".format(most_valueable_cells))

    dropoff_count = len(me.get_dropoffs())
    ship_count = len(me.get_ships())

    created_drop_off = False

    # logging.info("Most valueable cells: {} Max: {}".format(most_values, highest_amount_found))

    # A command queue holds all the commands you will run this turn. You build this list up and submit it at the
    #   end of the turn.
    command_queue = []
    ships_moved_this_turn = []

    ship_ids = []

    create_drop()

    for ship in me.get_ships():
        ship_ids.append(ship.id)
        # Mark the position of the ship on the map
        game_map[ship.position].ship = ship
        if ship.id not in ship_info:
            ship_info[ship.id] = {
                'state': "exploring",
                'target_position': None,
                'previous_pos': []
            }

    for key in ship_info.keys() - ship_ids:
        logging.warning("We lost ship {} -> {}".format(key, ship_info[key]))
        del ship_info[key]

    returning = sorted([me.get_ship(k) for (k, v) in ship_info.items() if v['state'] == 'returning'], key=lambda k: k.halite_amount, reverse=True)
    collecting = [me.get_ship(k) for (k, v) in ship_info.items() if v['state'] == 'collecting']
    exploring = [me.get_ship(k) for (k, v) in ship_info.items() if v['state'] == 'exploring']
    
    logging.info("Retuning ships: {}".format(returning))
    for ship in returning:
        if ship in ships_moved_this_turn:
            continue
        move_ship(ship)

    for ship in exploring:
        if ship in ships_moved_this_turn:
            continue
        move_ship(ship)

    for ship in collecting:
        if ship in ships_moved_this_turn:
            continue
        move_ship(ship)

    # If the game is in the first 200 turns and you have enough halite, spawn a ship.
    # Don't spawn a ship if you currently have a ship at port, though - the ships will collide.
    # if game.turn_number <= 200 and me.halite_amount >= constants.SHIP_COST and not game_map[me.shipyard].is_occupied:

    if game.turn_number <= constants.MAX_TURNS / 2:
        if me.halite_amount >= constants.SHIP_COST and not game_map[me.shipyard].is_occupied:
            # if returning_incomming and not all_occupied:
            command_queue.append(me.shipyard.spawn())
            logging.info("Spawning new ship!")

        # if not returning_incomming and not all_collecting and
        #     command_queue.append(me.shipyard.spawn())
        #     logging.info("Spawning new ship!")

    # Send your moves back to the game environment, ending this turn.
    game.end_turn(command_queue)

