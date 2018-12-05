#!/usr/bin/env python3
# Python 3.6

# Import the Halite SDK, which will let you interact with the game.
import hlt

import heapq

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
command_queue = []
most_valueable_cells = []
ship_targets = []
intended_moves = {}
game_map = game.game_map
me = game.me
ship_info = {}

# At this point "game" variable is populated with initial map data.
# This is a good place to do computationally expensive start-up pre-processing.
# As soon as you call "ready" function below, the 2 second per turn timer
# will start.
game.ready("AlternativeChaosBot")


def determin_target(ship):
    if ship_info[ship.id]["state"] == "returning":
        ship_info[ship.id]["target_position"] = closest_dropoff(ship)
        return

    center_pos = ship.position
    target = None
    # Choose the closest most valueable
    closest = None
    for pos in most_valueable_cells:
        distance = game_map.calculate_distance(ship.position, pos)
        if closest is None or distance < closest:
            closest = distance
            target = pos
    if target:
        logging.info("Targeting closest most valueable...")
        ship_info[ship.id]["target_position"] = target
        ship_targets.append(target)
    else:
        halite_amount = 0
        for x in range(-2, 2):
            for y in range(-2, 2):
                test_position = game_map.normalize(
                    Position(center_pos.x + x, center_pos.y + y))
                if test_position in ship_targets:
                    continue
                possible_target = game_map[test_position]
                current_amount = possible_target.halite_amount
                if current_amount > halite_amount:
                    halite_amount = current_amount
                    target = test_position
        ship_targets.append(target)
        ship_info[ship.id]["target_position"] = target


def fill_intended_moves():
    # Remove all own ships
    own_ships = me.get_ships()
    for y in range(game_map.height):
            for x in range(game_map.width):
                test_ship = game_map[Position(x, y)].ship
                if test_ship and test_ship in own_ships:
                    game_map[Position(x, y)].ship = None
    
    intended_moves = {}
    for ship in me.get_ships():
        if ship.id not in ship_info.keys():
            continue
        check_for_dropoff(ship)
        # logging.info("Checking ship({}) -> {}".format(ship, ship_info[ship.id]))
        if ship.position in ship_targets:
            ship_targets.remove(ship.position)

        if ship_info[ship.id]["target_position"] and ship_info[ship.id]["target_position"] == ship.position:
            if ship_info[ship.id]["state"] == "exploring":
                logging.info("Ship reached target, collecting")
                ship_info[ship.id]["state"] = "collecting"
            elif ship_info[ship.id]["state"] == "returning":
                ship_info[ship.id]["state"] = "exploring"
                ship_info[ship.id]["target_position"] = None
                logging.info("Ship returned? -> {}".format(ship.halite_amount))

        if game_map[ship.position].has_structure and ship.halite_amount == 0:
            ship_info[ship.id]["state"] = "exploring"

        moving_costs = game_map[ship.position].halite_amount / constants.MOVE_COST_RATIO
        if ship.halite_amount < moving_costs:
            logging.warning("Can't move ship! It would cost {} and we have {}".format(moving_costs, ship.halite_amount))
            # Can't move even if we wanted to!!
            ship_info[ship.id]["state"] = "collecting"

        if ship_info[ship.id]['state'] == "collecting":
            if game_map[ship.position].halite_amount <= 80 or moving_costs < ship.halite_amount * 0.05:
                ship_info[ship.id]["state"] = "exploring"
            else:
                if ship.position not in intended_moves:
                    intended_moves[ship.position] = {"ships": []}
                intended_moves[ship.position]["ships"].append(ship)
                continue

        if ship_info[ship.id]["target_position"] is None:
            determin_target(ship)
        if ship.position == ship_info[ship.id]["target_position"]:
            if ship.position not in intended_moves:
                intended_moves[ship.position] = {"ships": []}
            ship_info[ship.id]["state"] = "collecting"
            intended_moves[ship.position]["ships"].append(ship)
            continue

        logging.info("Start: {} Goal: {}".format(ship.position, ship_info[ship.id]['target_position']))
        path = a_star_search(ship, ship_info[ship.id]['target_position'])
        logging.info("Path: {}".format(path))
        # logging.info("costs keys only: {}".format(costs.keys()))
        if path is None:
            logging.info("There is no path to goal!")
            position = ship.position
        else:
            position = path[1]
            logging.info("Next move: {}".format(position))

        # direction = game_map.get_unsafe_moves(
        #     ship.position, ship_info[ship.id]['target_position'])[0]
        # position = ship.position.directional_offset(direction)
        # logging.info()
        if position not in intended_moves:
            intended_moves[position] = {"ships": []}
        intended_moves[position]["ships"].append(ship)
    return intended_moves


