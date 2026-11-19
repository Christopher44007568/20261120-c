"""Benchmark: dirty-flag vs naive world-matrix updates on deep cascades.

Scenario per frame: one node's local transform changes (typical animation
edit), then the world pass runs. We sweep hierarchy depth and report
matrix-update counts and traversal time for both strategies.
"""

import time

from scene_graph import (
    Node,
    UpdateStats,
    build_chain,
    count_nodes,
    mat_rotation_y,
    update_world_dirty,
    update_world_naive,
)

FRAMES = 200


def chain_node_at(root, depth):
    node = root
    for _ in range(depth):
        node = node.children[0]
    return node


def run_frames(root, edited, update_fn):
    stats = UpdateStats()
    start = time.perf_counter()
    for frame in range(FRAMES):
        edited.set_local(mat_rotation_y(0.01 * frame))
        update_fn(root, stats)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return stats, elapsed_ms


def bench_depth(depth, breadth=2, edit="leaf"):
    edit_depth = depth if edit == "leaf" else depth // 2

    root, _ = build_chain(depth, breadth)
    total = count_nodes(root)
    update_world_dirty(root, UpdateStats())  # warm the cache
    edited = chain_node_at(root, edit_depth)
    dirty_stats, dirty_ms = run_frames(root, edited, update_world_dirty)

    root2, _ = build_chain(depth, breadth)
    edited2 = chain_node_at(root2, edit_depth)
    naive_stats, naive_ms = run_frames(root2, edited2, update_world_naive)

    return {
        "depth": depth,
        "nodes": total,
        "edit": f"{edit}@d{edit_depth}",
        "naive_updates": naive_stats.matrix_updates,
        "dirty_updates": dirty_stats.matrix_updates,
        "naive_ms": naive_ms,
        "dirty_ms": dirty_ms,
    }


def fmt_row(r):
    saved = 100.0 * (1.0 - r["dirty_updates"] / r["naive_updates"])
    speedup = r["naive_ms"] / r["dirty_ms"] if r["dirty_ms"] > 0 else float("inf")
    return (
        f"{r['depth']:>5} {r['nodes']:>6} {r['edit']:>9} "
        f"{r['naive_updates']:>14} {r['dirty_updates']:>14} {saved:>8.1f}% "
        f"{r['naive_ms']:>10.2f} {r['dirty_ms']:>10.2f} {speedup:>8.2f}x"
    )


def main():
    header = (
        f"{'depth':>5} {'nodes':>6} {'edit':>9} "
        f"{'naive_updates':>14} {'dirty_updates':>14} {'saved':>9} "
        f"{'naive_ms':>10} {'dirty_ms':>10} {'speedup':>9}"
    )

    print(f"== Deep-cascade sweep, leaf edit per frame, {FRAMES} frames ==")
    print(header)
    leaf_rows = []
    for depth in (4, 8, 16, 32, 64, 128):
        r = bench_depth(depth, edit="leaf")
        leaf_rows.append(r)
        print(fmt_row(r))

    print()
    print(f"== Deep-cascade sweep, mid-chain edit per frame, {FRAMES} frames ==")
    print(header)
    mid_rows = []
    for depth in (4, 8, 16, 32, 64, 128):
        r = bench_depth(depth, edit="mid")
        mid_rows.append(r)
        print(fmt_row(r))

    print()
    deepest = leaf_rows[-1]
    print(
        "Deep cascade (depth={depth}, nodes={nodes}): dirty flags cut matrix "
        "updates from {naive} to {dirty} ({pct:.1f}% fewer), traversal "
        "{n:.2f}ms -> {d:.2f}ms.".format(
            depth=deepest["depth"],
            nodes=deepest["nodes"],
            naive=deepest["naive_updates"],
            dirty=deepest["dirty_updates"],
            pct=100.0 * (1.0 - deepest["dirty_updates"] / deepest["naive_updates"]),
            n=deepest["naive_ms"],
            d=deepest["dirty_ms"],
        )
    )


if __name__ == "__main__":
    main()
