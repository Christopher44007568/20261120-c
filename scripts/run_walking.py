#!/usr/bin/env python3
"""Run the procedural gait sweep, contact checks, plots, and animations."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from walker.analysis import (  # noqa: E402
    compare_scenarios,
    continuity_metrics,
    sweep_slopes,
    write_json,
    write_rows_csv,
)
from walker.gait import GaitParams, simulate_scenario  # noqa: E402
from walker.visualize import (  # noqa: E402
    animate_scenario,
    plot_foot_trajectory,
    plot_gait_phases,
    plot_joint_angles,
    plot_stride_vs_slope,
)


def main() -> None:
    out = ROOT / "outputs" / "gait"
    out.mkdir(parents=True, exist_ok=True)
    params = GaitParams()

    slopes = list(range(-25, 26))
    sweep = sweep_slopes(slopes, params=params, sample_hz=180.0)
    continuity = continuity_metrics(sweep)
    write_rows_csv(out / "stride_vs_slope.csv", sweep)
    plot_stride_vs_slope(sweep, out / "stride_vs_slope.png", continuity)

    comparison = compare_scenarios((-20.0, 0.0, 20.0), params=params, sample_hz=240.0)
    write_rows_csv(out / "scenario_comparison.csv", comparison["comparison"])
    plot_joint_angles(comparison["results"], out / "joint_angles.png")
    plot_foot_trajectory(comparison["results"], out / "foot_trajectory.png")
    plot_gait_phases(comparison["results"], out / "gait_phases.png")

    frame_rows: list[dict] = []
    for slope_key, result in comparison["results"].items():
        slope_name = f"{float(slope_key):+.0f}".replace("+", "plus").replace("-", "minus")
        write_rows_csv(out / f"frames_{slope_name}_deg.csv", result.rows)
        frame_rows.extend({"slope_deg": result.slope_deg, **row} for row in result.rows)
    write_rows_csv(out / "frames_all.csv", frame_rows)

    for slope, name in ((20.0, "uphill_plus20"), (-20.0, "downhill_minus20"), (0.0, "level")):
        animation_result = simulate_scenario(
            slope, params=params, duration_cycles=2.0, sample_hz=30.0
        )
        animate_scenario(animation_result, out / f"walk_{name}.gif", fps=30)

    max_contact = max(row["contact_max_abs_m"] for row in sweep)
    max_slip = max(row["foot_slip_max_m"] for row in sweep)
    reach_max = max(row["reach_ratio_max"] for row in sweep)
    all_reached = all(row["all_reached"] for row in sweep)
    payload = {
        "params": {
            "cycle_s": params.cycle_s,
            "stance_fraction": params.stance_fraction,
            "base_stride_m": params.base_stride_m,
            "hip_height_m": params.hip_height_m,
            "thigh_m": params.leg.thigh_m,
            "shank_m": params.leg.shank_m,
            "foot_length_m": params.leg.foot_length_m,
            "ankle_height_m": params.leg.ankle_height_m,
            "swing_clearance_m": params.swing_clearance_m,
            "uphill_stride_coeff": params.uphill_stride_coeff,
            "downhill_stride_coeff": params.downhill_stride_coeff,
            "slope_reference_deg": params.slope_reference_deg,
        },
        "gait_cycle": {
            "cycle_s": params.cycle_s,
            "stance_s": params.stance_fraction * params.cycle_s,
            "swing_s": (1.0 - params.stance_fraction) * params.cycle_s,
            "double_support_s": (2.0 * params.stance_fraction - 1.0) * params.cycle_s,
            "cadence_steps_per_min": 120.0 / params.cycle_s,
        },
        "sweep_checks": {
            "slopes_tested_deg": [min(slopes), max(slopes)],
            "max_contact_abs_mm": max_contact * 1000.0,
            "contact_tolerance_mm": 1.0,
            "contact_pass": bool(max_contact < 0.001),
            "max_foot_slip_mm": max_slip * 1000.0,
            "foot_slip_pass": bool(max_slip < 1e-4),
            "reach_ratio_max": reach_max,
            "all_reached": bool(all_reached),
        },
        "continuity": continuity,
        "comparison": comparison["comparison"],
        "comparison_checks": comparison["checks"],
        "stride_vs_slope": sweep,
    }
    write_json(out / "gait_summary.json", payload)

    print("slope  stride  speed  contact_max  slip     reach")
    for row in sweep:
        if int(row["slope_deg"]) % 5 == 0:
            print(
                f"{row['slope_deg']:+5.0f}  {row['stride_m']:.4f}  "
                f"{row['speed_mps']:.3f}  {row['contact_max_abs_m']*1000:9.3e} mm  "
                f"{row['foot_slip_max_m']*1000:7.3e} mm  {row['reach_ratio_max']:.3f}"
            )
    print(f"continuity: {continuity}")
    print(f"contact/stride checks: {payload['sweep_checks']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