def ship_is_mine(ship):
    return ship in me.get_ships()


def resolve_intended_moves(moves):
    # Execute each intended_move
    for key in moves:
        data = moves[key]
        ship = data["ships"][0]
        target = key
        direction = ship.position.directional(target)
        target_position = key

        logging.info("Ship {} is {}".format(ship.id, ship_info[ship.id]["state"]))

        if target_position == ship.position:
            logging.info("Ship info: {}".format(ship_info[ship.id]))
            logging.info("Ship staying still")
            command_queue.append(ship.stay_still())
            continue

        if ship_info[ship.id]["state"] == "returning":
            logging.info(ship_info[ship.id])
            logging.info("Shipyard pos: {}".format(me.shipyard.position))

        if ship_info[ship.id]["state"] == "collecting":
            logging.info("{} collecting at {}".format(ship, ship.position))
            command_queue.append(ship.stay_still())
        else:
            if game_map[ship.position].cost <= ship.halite_amount:
                logging.info("Moving {} to {}".format(ship, target_position))
                if direction is None:
                    logging.info("No direction set!")
                    direction = game_map.get_unsafe_moves(ship.position, target_position)[0]
                command_queue.append(ship.move(direction))
            else:
                logging.info("Can't move ship! -> {} > {}".format(game_map[ship.position].cost, ship.halite_amount))
                command_queue.append(ship.stay_still())

    logging.info("Executed moves.")


def check_intended_moves(moves):
    logging.debug("Moves: {}".format(moves))
    new_intended_moves = {}
    positions_done = []
    needs_recheck = False

    for position in moves:
        data = moves[position]
        # logging.info("Position: {} Data: {}".format(position, data))
        if len(data["ships"]) > 1:
            logging.info(
                "More ships want to go to the same space!! -> {}".format(position))
            # Two or more ships want to go to the same place!
            prio_ship = None
            returning = None
            most_halite = 0
            for ship in data["ships"]:
                if ship_info[ship.id]["state"] == "collecting" and ship.position == position:
                    prio_ship = ship
                    break
                if ship_info[ship.id]["state"] == "returning":
                    returning = ship
                    if prio_ship is None or returning.halite_amount < ship.halite_amount:
                        prio_ship = ship
                        returning = ship
                elif returning is None and ship.halite_amount > most_halite:
                    prio_ship = ship
                    most_halite = ship.halite_amount
            logging.info("Priority ship: {}".format(prio_ship))

            if position not in new_intended_moves:
                new_intended_moves[position] = {"ships": []}
            if prio_ship not in new_intended_moves[position]["ships"]: 
                new_intended_moves[position]["ships"].append(prio_ship)
                game_map[position].ship = prio_ship

            logging.info("Checking other ships...")
            for ship in data["ships"]:
                if ship == prio_ship:
                    continue
                logging.info("Checking {}".format(ship.id))
                if ship_info[ship.id]["state"] == "collecting" and ship.position != position:
                    logging.info("Collecting, staying at {}".format(ship.position))
                    if ship.position not in new_intended_moves:
                        new_intended_moves[ship.position] = {"ships": []}

                    if ship not in new_intended_moves[ship.position]["ships"]:
                        new_intended_moves[ship.position]["ships"].append(ship)
                    continue

                if ship_info[ship.id]["target_position"] == position:
                    # Can't move to this target, elect new one
                    logging.info("Old target: {}".format(ship_info[ship.id]["target_position"]))
                    determin_target(ship)
                    logging.info("New target: {}".format(ship_info[ship.id]["target_position"]))

                # Need an alternative route!
                # direction = game_map.naive_navigate(
                #     ship, ship_info[ship.id]["target_position"], me)
                # target_position = ship.position.directional_offset(direction)
                path = a_star_search(ship, ship_info[ship.id]['target_position'])
                logging.info("Path: {}".format(path))
                # logging.info("costs keys only: {}".format(costs.keys()))
                if path is None:
                    logging.info("Want {} -> {}".format(ship.position, ship_info[ship.id]['target_position']))
                    logging.info("There is no path to goal!")
                    target_position = ship.position
                else:
                    target_position = path[1]
                    logging.info("Next move: {}".format(target_position))

                if target_position not in new_intended_moves:
                    new_intended_moves[target_position] = {"ships": []}

                if ship not in new_intended_moves[target_position]["ships"]:
                    new_intended_moves[target_position]["ships"].append(ship)
        else:
            # Move ship to that pos
            ship = data["ships"][0]
            target = ship_info[ship.id]['target_position']
            target_position = None
            if target == ship.position:
                target_position = ship.position
            else:
                path = a_star_search(ship, target)
                if path is None:
                    logging.info("No path to target")
                    target_postition = ship.position
                else:
                    target_position = path[1]
                # direction = game_map.naive_navigate(ship, target, me)
                # target_position = ship.position.directional_offset(direction)
                if target_position is None:
                    target_position = ship.position
                logging.info("Target position: {}".format(target_position))

            if target_position not in new_intended_moves:
                new_intended_moves[target_position] = {"ships": []}
            if ship not in new_intended_moves[target_position]["ships"]:
                new_intended_moves[target_position]["ships"].append(ship)
                logging.info("Setting ship in game_map -> {} -> {}".format(target_position, ship))
                game_map[target_position].ship = ship
            continue

        # Check next position
        positions_done.append(position)
    # Now keep checking until moves have been resolved
    for key in new_intended_moves:
        if len(new_intended_moves[key]["ships"]) > 1:
            needs_recheck = True
            break

    if needs_recheck:
        return check_intended_moves(new_intended_moves)
    else:
        return new_intended_moves


