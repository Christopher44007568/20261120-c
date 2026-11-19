"""运行所有户型的布局求解，输出面积/碰撞/连通性统计与参数影响分析。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from indoor_layout.apartments import build_apartments, door_links
from indoor_layout.solver import SolverParams, solve_room
from indoor_layout.viz import room_svg

OUT = ROOT / "artifacts"


def solve_plan(rooms, params: SolverParams):
    return [solve_room(room, params) for room in rooms]


def print_plan_report(plan_name: str, rooms, solutions) -> dict:
    print(f"\n=== 户型：{plan_name} ===")
    print(f"{'房间':<8}{'面积m²':>8}{'家具数':>7}{'碰撞数':>7}"
          f"{'重叠m²':>9}{'走道连通':>10}{'可行':>6}{'尝试':>6}{'耗时ms':>9}")
    total_area = total_collisions = total_furniture = 0
    all_connected = True
    all_feasible = True
    rows = []
    for room, sol in zip(rooms, solutions):
        print(
            f"{room.name:<8}{room.area:>8.2f}{len(room.furniture):>7d}"
            f"{sol.collisions:>7d}{sol.overlap_area:>9.3f}"
            f"{('是' if sol.connected else '否'):>10}"
            f"{('是' if sol.feasible else '否'):>6}"
            f"{sol.attempts:>6d}{sol.elapsed_ms:>9.2f}"
        )
        total_area += room.area
        total_collisions += sol.collisions
        total_furniture += len(room.furniture)
        all_connected &= sol.connected
        all_feasible &= sol.feasible
        rows.append(
            {
                "room": room.name,
                "area_m2": round(room.area, 2),
                "furniture": len(room.furniture),
                "collisions": sol.collisions,
                "overlap_m2": round(sol.overlap_area, 3),
                "connected": sol.connected,
                "feasible": sol.feasible,
                "reachable_cells": sol.reachable_cells,
                "free_cells": sol.free_cells,
                "attempts": sol.attempts,
                "elapsed_ms": round(sol.elapsed_ms, 2),
                "note": sol.note,
            }
        )
    links = door_links(rooms)
    print(
        f"合计：面积 {total_area:.2f} m²，家具 {total_furniture} 件，"
        f"碰撞 {total_collisions}，房间间门连接 {len(links)} 条，"
        f"全部走道连通={all_connected}，户型可行={all_feasible}"
    )
    return {
        "plan": plan_name,
        "total_area_m2": round(total_area, 2),
        "total_furniture": total_furniture,
        "total_collisions": total_collisions,
        "all_connected": all_connected,
        "feasible": all_feasible,
        "door_links": [list(link) for link in links],
        "rooms": rows,
    }


def parameter_sweep(rooms) -> list[dict]:
    print("\n=== 参数影响分析（以首个房间为样本，rng 种子固定）===")
    base = SolverParams()
    room = rooms[0]
    variants = [
        ("默认参数", base),
        ("走道宽度 0.4m", SolverParams(walkway_width=0.4)),
        ("走道宽度 0.9m", SolverParams(walkway_width=0.9)),
        ("门净空 1.2m", SolverParams(door_clearance=1.2)),
        ("窗净空 1.0m", SolverParams(window_clearance=1.0)),
        ("候选步长 0.5m(粗)", SolverParams(grid_step=0.5)),
        ("候选步长 0.1m(细)", SolverParams(grid_step=0.1)),
        ("重启 2 次", SolverParams(restarts=2)),
        ("重启 30 次", SolverParams(restarts=30)),
    ]
    print(f"{'参数变体':<18}{'碰撞':>5}{'连通':>6}{'可行':>6}"
          f"{'可达栅格':>9}{'尝试':>6}{'耗时ms':>9}")
    records = []
    for label, params in variants:
        sol = solve_room(room, params)
        print(
            f"{label:<18}{sol.collisions:>5d}{('是' if sol.connected else '否'):>6}"
            f"{('是' if sol.feasible else '否'):>6}{sol.reachable_cells:>9d}"
            f"{sol.attempts:>6d}{sol.elapsed_ms:>9.2f}"
        )
        records.append(
            {
                "variant": label,
                "collisions": sol.collisions,
                "connected": sol.connected,
                "feasible": sol.feasible,
                "reachable_cells": sol.reachable_cells,
                "attempts": sol.attempts,
                "elapsed_ms": round(sol.elapsed_ms, 2),
            }
        )
    return records


def main() -> None:
    OUT.mkdir(exist_ok=True)
    plans = build_apartments()
    params = SolverParams()
    report = {"params": params.__dict__, "plans": []}
    for plan_name, rooms in plans.items():
        solutions = solve_plan(rooms, params)
        plan_report = print_plan_report(plan_name, rooms, solutions)
        report["plans"].append(plan_report)
        for room, sol in zip(rooms, solutions):
            safe = f"{plan_name}_{room.name}".replace("/", "_")
            room_svg(room, sol, str(OUT / f"layout_{safe}.svg"))
    sweep_room = plans["一居室"]
    report["parameter_sweep"] = parameter_sweep(sweep_room)
    with open(OUT / "layout_report.json", "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(f"\n报告与 SVG 已写入 {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
