"""Parameter sweeps quantifying how layout parameters drive density."""

import random

from .geometry import Board, Obstacle, Pin
from .router import Router


def _random_board(width, height, layers, obstacle_ratio, net_count, rng):
    target = int(width * height * obstacle_ratio)
    obstacles, used = [], set()
    while len(used) < target:
        ow = rng.randint(1, max(1, width // 6))
        oh = rng.randint(1, max(1, height // 6))
        x0 = rng.randint(0, width - ow)
        y0 = rng.randint(0, height - oh)
        layer = rng.randrange(layers)
        cells = {(x, y) for x in range(x0, x0 + ow)
                 for y in range(y0, y0 + oh)}
        if cells & used:
            continue
        obstacles.append(Obstacle(layer, x0, y0, x0 + ow, y0 + oh))
        used |= cells
    board = Board(width, height, layers, obstacles)
    pins, occupied = [], set(used)
    net = 0
    while net < net_count:
        chosen = []
        for layer in (0, layers - 1):
            for _ in range(100):
                cell = (rng.randrange(width), rng.randrange(height))
                if cell not in occupied and not board.blocked(layer, cell):
                    chosen.append(Pin(f"n{net}", layer, *cell))
                    break
            else:
                chosen = []
                break
        if len(chosen) == 2:
            pins.extend(chosen)
            occupied.add(chosen[0].cell)
            occupied.add(chosen[1].cell)
            net += 1
    return board, pins


def run_sweep(seeds=(1, 2, 3), widths=(16, 24),
              obstacle_ratios=(0.05, 0.15, 0.25),
              net_counts=(4, 8, 12), layers=2):
    rows = []
    for width in widths:
        for ratio in obstacle_ratios:
            for net_count in net_counts:
                for seed in seeds:
                    rng = random.Random(seed * 7919 + width)
                    board, pins = _random_board(
                        width, width, layers, ratio, net_count, rng)
                    result = Router(board, pins).route()
                    capacity = width * width * layers
                    rows.append({
                        "width": width,
                        "obstacle_ratio": ratio,
                        "net_count": net_count,
                        "seed": seed,
                        "routed": result.routed,
                        "crossings": result.crossings,
                        "vias": result.via_count,
                        "planar_length": result.planar_length,
                        "cell_density": round(
                            result.planar_length / capacity, 4),
                        "obstacle_density": round(
                            ratio, 4),
                    })
    return rows


def aggregate(rows):
    groups = {}
    for row in rows:
        key = (row["width"], row["obstacle_ratio"], row["net_count"])
        groups.setdefault(key, []).append(row)
    summary = []
    for key, items in sorted(groups.items()):
        n = len(items)
        summary.append({
            "width": key[0],
            "obstacle_ratio": key[1],
            "net_count": key[2],
            "mean_crossings": round(
                sum(i["crossings"] for i in items) / n, 2),
            "mean_vias": round(sum(i["vias"] for i in items) / n, 2),
            "mean_cell_density": round(
                sum(i["cell_density"] for i in items) / n, 4),
            "routed_fraction": round(
                sum(1 for i in items if i["routed"]) / n, 2),
        })
    return summary