def determin_high_halite_cells():
    ship_count = len(me.get_ships())
    highest_amount_found = 0
    most_valueable_cells = []
    # Find the highest amounts of halite on the map
    for x in range(game_map.height):
        for y in range(game_map.width):
            # Check the mapcells
            current_amount = game_map[Position(x, y)].halite_amount
            if game_map[Position(x, y)].is_occupied:
                continue
            if current_amount >= highest_amount_found:
                if ship_count > 2 and len(most_valueable_cells) > ship_count / 2:
                    del most_valueable_cells[0]
                    # del most_values[0]
                most_valueable_cells.append(Position(x, y))
                # most_values.append(current_amount)
                highest_amount_found = current_amount


def check_ship_info():
    ship_ids = []
    for ship in me.get_ships():
        ship_ids.append(ship.id)
        if ship.id not in ship_info:
            ship_info[ship.id] = {
                'state': "exploring",
                'target_position': None,
                'previous_pos': []
            }
    for key in ship_info.keys() - ship_ids:
        logging.warning("We lost ship {} -> {}".format(key, ship_info[key]))
        del ship_info[key]


def create_drop():
    if game.turn_number > constants.MAX_TURNS * 0.8:
        return
    if me.halite_amount < constants.DROPOFF_COST + constants.SHIP_COST:
        return

    if len(me.get_dropoffs()) > 1:
        return

    max_halite_found = 0
    max_ships_found = 0
    best_ship = None
    for ship in me.get_ships():
        # if not ship.id in ship_info:
        #     continue
        # Don't use ships that are returning to a base
        # if ship_info[ship.id]["state"] == "returning":
        #     continue

        dist_to_shipyard = game_map.calculate_distance(
            ship.position, me.shipyard.position)
        if dist_to_shipyard <= 10:
            continue

        dist_to_drop_off = game_map.height
        for drop in me.get_dropoffs():
            if game_map.calculate_distance(ship.position, drop.position) < dist_to_drop_off:
                dist_to_drop_off = game_map.calculate_distance(
                    ship.position, drop.position)

        if dist_to_drop_off <= 10:
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
                if test_position.ship in me.get_ships():
                    own_ships += 1
                total_halite += test_position.halite_amount

        if total_halite > max_halite_found and own_ships > max_ships_found:
            max_ships_found = own_ships
            max_halite_found = total_halite
            best_ship = ship

    if best_ship and max_halite_found >= constants.MAX_HALITE * 5:
        cost = 4000 - \
            game_map[best_ship.position].halite_amount - \
            best_ship.halite_amount
        logging.info("In a 10x10 we found {} halite with {} ships. Creating drop point from {} for {}!".format(
            max_halite_found, max_ships_found, ship, cost))
        me.halite_amount -= cost
        command_queue.append(best_ship.make_dropoff())
        del ship_info[best_ship.id]


