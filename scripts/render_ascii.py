"""把全部户型的布局结果导出为 ASCII 平面图文本。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from indoor_layout.apartments import build_apartments
from indoor_layout.ascii_viz import render_room
from indoor_layout.solver import SolverParams, solve_room

OUT = ROOT / "artifacts" / "layout_ascii.txt"


def main() -> None:
    blocks = []
    for plan_name, rooms in build_apartments().items():
        blocks.append(f"########## {plan_name} ##########")
        for room in rooms:
            sol = solve_room(room, SolverParams())
            blocks.append(render_room(room, sol))
            blocks.append(
                f"碰撞={sol.collisions} 连通={sol.connected} 可行={sol.feasible} "
                f"备注={sol.note or '-'}"
            )
            blocks.append("")
    OUT.write_text("\n".join(blocks), encoding="utf-8")
    print(f"已写入 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
