"""裁剪前后排列数、编译时间与首帧延迟对比基准。

A. 受控搜索实例：朴素/碰撞剪枝/全剪枝三种模式均完整枚举，
   对比节点数、叶子数、可行排列数与编译时间；
   另以“首解即停”模式测量首帧延迟。
B. 真实大房间：朴素枚举受节点上限保护（标记截断），
   裁剪模式首解即停，展示规模化下的首帧延迟下降。
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from indoor_layout.apartments import build_apartments, build_search_instances
from indoor_layout.culling import (
    naive_search,
    pruned_search,
    warm_greedy_first_frame,
)
from indoor_layout.room import Room
from indoor_layout.solver import SolverParams

OUT = ROOT / "artifacts"
TRIALS = 5
NODE_CAP = 200_000


def median(values: list[float]) -> float:
    return round(statistics.median(values), 3)


def full_enumeration_row(room: Room, params: SolverParams) -> dict:
    full = {"naive": [], "collision": [], "full": []}
    first = {"naive": [], "collision": [], "full": []}
    greedy = []
    for _ in range(TRIALS):
        full["naive"].append(naive_search(room, params, node_cap=10 ** 9))
        full["collision"].append(pruned_search(room, params, stop_at_first=False))
        full["full"].append(
            pruned_search(
                room, params, stop_at_first=False, early_connectivity=True
            )
        )
        first["naive"].append(naive_search(room, params, node_cap=10 ** 9))
        first["collision"].append(pruned_search(room, params))
        first["full"].append(
            pruned_search(room, params, early_connectivity=True)
        )
        greedy.append(warm_greedy_first_frame(room, params))
    n, c, f = full["naive"][0], full["collision"][0], full["full"][0]
    return {
        "room": room.name,
        "furniture": len(room.furniture),
        "candidate_space": n.candidate_space,
        "naive": {"nodes": n.nodes_visited, "leaves": n.leaves_evaluated,
                  "compile_ms": median([r.compile_ms for r in full["naive"]]),
                  "first_frame_ms": median([r.first_frame_ms for r in first["naive"]])},
        "collision_pruned": {
            "nodes": c.nodes_visited, "leaves": c.leaves_evaluated,
            "pruned_branches": c.pruned_branches,
            "compile_ms": median([r.compile_ms for r in full["collision"]]),
            "first_frame_ms": median([r.first_frame_ms for r in first["collision"]]),
        },
        "full_pruned": {
            "nodes": f.nodes_visited, "leaves": f.leaves_evaluated,
            "pruned_branches": f.pruned_branches,
            "compile_ms": median([r.compile_ms for r in full["full"]]),
            "first_frame_ms": median([r.first_frame_ms for r in first["full"]]),
        },
        "valid_arrangements": n.valid_arrangements,
        "greedy_first_frame_ms": median(greedy),
        "leaf_reduction_pct": round((1 - c.leaves_evaluated / n.leaves_evaluated) * 100, 1),
        "node_reduction_pct": round((1 - c.nodes_visited / n.nodes_visited) * 100, 1),
        "first_frame_reduction_pct": round(
            (1 - median([r.first_frame_ms for r in first["collision"]]) /
             median([r.first_frame_ms for r in first["naive"]])) * 100, 1
        ),
        "capped": False,
    }


def capped_row(room: Room, params: SolverParams) -> dict:
    pruned_runs, naive_runs = [], []
    for _ in range(TRIALS):
        pruned_runs.append(pruned_search(room, params))
        naive_runs.append(naive_search(room, params, node_cap=NODE_CAP))
    p, n = pruned_runs[0], naive_runs[0]
    return {
        "room": room.name,
        "furniture": len(room.furniture),
        "candidate_space": p.candidate_space,
        "naive_nodes_explored": n.nodes_visited,
        "naive_capped": n.capped,
        "node_cap": NODE_CAP,
        "pruned_nodes": p.nodes_visited,
        "pruned_branches": p.pruned_branches,
        "naive_first_frame_ms": median([r.first_frame_ms for r in naive_runs]),
        "pruned_first_frame_ms": median([r.first_frame_ms for r in pruned_runs]),
        "first_frame_reduction_pct": round(
            (1 - median([r.first_frame_ms for r in pruned_runs]) /
             max(1e-9, median([r.first_frame_ms for r in naive_runs]))) * 100, 1
        ),
        "pruned_compile_ms": median([r.compile_ms for r in pruned_runs]),
        "capped": True,
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    compact_params = SolverParams(grid_step=1.0, max_candidates=12, restarts=4)
    print("=== A. 完整枚举：排列数与编译时间（三种模式均跑完全部排列）===")
    print(f"{'房间':<10}{'排列空间':>10}{'朴素 节点/叶子':>15}"
          f"{'碰撞剪枝 节点/叶子':>18}{'全剪枝 节点/叶子':>17}"
          f"{'可行排列':>9}{'朴素ms':>10}{'碰撞ms':>10}{'全剪ms':>9}")
    full_rows = []
    for room in build_search_instances().values():
        row = full_enumeration_row(room, compact_params)
        full_rows.append(row)
        print(
            f"{row['room']:<10}{row['candidate_space']:>10d}"
            f"{str(row['naive']['nodes']) + '/' + str(row['naive']['leaves']):>15}"
            f"{str(row['collision_pruned']['nodes']) + '/' + str(row['collision_pruned']['leaves']):>18}"
            f"{str(row['full_pruned']['nodes']) + '/' + str(row['full_pruned']['leaves']):>17}"
            f"{row['valid_arrangements']:>9d}"
            f"{row['naive']['compile_ms']:>10.3f}"
            f"{row['collision_pruned']['compile_ms']:>10.3f}"
            f"{row['full_pruned']['compile_ms']:>9.3f}"
        )
    print("\n首帧延迟（首解即停，ms 中位数）：")
    print(f"{'房间':<10}{'朴素':>10}{'碰撞剪枝':>12}{'全剪枝':>10}"
          f"{'首帧下降%':>11}{'贪心参照':>10}")
    for row in full_rows:
        print(
            f"{row['room']:<10}{row['naive']['first_frame_ms']:>10.3f}"
            f"{row['collision_pruned']['first_frame_ms']:>12.3f}"
            f"{row['full_pruned']['first_frame_ms']:>10.3f}"
            f"{row['first_frame_reduction_pct']:>10.1f}%"
            f"{row['greedy_first_frame_ms']:>10.3f}"
        )

    scale_params = SolverParams(grid_step=0.5, max_candidates=400)
    rooms = build_apartments()["一居室"] + build_apartments()["紧凑开间"]
    print("\n=== B. 真实大房间（朴素截断于节点上限，裁剪首解即停）===")
    print(f"{'房间':<8}{'理论排列空间':>16}{'朴素已探节点':>13}{'裁剪节点':>9}"
          f"{'朴素首帧ms':>12}{'裁剪首帧ms':>12}{'首帧下降%':>10}")
    cap_rows = []
    for room in rooms:
        row = capped_row(room, scale_params)
        cap_rows.append(row)
        print(
            f"{row['room']:<8}{row['candidate_space']:>16d}"
            f"{row['naive_nodes_explored']:>13d}{row['pruned_nodes']:>9d}"
            f"{row['naive_first_frame_ms']:>12.3f}"
            f"{row['pruned_first_frame_ms']:>12.3f}"
            f"{row['first_frame_reduction_pct']:>9.1f}%"
        )

    with open(OUT / "culling_benchmark.json", "w", encoding="utf-8") as handle:
        json.dump(
            {"trials": TRIALS, "full_enumeration": full_rows,
             "capped_scaleup": cap_rows},
            handle, ensure_ascii=False, indent=2,
        )
    print(f"\n基准数据已写入 {OUT.relative_to(ROOT)}/culling_benchmark.json")


if __name__ == "__main__":
    main()