def closest_dropoff(ship):
    dist_to_shipyard = game_map.calculate_distance(
        ship.position, me.shipyard.position)
    closest_drop = 0
    closest_drop_off = None
    dist_to_drop_off = game_map.height
    for drop in me.get_dropoffs():
        if game_map.calculate_distance(ship.position, drop.position) < dist_to_drop_off:
            dist_to_drop_off = game_map.calculate_distance(
                ship.position, drop.position)
            closest_drop_off = drop.position

    return me.shipyard.position if dist_to_shipyard < dist_to_drop_off else closest_drop_off

def check_for_dropoff(ship):
    dist_to_shipyard = game_map.calculate_distance(
        ship.position, me.shipyard.position)
    closest_drop = 0
    closest_drop_off = None
    dist_to_drop_off = game_map.height
    for drop in me.get_dropoffs():
        if game_map.calculate_distance(ship.position, drop.position) < dist_to_drop_off:
            dist_to_drop_off = game_map.calculate_distance(
                ship.position, drop.position)
            closest_drop_off = drop.position

    closest_drop = dist_to_shipyard if dist_to_shipyard < dist_to_drop_off else dist_to_drop_off
    closest_drop_off = me.shipyard.position if dist_to_shipyard < dist_to_drop_off else closest_drop_off

    # Check for end game
    # and ship.percentage_filled > closest_drop:
    if game.turn_number > constants.MAX_TURNS - closest_drop - 10:
        logging.info("End game is near, returning {}".format(ship))
        ship_info[ship.id]["target_position"] = closest_drop_off
        ship_info[ship.id]["state"] = "returning"
        return

    if ship.is_full_enough:
        logging.info("Ship needs to return! {}".format(ship))
        ship_info[ship.id]["target_position"] = closest_drop_off
        ship_info[ship.id]["state"] = "returning"
    elif ship.percentage_filled > 10 and ship.percentage_filled >= closest_drop * 10:
        logging.info("Closest drop: {} Percentage full: {}".format(
            closest_drop, ship.percentage_filled))
        ship_info[ship.id]["target_position"] = closest_drop_off
        ship_info[ship.id]["state"] = "returning"


def heuristic(a, b):
    (x1, y1) = a.x, a.y
    (x2, y2) = b.x, b.y

    return abs(x1 - x2) + abs(y1 - y2) * 1.01

def a_star_search(ship, goal):
    frontier = PriorityQueue()
    start = ship.position
    frontier.put(start, 0)
    came_from = {}
    cost_so_far = {}
    came_from[start] = None
    cost_so_far[start] = 0
    
    while not frontier.empty():
        current = frontier.get()
        
        if current == goal:
            path = []
            while current != start:
                path.append(current)
                current = came_from[current]
            path.append(start)
            path.reverse()
            return path
        
        for next in game_map[current].position.neighbors():
            # if game_map[next].is_occupied:
            # if next in intended_moves:
            #     continue
            if game_map[next].ship is not None:
                logging.info("Ship detected: {}".format(game_map[next].ship))
                if ship != game_map[next].ship:
                    continue
            new_cost = cost_so_far[current] + game_map[next].cost
            if next not in cost_so_far or new_cost < cost_so_far[next]:
                cost_so_far[next] = new_cost
                priority = new_cost + heuristic(goal, next)
                frontier.put(next, priority)
                came_from[next] = current
    
    # return came_from, cost_so_far


class PriorityQueue:
    def __init__(self):
        self.elements = []
    
    def empty(self):
        return len(self.elements) == 0
    
    def put(self, item, priority):
        heapq.heappush(self.elements, (priority, item))
    
    def get(self):
        return heapq.heappop(self.elements)[1]

while True:
    # This loop handles each turn of the game. The game object changes every turn, and you refresh that state by
    #   running update_frame().
    game.update_frame()
    command_queue = []
    # ship_targets = []
    # You extract player metadata and the updated map metadata here for
    # convenience.
    me = game.me
    game_map = game.game_map
    # Check targets
    determin_high_halite_cells()
    check_ship_info()
    create_drop()
    resolve_intended_moves(check_intended_moves(fill_intended_moves()))
    # logging.info("Resolved moves, resetting intended_moves")
    # intended_moves = {}

    # Spawn new ships
    if game.turn_number <= 200:
        if me.halite_amount >= constants.SHIP_COST and not game_map[me.shipyard].is_occupied:
            command_queue.append(me.shipyard.spawn())
            logging.info("Spawning new ship!")

    # Send your moves back to the game environment, ending this turn.
    game.end_turn(command_queue)
