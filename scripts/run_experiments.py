"""Drive L-system generation experiments across recursion depths and rules."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proctree.plant import LSystemParams, generate
from proctree.svg import render_comparison_svg, render_tree_svg

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts")

PARAM_SETS = [
    LSystemParams(
        name="upright_tree",
        axiom="F",
        rules={"F": "F[+F]F[-F][F]"},
        angle_deg=20.0,
        step=1.0,
    ),
    LSystemParams(
        name="spreading_bush",
        axiom="X",
        rules={"X": "F+[[XL]-XL]-F[-FXL]+L", "F": "FF"},
        angle_deg=28.0,
        step=0.85,
    ),
]

DEPTHS = (3, 4, 5, 6)


def validate_naturalness(summaries: list[dict]) -> list[str]:
    """Heuristic checks that deeper recursion yields a natural growing tree."""
    issues: list[str] = []
    for prev, cur in zip(summaries, summaries[1:]):
        if cur["segment_instances"] <= prev["segment_instances"]:
            issues.append(f"depth {cur['depth']} did not add segments")
        if cur["bbox"]["height"] < prev["bbox"]["height"]:
            issues.append(f"depth {cur['depth']} shrank in height")
        if cur["max_level"] < prev["max_level"]:
            issues.append(f"depth {cur['depth']} lost hierarchy levels")
    deepest = summaries[-1]
    if deepest["bbox"]["width"] <= 0 or deepest["bbox"]["height"] <= 0:
        issues.append("deepest tree has a degenerate bounding box")
    return issues


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    report: dict[str, object] = {"depth_experiments": [], "naturalness": {}, "rule_params": []}

    for params in PARAM_SETS:
        trees = []
        summaries = []
        for depth in DEPTHS:
            tree = generate(params, depth)
            trees.append(tree)
            summaries.append(tree.summary())
            with open(os.path.join(OUT_DIR, f"{params.name}_d{depth}.svg"), "w") as fh:
                fh.write(render_tree_svg(tree))
        with open(os.path.join(OUT_DIR, f"{params.name}_comparison.svg"), "w") as fh:
            fh.write(render_comparison_svg(trees))
        issues = validate_naturalness(summaries)
        report["depth_experiments"].extend(summaries)
        report["naturalness"][params.name] = {"passed": not issues, "issues": issues}
        report["rule_params"].append(
            {
                "name": params.name,
                "axiom": params.axiom,
                "rules": params.rules,
                "angle_deg": params.angle_deg,
                "step": params.step,
                "leaf_length": params.leaf_length,
            }
        )

    with open(os.path.join(OUT_DIR, "plant_report.json"), "w") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
