import queue

from . import constants
from .entity import Entity, Shipyard, Ship, Dropoff
from .player import Player
from .positionals import Direction, Position
from .common import read_input
import numpy as np
import logging
import random
import heapq


class PriorityQueue:

    def __init__(self):
        self.elements = []

    def empty(self):
        return len(self.elements) == 0

    def put(self, item, priority):
        heapq.heappush(self.elements, (priority, item))

    def get(self):
        return heapq.heappop(self.elements)[1]


class MapCell:
    """A cell on the game map."""

    def __init__(self, position, halite_amount):
        self.position = position
        self.halite_amount = halite_amount
        self.ship = None
        self.structure = None
        self._cost = halite_amount / constants.MOVE_COST_RATIO

    def update_cost(self):
        self._cost = self.halite_amount / constants.MOVE_COST_RATIO

    @property
    def cost(self):
        return self._cost

    @property
    def is_empty(self):
        """
        :return: Whether this cell has no ships or structures
        """
        return self.ship is None and self.structure is None

    @property
    def is_occupied(self):
        """
        :return: Whether this cell has any ships
        """
        return self.ship is not None

    @property
    def has_structure(self):
        """
        :return: Whether this cell has any structures
        """
        return self.structure is not None

    @property
    def structure_type(self):
        """
        :return: What is the structure type in this cell
        """
        return None if not self.structure else type(self.structure)

    def mark_unsafe(self, ship):
        """
        Mark this cell as unsafe (occupied) for navigation.

        Use in conjunction with GameMap.naive_navigate.
        """
        self.ship = ship

    def __eq__(self, other):
        return self.position == other.position

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return 'MapCell({}, halite={})'.format(self.position, self.halite_amount)


