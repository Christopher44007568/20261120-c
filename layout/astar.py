"""A* search for layer-aware orthogonal paths on a grid board."""

import heapq

VIA_COST = 5.0
OCCUPIED_COST = 8.0
HOTSPOT_COST = 20.0


def heuristic(state, goal):
    (layer_a, (xa, ya)), (layer_b, (xb, yb)) = state, goal
    planar = abs(xa - xb) + abs(ya - yb)
    return planar + VIA_COST * abs(layer_a - layer_b)


def astar(board, start, goal, reserved, occupancy, hotspots=None):
    """Return list of (layer, cell) states from start to goal, or None.

    reserved  : hard-blocked (layer, cell) states (other nets' pins).
    occupancy: soft-cost map (layer, cell) -> extra entry cost.
    hotspots : conflict states weighted extra strongly during rip-up.
    """
    hotspots = hotspots or {}
    if start == goal:
        return [start]
    open_heap = [(heuristic(start, goal), 0, start)]
    best_g = {start: 0.0}
    came_from = {}
    counter = 1

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path
        layer, cell = current
        for nxt in board.neighbors(layer, cell):
            if nxt in reserved:
                continue
            step_cost = (1.0
                         + occupancy.get(nxt, 0.0) * OCCUPIED_COST
                         + hotspots.get(nxt, 0.0) * HOTSPOT_COST)
            _relax(nxt, step_cost, current, goal, open_heap, best_g,
                   came_from, counter)
            counter += 1
        for nxt_layer in (layer - 1, layer + 1):
            nxt = (nxt_layer, cell)
            if not board.in_bounds(nxt_layer, cell):
                continue
            if board.blocked(nxt_layer, cell) or nxt in reserved:
                continue
            _relax(nxt, VIA_COST, current, goal, open_heap, best_g,
                   came_from, counter)
            counter += 1
    return None


def _relax(nxt, step_cost, current, goal, open_heap, best_g, came_from,
           counter):
    new_g = best_g[current] + step_cost
    if new_g < best_g.get(nxt, float("inf")):
        best_g[nxt] = new_g
        came_from[nxt] = current
        f = new_g + heuristic(nxt, goal)
        heapq.heappush(open_heap, (f, counter, nxt))
