#!/usr/bin/env python3
"""Entry point: run the full Early-Z / overdraw experiment matrix."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from earlyz_overdraw.benchmark import RunResult, benefit_table, run_matrix
from earlyz_overdraw.experiments import EXPERIMENTS, boundary_parameter_rows
from earlyz_overdraw.report import (
    build_markdown_report,
    metrics_row,
    write_json,
)


def _find(results: list[RunResult], pipeline: str,
          order: str) -> RunResult:
    return next(result for result in results
                if result.pipeline == pipeline and result.draw_order == order)


def build_conclusions(all_results: dict[str, list[RunResult]]) -> list[str]:
    conclusions: list[str] = []
    e1 = all_results["E1_heavy_opaque"]
    base = _find(e1, "forward_no_early_z", "back_to_front").metrics
    prepass = _find(e1, "z_prepass", "front_to_back").metrics
    early = _find(e1, "forward_early_z", "front_to_back").metrics
    conclusions.append(
        f"大量重叠全不透明场景：基线重复绘制 {base.redundant_shaded} 像素，"
        f"早Z(前→后) 降至 {early.redundant_shaded}，"
        f"Z-Prepass 降至 {prepass.redundant_shaded}，"
        f"每覆盖像素平均着色次数由 "
        f"{base.shader_invocations / base.covered_pixels:.2f} 降到 "
        f"{prepass.shader_invocations / prepass.covered_pixels:.2f}。")

    f2b = _find(e1, "forward_early_z", "front_to_back").metrics
    b2f = _find(e1, "forward_early_z", "back_to_front").metrics
    conclusions.append(
        f"早Z收益依赖绘制顺序：前→后深度拒绝 {f2b.depth_rejects} 次，"
        f"后→前仅 {b2f.depth_rejects} 次；不透明物体前→后提交可最大化跳过。")

    e6 = all_results["E6_heavy_100pct_transparent"]
    transparent_base = _find(
        e6, "forward_no_early_z", "back_to_front").metrics
    transparent_prepass = _find(e6, "z_prepass", "back_to_front").metrics
    conclusions.append(
        "透明边界：混合透明片元不写深度，早Z无法剔除被遮挡的透明片元，"
        f"全透明场景重复绘制仍为 {transparent_base.redundant_shaded}；"
        f"Z-Prepass 因额外通道反而增加 "
        f"{transparent_prepass.model_cycles - transparent_base.model_cycles:,} "
        "模型周期，收益失效。")

    for case_id in ("E3_heavy_25pct_transparent",
                    "E4_heavy_50pct_transparent",
                    "E5_heavy_75pct_transparent"):
        scene_results = all_results[case_id]
        scene_base = _find(
            scene_results, "forward_no_early_z", "front_to_back").metrics
        scene_pre = _find(
            scene_results, "z_prepass", "front_to_back").metrics
        conclusions.append(
            f"{case_id}：Z-Prepass 模型周期相对基线变化 "
            f"{scene_pre.model_cycles - scene_base.model_cycles:,}，"
            "混合透明比例越高，可被预通道消除的重复绘制越少。")

    e7 = all_results["E7_heavy_100pct_alpha_test"]
    alpha_prepass = _find(e7, "z_prepass", "front_to_back").metrics
    conclusions.append(
        f"边界反例：alpha-test 裁剪后存活片元仍写深度，"
        f"Z-Prepass 重复绘制可降到 {alpha_prepass.redundant_shaded}，"
        "说明失效边界是“不写深度的混合透明”，而非带透明度的材质本身。")
    return conclusions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="artifacts/results",
                        help="output directory for report and data files")
    parser.add_argument("--repeats", type=int, default=5,
                        help="wall-clock timing repetitions (minimum kept)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results: dict[str, list[RunResult]] = {}
    sections: list[tuple[str, list[RunResult]]] = []
    benefit_by_scene: dict[str, list[dict[str, float | str]]] = {}
    flat_rows: list[dict[str, float | int | str]] = []
    flat_benefits: list[dict[str, float | int | str]] = []

    for spec in EXPERIMENTS:
        scene = spec.build()
        results = run_matrix(scene, repeats=args.repeats)
        all_results[spec.case_id] = results
        sections.append((f"{spec.case_id} — {spec.description}", results))
        benefits = benefit_table(results)
        benefit_by_scene[spec.case_id] = benefits
        for result in results:
            row = metrics_row(result)
            row["scene"] = spec.case_id
            flat_rows.append(row)
        for row in benefits:
            enriched = {"scene": spec.case_id, **row}
            flat_benefits.append(enriched)

    with (out_dir / "metrics.csv").open("w", newline="",
                                        encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0].keys()))
        writer.writeheader()
        writer.writerows(flat_rows)

    with (out_dir / "benefits.csv").open("w", newline="",
                                         encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(flat_benefits[0].keys()))
        writer.writeheader()
        writer.writerows(flat_benefits)

    write_json(out_dir / "boundary_parameters.json", boundary_parameter_rows())
    report = build_markdown_report(
        boundary_parameter_rows(), sections, benefit_by_scene,
        build_conclusions(all_results))
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print(f"report written to {out_dir / 'report.md'}")


if __name__ == "__main__":
    main()