class GameMap:
    """
    The game map.

    Can be indexed by a position, or by a contained entity.
    Coordinates start at 0. Coordinates are normalized for you
    """

    def __init__(self, cells, width, height):
        self.width = width
        self.height = height
        self._cells = cells
        self._average = None
        self._total = None

    def __getitem__(self, location):
        """
        Getter for position object or entity objects within the game map
        :param location: the position or entity to access in this map
        :return: the contents housing that cell or entity
        """
        if isinstance(location, Position):
            location = self.normalize(location)
            return self._cells[location.y][location.x]
        elif isinstance(location, Entity):
            return self._cells[location.position.y][location.position.x]
        return None

    @property
    def total_halite(self):
        if not self._total:
            cells = np.array(self._cells).flatten()
            tot = 0
            tot += sum(c.halite_amount for c in cells)
            self._total = tot
        return self._total

    @property
    def average_halite(self):
        if not self._average:
            self._average = self.total_halite / (self.width * self.height)
        return self._average

    def most_valueable_cells(self):
        all_cells = np.array(self._cells).flatten()
        return sorted(all_cells, key=lambda c: c.halite_amount, reverse=True)[:10]


    def calculate_distance(self, source, target):
        """
        Compute the Manhattan distance between two locations.
        Accounts for wrap-around.
        :param source: The source from where to calculate
        :param target: The target to where calculate
        :return: The distance between these items
        """
        source = self.normalize(source)
        target = self.normalize(target)
        resulting_position = abs(source - target)
        return min(resulting_position.x, self.width - resulting_position.x) + \
            min(resulting_position.y, self.height - resulting_position.y)

    def normalize(self, position):
        """
        Normalized the position within the bounds of the toroidal map.
        i.e.: Takes a point which may or may not be within width and
        height bounds, and places it within those bounds considering
        wraparound.
        :param position: A position object.
        :return: A normalized position object fitting within the bounds of the map
        """
        return Position(position.x % self.width, position.y % self.height)

    @staticmethod
    def _get_target_direction(source, target):
        """
        Returns where in the cardinality spectrum the target is from source. e.g.: North, East; South, West; etc.
        NOTE: Ignores toroid
        :param source: The source position
        :param target: The target position
        :return: A tuple containing the target Direction. A tuple item (or both) could be None if within same coords
        """
        return (Direction.South if target.y > source.y else Direction.North if target.y < source.y else None,
                Direction.East if target.x > source.x else Direction.West if target.x < source.x else None)

    def get_unsafe_moves(self, source, destination):
        """
        Return the Direction(s) to move closer to the target point, or empty if the points are the same.
        This move mechanic does not account for collisions. The multiple directions are if both directional movements
        are viable.
        :param source: The starting position
        :param destination: The destination towards which you wish to move your object.
        :return: A list of valid (closest) Directions towards your target.
        """
        source = self.normalize(source)
        destination = self.normalize(destination)
        possible_moves = []
        distance = abs(destination - source)
        y_cardinality, x_cardinality = self._get_target_direction(
            source, destination)

        if distance.x != 0:
            possible_moves.append(x_cardinality if distance.x < (self.width / 2)
                                  else Direction.invert(x_cardinality))
        if distance.y != 0:
            possible_moves.append(y_cardinality if distance.y < (self.height / 2)
                                  else Direction.invert(y_cardinality))
        return possible_moves

    def naive_navigate(self, ship, destination, excluded_direction=None):
        """
        Returns a singular safe move towards the destination.

        :param ship: The ship to move.
        :param destination: Ending position
        :return: A direction.
        """
        # No need to normalize destination, since get_unsafe_moves
        # does that
        best_direction = None
        lowest_cost = None
        for direction in self.get_unsafe_moves(ship.position, destination):
            if excluded_direction and excluded_direction == direction:
                continue
            target_pos = ship.position.directional_offset(direction)
            if not self[target_pos].is_occupied:
                cost = self[target_pos].halite_amount / \
                    constants.MOVE_COST_RATIO
                if lowest_cost is None or cost < lowest_cost:
                    lowest_cost = cost
                    best_direction = direction

        if best_direction:
            target_pos = ship.position.directional_offset(direction)
            if not self[target_pos].is_occupied:
                # logging.debug("1. Found best direction. Cost: {}".format(lowest_cost))
                self[target_pos].mark_unsafe(ship)
                return direction

        # Cant move in a good direction, let's see if we can move in any
        # direction
        lowest_cost = None
        best_direction = None
        all_directions = [Direction.North, Direction.East,
                          Direction.South, Direction.West]
        random.shuffle(all_directions)
        for direction in all_directions:
            target_pos = ship.position.directional_offset(direction)
            if excluded_direction and excluded_direction == direction:
                continue
            if not self[target_pos].is_occupied:
                cost = self[target_pos].halite_amount / \
                    constants.MOVE_COST_RATIO
                if lowest_cost is None or cost < lowest_cost:
                    lowest_cost = cost
                    best_direction = direction

        if best_direction:
            target_pos = ship.position.directional_offset(direction)
            if not self[target_pos].is_occupied:
                # logging.debug("2. Found best direction. Cost: {}".format(lowest_cost))
                self[target_pos].mark_unsafe(ship)
                return direction
        # Still nowhere to go?
        for direction in all_directions:
            if excluded_direction and excluded_direction == direction:
                continue
            target_pos = ship.position.directional_offset(direction)
            if not self[target_pos].is_occupied:
                # logging.debug("3. Found best direction. Cost: {}".format(lowest_cost))
                self[target_pos].mark_unsafe(ship)
                return direction
        # We can't move at all, lay still and hope for the best...
        # logging.info("We can't move, ordering to stay still... {}".format(ship))
        return Direction.Still

    def heuristic(self, a, b):
        return self.calculate_distance(a, b)
        # (x1, y1) = a.x, a.y
        # (x2, y2) = b.x, b.y

        # return abs(x1 - x2) + abs(y1 - y2)

    def a_star_navigate(self, ship, goal, blocked_position=None):
        start = ship.position
        if blocked_position:
            exclude_dir = ship.position.directional(blocked_position)
        else:
            exclude_dir = None

        if self.calculate_distance(start, goal) > 5:
            # Too far away to calc with this
            return self.naive_navigate(ship, goal, exclude_dir)
        logging.debug("Distance astar: {}".format(self.calculate_distance(start, goal)))
        frontier = PriorityQueue()
        frontier.put(start, 0)
        came_from = {}
        cost_so_far = {}
        came_from[start] = None
        cost_so_far[start] = 0

        while not frontier.empty():
            current = frontier.get()

            if current == goal:
                # path = []
                pos = None
                while current != start:
                    # path.append(current)
                    pos = current
                    current = came_from[current]
                # path.append(start)
                # path.reverse()
                if pos:
                    self[pos].mark_unsafe(ship)
                    return ship.position.directional(pos)
                else:
                    return Direction.Still

            for next in self[current].position.neighbors():
                if blocked_position and next == blocked_position:
                    continue
                # if game_map[next].is_occupied:
                # if next in intended_moves:
                #     continue
                if self[next].ship is not None:
                    if ship != self[next].ship:
                        continue

                new_cost = cost_so_far[current] + self[next].cost
                if next not in cost_so_far or new_cost < cost_so_far[next]:
                    cost_so_far[next] = new_cost
                    priority = new_cost + self.heuristic(goal, next)
                    frontier.put(next, priority)
                    came_from[next] = current

        # Could not find a path, fallback to naive_navigate
        # logging.warning("AStar navigate failed, falling back to naive_navigate")
        return self.naive_navigate(ship, goal, exclude_dir)

    @staticmethod
    def _generate():
        """
        Creates a map object from the input given by the game engine
        :return: The map object
        """
        map_width, map_height = map(int, read_input().split())
        game_map = [[None for _ in range(map_width)]
                    for _ in range(map_height)]
        for y_position in range(map_height):
            cells = read_input().split()
            for x_position in range(map_width):
                game_map[y_position][x_position] = MapCell(Position(x_position, y_position),
                                                           int(cells[x_position]))
        return GameMap(game_map, map_width, map_height)

    def _update(self):
        """
        Updates this map object from the input given by the game engine
        :return: nothing
        """
        self._average = None
        # Mark cells as safe for navigation (will re-mark unsafe cells
        # later)
        for y in range(self.height):
            for x in range(self.width):
                self[Position(x, y)].ship = None
        diff = 0
        for _ in range(int(read_input())):
            cell_x, cell_y, cell_energy = map(int, read_input().split())
            cell = self[Position(cell_x, cell_y)]
            diff += cell.halite_amount - cell_energy
            cell.halite_amount = cell_energy
            cell.update_cost()
        if diff > 0:
            self._total -= diff
