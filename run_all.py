#!/usr/bin/env python3
"""Run all experiments and write the artifact bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bbh_geodesic.bbh_experiment import run_bbh_experiment, run_culling_experiment
from bbh_geodesic.geodesic_experiment import run_geodesic_experiment
from bbh_geodesic.render import (
    render_culling_chart,
    render_geodesic_chart,
    render_layer_volume_chart,
    render_running_bbh,
)
from bbh_geodesic.report import write_report

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="fewer animation frames")
    args = parser.parse_args()
    frame_count = 12 if args.quick else 48
    timing_repeats = 3 if args.quick else 12
    frame_stride = 2 if args.quick else 1
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print("[1/5] fitting and timing the skeletal AABB hierarchy")
    bbh = run_bbh_experiment(
        ARTIFACTS,
        frame_count=frame_count,
        timing_repeats=timing_repeats,
    )
    print("[2/5] benchmarking depth-limited frustum culling")
    culling = run_culling_experiment(ARTIFACTS, bbh, frame_stride=frame_stride)
    print("[3/5] solving obstacle-surface geodesic paths")
    geodesic = run_geodesic_experiment(ARTIFACTS)
    print("[4/5] rendering SVG figures")
    rig = bbh["rig"]
    bvh = bbh["bvh"]
    render_running_bbh(ARTIFACTS / "figure_running_bbh.svg", rig, bvh)
    render_culling_chart(
        ARTIFACTS / "figure_culling_depth.svg",
        culling["depths"],
        culling["validation"],
        frames=int(culling["frames"]),
        cameras=int(culling["cameras"]),
    )
    render_layer_volume_chart(
        ARTIFACTS / "figure_layer_volumes.svg",
        bbh["layers"],
    )
    render_geodesic_chart(
        ARTIFACTS / "figure_geodesic_path.svg",
        geodesic["curved_points"],
        geodesic["analytic_points"],
        geodesic["rows"],
        geodesic["checks"],
    )
    print("[5/5] writing report and combined metrics")
    report_path = write_report(ARTIFACTS, bbh, culling, geodesic, root_dir=ROOT)
    summary = {
        "configuration": {
            "frames": frame_count,
            "timing_repeats": timing_repeats,
            "culling_frame_stride": frame_stride,
        },
        "bbh": bbh["fit"],
        "layers": bbh["layers"],
        "culling": culling,
        "geodesic": geodesic["checks"],
    }
    (ARTIFACTS / "metrics.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    fit = bbh["fit"]
    print(
        f"done: {int(fit['frames'])} frames, containment "
        f"{float(fit['all_frames_fully_contained'])}, "
        f"box update {float(fit['box_update_ms_per_frame']):.3f} ms/frame"
    )
    print(
        "culling: "
        + " -> ".join(
            f"{float(row['culling_rate']) * 100:.1f}%" for row in culling["depths"]
        )
    )
    print(
        "geodesic: flat error "
        f"{float(geodesic['checks']['flat_relative_error']) * 100:.3f}%, "
        f"curved {float(geodesic['checks']['curved_fine_distance_m']):.6f} m"
    )
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
