"""L-system experiments: recursion depth sweep and rule-parameter comparison."""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from lsystem import LSystemConfig, build_tree
from tree_render import render_tree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "artifacts")


def tree_stats(tree: dict) -> dict:
    segments = tree["segments"]
    leaves = tree["leaves"]
    ends = np.array([s[1] for s in segments])
    heights = ends[:, 2]
    widths = np.array([s[2] for s in segments])
    span_x = float(np.ptp(ends[:, 0])) if len(ends) else 0.0
    span_y = float(np.ptp(ends[:, 1])) if len(ends) else 0.0
    height = float(heights.max())
    radial = np.hypot(ends[:, 0], ends[:, 1])
    canopy_radius = float(radial.max()) if len(ends) else 0.0
    canopy_area = np.pi * max(canopy_radius, 0.5) ** 2
    depth_bins = np.clip((widths / max(widths.max(), 1e-9) * 4).astype(int), 0, 3)
    branch_by_level = [int(np.sum(depth_bins == k)) for k in range(4)]
    return {
        "branch_segments": len(segments),
        "leaf_tips": int(leaves.shape[0]),
        "sentence_length": tree["sentence_len"],
        "height": round(float(heights.max()), 3),
        "horizontal_span": round(span_x, 3),
        "canopy_footprint": round(canopy_area, 3),
        "canopy_volume": round(canopy_area * max(height, 1e-9), 3),
        "mean_branch_width": round(float(widths.mean()), 4),
        "branches_per_width_level": branch_by_level,
    }


def main() -> None:
    os.makedirs(os.path.join(OUT, "renders", "trees"), exist_ok=True)
    report: dict = {"depth_sweep": [], "rule_comparison": []}

    # 1. Recursion depth sweep with one fixed rule set.
    depth_rules = {"F": "FF+[+F-F-F]-[-F+F+F]"}
    for depth in range(1, 5):
        cfg = LSystemConfig(axiom="F", rules=depth_rules, depth=depth,
                            angle_deg=22.5, step=0.55, width=1.4, seed=42)
        tree = build_tree(cfg)
        img, metrics = render_tree(tree)
        fname = f"renders/trees/tree_depth{depth}.png"
        img.save(os.path.join(OUT, fname))
        entry = {"depth": depth, **tree_stats(tree), "image": fname}
        report["depth_sweep"].append(entry)
        print(json.dumps(entry, ensure_ascii=False))

    # 2. Same depth, different rule parameters -> distribution and density.
    rule_sets = {
        "dense_bushy": {
            "rules": {"F": "FF[+F][-F][&F][^F]"},
            "angle_deg": 28.0,
        },
        "balanced": {
            "rules": {"F": "FF+[+F-F-F]-[-F+F+F]"},
            "angle_deg": 22.5,
        },
        "tall_sparse": {
            "rules": {"F": "F[+F]F[-F][F]"},
            "angle_deg": 16.0,
        },
    }
    for name, spec in rule_sets.items():
        cfg = LSystemConfig(axiom="F", rules=spec["rules"], depth=4,
                            angle_deg=spec["angle_deg"], step=0.55,
                            width=1.4, seed=42)
        tree = build_tree(cfg)
        img, _ = render_tree(tree)
        fname = f"renders/trees/tree_rule_{name}.png"
        img.save(os.path.join(OUT, fname))
        stats = tree_stats(tree)
        density = stats["leaf_tips"] / max(stats["canopy_volume"], 1e-9)
        entry = {
            "name": name,
            "angle_deg": spec["angle_deg"],
            "rule": next(iter(spec["rules"].values())),
            **stats,
            "leaf_density": round(float(density), 5),
            "image": fname,
        }
        report["rule_comparison"].append(entry)
        print(json.dumps(entry, ensure_ascii=False))

    with open(os.path.join(OUT, "tree_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print("report -> artifacts/tree_report.json")


if __name__ == "__main__":
    main()
