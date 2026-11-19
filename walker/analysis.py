"""Aggregate metrics, CSV export, and slope/gait comparisons."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .gait import GaitParams, SimulationResult, simulate_scenario


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer, np.bool_)):
        return value.item()
    return value


def write_json(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), indent=2, ensure_ascii=False))


def write_rows_csv(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        raise ValueError("cannot write empty row set")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def sweep_slopes(
    slopes_deg: Iterable[float],
    params: GaitParams | None = None,
    sample_hz: float = 180.0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slope in slopes_deg:
        result = simulate_scenario(
            slope, params=params, duration_cycles=1.0, sample_hz=sample_hz
        )
        summary = result.summary
        rows.append(
            {
                "slope_deg": float(slope),
                "stride_m": summary["stride_m"],
                "step_m": summary["step_m"],
                "measured_stride_m": summary["measured_stride_m"],
                "speed_mps": summary["speed_mps"],
                "cycle_s": summary["cycle_s"],
                "contact_max_abs_m": summary["contact_max_abs_m"],
                "contact_rmse_m": summary["contact_rmse_m"],
                "foot_slip_max_m": summary["foot_slip_max_m"],
                "reach_ratio_max": summary["reach_ratio_max"],
                "all_reached": summary["all_reached"],
                "knee_flexion_max_deg": summary["left"]["knee_flexion_deg_max"],
                "hip_flexion_max_deg": summary["left"]["hip_flexion_deg_max"],
            }
        )
    return rows


def continuity_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: row["slope_deg"])
    slopes = np.array([row["slope_deg"] for row in ordered], dtype=float)
    strides = np.array([row["stride_m"] for row in ordered], dtype=float)
    measured = np.array([row["measured_stride_m"] for row in ordered], dtype=float)
    first_diff = np.diff(strides)
    second_diff = np.diff(strides, n=2)
    measured_first = np.diff(measured)
    up_mask = slopes > 1e-9
    down_mask = slopes < -1e-9
    up_monotonic = bool(np.all(np.diff(strides[up_mask]) < 0.0)) if up_mask.any() else True
    down_monotonic = (
        bool(np.all(np.diff(strides[down_mask]) > 0.0)) if down_mask.any() else True
    )
    return {
        "slope_min_deg": float(slopes.min()),
        "slope_max_deg": float(slopes.max()),
        "sample_count": int(slopes.size),
        "stride_at_zero_m": float(strides[np.argmin(np.abs(slopes))]),
        "stride_range_m": float(strides.max() - strides.min()),
        "max_adjacent_stride_jump_m": float(np.max(np.abs(first_diff)))
        if first_diff.size
        else 0.0,
        "max_second_difference_m": float(np.max(np.abs(second_diff)))
        if second_diff.size
        else 0.0,
        "measured_vs_model_max_error_m": float(np.max(np.abs(measured - strides))),
        "max_adjacent_measured_jump_m": float(np.max(np.abs(measured_first)))
        if measured_first.size
        else 0.0,
        "uphill_stride_monotone_decreasing": up_monotonic,
        "downhill_stride_monotone_decreasing_with_abs_slope": down_monotonic,
        "continuous": bool(
            (first_diff.size == 0 or np.max(np.abs(first_diff)) < 0.01)
            and (second_diff.size == 0 or np.max(np.abs(second_diff)) < 0.001)
        ),
    }


def compare_scenarios(
    slopes_deg: Iterable[float] = (-20.0, 0.0, 20.0),
    params: GaitParams | None = None,
    sample_hz: float = 240.0,
) -> dict[str, Any]:
    results: dict[str, SimulationResult] = {}
    comparison: list[dict[str, Any]] = []
    for slope in slopes_deg:
        result = simulate_scenario(
            slope, params=params, duration_cycles=2.0, sample_hz=sample_hz
        )
        results[str(float(slope))] = result
        summary = result.summary
        left = summary["left"]
        right = summary["right"]
        comparison.append(
            {
                "slope_deg": float(slope),
                "direction": "uphill"
                if slope > 0
                else ("downhill" if slope < 0 else "level"),
                "cycle_s": summary["cycle_s"],
                "stance_s": summary["stance_s"],
                "swing_s": summary["swing_s"],
                "stride_m": summary["stride_m"],
                "step_m": summary["step_m"],
                "speed_mps": summary["speed_mps"],
                "contact_max_abs_mm": summary["contact_max_abs_m"] * 1000.0,
                "contact_rmse_mm": summary["contact_rmse_m"] * 1000.0,
                "contact_penetration_mm": summary["contact_penetration_max_m"] * 1000.0,
                "contact_gap_mm": summary["contact_gap_max_m"] * 1000.0,
                "foot_slip_mm": summary["foot_slip_max_m"] * 1000.0,
                "swing_clearance_m": summary["swing_clearance_max_m"],
                "reach_ratio_max": summary["reach_ratio_max"],
                "all_reached": summary["all_reached"],
                "hip_rom_deg": left["hip_flexion_deg_rom"],
                "knee_rom_deg": left["knee_flexion_deg_rom"],
                "ankle_rom_deg": left["ankle_dorsiflexion_deg_rom"],
                "peak_knee_flexion_deg": left["peak_knee_flexion_deg"],
                "hip_min_deg": left["hip_flexion_deg_min"],
                "hip_max_deg": left["hip_flexion_deg_max"],
                "knee_min_deg": left["knee_flexion_deg_min"],
                "knee_max_deg": left["knee_flexion_deg_max"],
                "ankle_min_deg": left["ankle_dorsiflexion_deg_min"],
                "ankle_max_deg": left["ankle_dorsiflexion_deg_max"],
                "right_knee_rom_deg": right["knee_flexion_deg_rom"],
            }
        )

    all_contact = max(row["contact_max_abs_mm"] for row in comparison)
    all_slip = max(row["foot_slip_mm"] for row in comparison)
    by_slope = {row["slope_deg"]: row for row in comparison}
    up = max(by_slope)
    down = min(by_slope)
    return {
        "comparison": comparison,
        "results": results,
        "checks": {
            "contact_tolerance_mm": 1.0,
            "max_contact_error_mm": all_contact,
            "contact_pass": bool(all_contact < 1.0),
            "max_foot_slip_mm": all_slip,
            "foot_slip_pass": bool(all_slip < 0.01),
            "uphill_stride_m": by_slope[up]["stride_m"],
            "downhill_stride_m": by_slope[down]["stride_m"],
            "stride_reduction_uphill_pct": float(
                100.0
                * (1.0 - by_slope[up]["stride_m"] / by_slope[0.0]["stride_m"])
            )
            if 0.0 in by_slope
            else None,
            "stride_reduction_downhill_pct": float(
                100.0
                * (1.0 - by_slope[down]["stride_m"] / by_slope[0.0]["stride_m"])
            )
            if 0.0 in by_slope
            else None,
        },
    }
