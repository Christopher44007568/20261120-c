"""Multi-layer grid router: A* with via cost, obstacle avoidance, and
per-net via / crossing statistics."""
import heapq
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

W, H, LAYERS = 30, 30, 2
VIA_COST = 5

# blocked rectangles: (layer, x0, y0, x1, y1) inclusive
OBSTACLES = [
    (0, 8, 8, 12, 12),
    (0, 18, 15, 23, 19),
    (1, 13, 3, 16, 7),
    (1, 4, 20, 9, 24),
    (0, 3, 14, 5, 22),
]

# nets: ((layer, x, y) src, (layer, x, y) dst)
NETS = [
    ((0, 1, 1), (0, 28, 28)),
    ((0, 28, 1), (0, 1, 28)),
    ((1, 2, 15), (1, 27, 10)),
    ((0, 10, 2), (1, 25, 25)),
    ((1, 15, 28), (0, 20, 5)),
    ((0, 6, 27), (0, 14, 16)),
]


def blocked_cells():
    blocked = set()
    for lay, x0, y0, x1, y1 in OBSTACLES:
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                blocked.add((lay, x, y))
    return blocked


def neighbors(cell):
    lay, x, y = cell
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < W and 0 <= ny < H:
            yield (lay, nx, ny), 1
    if LAYERS > 1:
        yield (1 - lay, x, y), VIA_COST


def route(src, dst, occupied):
    openq = [(0, 0, src, None)]
    came, cost = {}, {src: 0}
    while openq:
        _, g, cur, parent = heapq.heappop(openq)
        if cur in came:
            continue
        came[cur] = parent
        if cur == dst:
            path = []
            while cur is not None:
                path.append(cur)
                cur = came[cur]
            return path[::-1]
        for nxt, w in neighbors(cur):
            if nxt in occupied and nxt != dst:
                continue
            ng = g + w
            if ng < cost.get(nxt, 1 << 30):
                cost[nxt] = ng
                h = abs(nxt[1] - dst[1]) + abs(nxt[2] - dst[2])
                heapq.heappush(openq, (ng + h, ng, nxt, cur))
    return None


def draw_layout(paths, out_png):
    fig, axes = plt.subplots(1, LAYERS, figsize=(11, 5.2), dpi=100)
    colors = plt.cm.tab10.colors
    for lay in range(LAYERS):
        ax = axes[lay]
        ax.set_title(f"layer {lay}")
        ax.set_xlim(-0.5, W - 0.5)
        ax.set_ylim(-0.5, H - 0.5)
        ax.set_aspect("equal")
        for olay, x0, y0, x1, y1 in OBSTACLES:
            if olay == lay:
                ax.add_patch(mpatches.Rectangle(
                    (x0 - 0.5, y0 - 0.5), x1 - x0 + 1, y1 - y0 + 1,
                    color="gray", alpha=0.6))
        for i, path in enumerate(paths):
            xs = [c[1] for c in path if c[0] == lay]
            ys = [c[2] for c in path if c[0] == lay]
            seg_x, seg_y = [], []
            for a, b in zip(path, path[1:]):
                if a[0] == lay and b[0] == lay:
                    ax.plot([a[1], b[1]], [a[2], b[2]],
                            color=colors[i % 10], lw=2)
            for a, b in zip(path, path[1:]):
                if a[0] != b[0]:
                    ax.plot(a[1], a[2], "o", color=colors[i % 10],
                            ms=7, mfc="none", mew=2)
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("routes (circles = vias, gray = obstacles)")
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def main():
    blocked = blocked_cells()
    occupied = set(blocked)
    owner = {}
    report = {"grid": [W, H, LAYERS], "via_cost": VIA_COST, "nets": []}
    total_vias = 0
    paths = []
    for i, (src, dst) in enumerate(NETS):
        path = route(src, dst, occupied)
        if path is None:
            report["nets"].append({"net": i, "status": "failed"})
            print(f"net {i}: FAILED")
            continue
        vias = sum(1 for a, b in zip(path, path[1:]) if a[0] != b[0])
        total_vias += vias
        hits_obstacle = any(c in blocked for c in path)
        for c in path:
            owner.setdefault(c, i)
        occupied.update(path)
        paths.append(path)
        report["nets"].append({"net": i, "status": "ok", "length": len(path),
                               "vias": vias, "hits_obstacle": hits_obstacle})
        print(f"net {i}: len={len(path)} vias={vias} "
              f"hits_obstacle={hits_obstacle}")

    # crossing check: any cell claimed by two different nets
    seen = {}
    cross_cells = 0
    for c, n in owner.items():
        if c in seen and seen[c] != n:
            cross_cells += 1
        seen[c] = n
    report["total_vias"] = total_vias
    report["crossings"] = cross_cells
    report["obstacle_violations"] = sum(
        1 for n in report["nets"] if n.get("hits_obstacle"))
    print(f"total vias={total_vias} crossings={cross_cells} "
          f"obstacle_violations={report['obstacle_violations']}")
    out = Path("artifacts/routing")
    out.mkdir(parents=True, exist_ok=True)
    (out / "routing_report.json").write_text(json.dumps(report, indent=2))
    draw_layout(paths, out / "layout.png")
    print(f"wrote {out}/routing_report.json and layout.png")


if __name__ == "__main__":
    main()
