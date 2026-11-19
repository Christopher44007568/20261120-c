"""Compare how L-system rule parameters change branch distribution/density."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proctree.plant import LSystemParams, generate

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts")
DEPTH = 5


def main() -> int:
    variants = [
        LSystemParams("narrow_12deg", "F", {"F": "F[+F]F[-F][F]"}, 12.0, 1.0),
        LSystemParams("medium_22deg", "F", {"F": "F[+F]F[-F][F]"}, 22.0, 1.0),
        LSystemParams("wide_38deg", "F", {"F": "F[+F]F[-F][F]"}, 38.0, 1.0),
        LSystemParams(
            "dense_rule",
            "F",
            {"F": "FF[+F][-F][+F][-F]"},
            22.0,
            0.7,
        ),
    ]
    rows = []
    for params in variants:
        tree = generate(params, DEPTH)
        summary = tree.summary()
        width, height = tree.bbox_size
        rows.append(
            {
                "name": params.name,
                "depth": DEPTH,
                "angle_deg": params.angle_deg,
                "rule": params.rules["F"],
                "segment_instances": len(tree.segments),
                "leaf_instances": len(tree.leaves),
                "bbox_width": round(width, 3),
                "bbox_height": round(height, 3),
                "aspect_w_over_h": round(width / height, 4),
                "elapsed_ms": round(tree.elapsed_ms, 3),
            }
        )

    angles = [row for row in rows if row["rule"] == "F[+F]F[-F][F]"]
    widths = [row["bbox_width"] for row in angles]
    angle_effect = {
        "check": "wider branching angle widens the canopy",
        "widths_by_angle": {str(row["angle_deg"]): row["bbox_width"] for row in angles},
        "monotonic_width": widths == sorted(widths),
    }
    medium = next(row for row in rows if row["name"] == "medium_22deg")
    dense = next(row for row in rows if row["name"] == "dense_rule")
    density_effect = {
        "check": "denser production rule yields more branch instances",
        "medium_segments": medium["segment_instances"],
        "dense_segments": dense["segment_instances"],
        "denser": dense["segment_instances"] > medium["segment_instances"],
    }
    payload = {"rows": rows, "angle_effect": angle_effect, "density_effect": density_effect}
    with open(os.path.join(OUT_DIR, "rule_sweep.json"), "w") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
