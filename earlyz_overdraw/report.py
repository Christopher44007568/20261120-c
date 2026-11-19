"""Serialize run results into Markdown, CSV and JSON artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .benchmark import RunResult
from .raster import Metrics

PIPELINE_LABELS = {
    "forward_no_early_z": "Forward 无早Z",
    "forward_early_z": "Forward 早Z",
    "z_prepass": "Z-Prepass 先深度后着色",
}
ORDER_LABELS = {
    "front_to_back": "前→后",
    "back_to_front": "后→前",
    "random": "随机顺序",
}


def _label(mapping: dict[str, str], key: str) -> str:
    return f"{mapping.get(key, key)} ({key})"


def metrics_row(result: RunResult) -> dict[str, float | int | str]:
    metrics: Metrics = result.metrics
    return {
        "scene": result.scene_name,
        "pipeline": result.pipeline,
        "draw_order": result.draw_order,
        "fragments_visited": metrics.fragments_visited,
        "covered_pixels": metrics.covered_pixels,
        "overdraw_pixels_redundant": metrics.redundant_shaded,
        "avg_draws_per_pixel_all": round(
            metrics.avg_draws_per_pixel(covered_only=False), 4),
        "avg_draws_per_covered_pixel": round(
            metrics.avg_draws_per_pixel(covered_only=True), 4),
        "avg_shades_per_covered_pixel": round(
            metrics.shader_invocations / metrics.covered_pixels, 4)
        if metrics.covered_pixels else 0.0,
        "depth_tests": metrics.depth_tests,
        "depth_rejects": metrics.depth_rejects,
        "shader_invocations": metrics.shader_invocations,
        "blend_invocations": metrics.blend_invocations,
        "model_cycles": metrics.model_cycles,
        "elapsed_ms": round(metrics.elapsed_ms, 4),
    }


def write_metrics_csv(path: Path, results: list[RunResult]) -> None:
    rows = [metrics_row(result) for result in results]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_benefit_csv(path: Path, rows: list[dict[str, float | str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _markdown_table(headers: list[str],
                    rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def scene_section(title: str, results: list[RunResult]) -> str:
    headers = [
        "管线", "绘制顺序", "访问片元", "覆盖像素", "重复绘制像素",
        "每像素平均绘制(全/覆盖区)", "着色次数", "深度拒绝",
        "模型周期", "耗时(ms)",
    ]
    rows: list[list[str]] = []
    for result in results:
        metrics = result.metrics
        rows.append([
            _label(PIPELINE_LABELS, result.pipeline),
            _label(ORDER_LABELS, result.draw_order),
            str(metrics.fragments_visited),
            str(metrics.covered_pixels),
            str(metrics.redundant_shaded),
            f"{metrics.avg_draws_per_pixel():.3f} / "
            f"{metrics.avg_draws_per_pixel(covered_only=True):.3f}",
            str(metrics.shader_invocations),
            str(metrics.depth_rejects),
            f"{metrics.model_cycles:,}",
            f"{metrics.elapsed_ms:.3f}",
        ])
    return f"## {title}\n\n" + _markdown_table(headers, rows)


def benefit_section(benefit_rows: list[dict[str, float | str]]) -> str:
    headers = [
        "排名", "管线", "绘制顺序", "重复绘制下降%", "着色次数下降%",
        "模型周期下降%(排序依据)", "墙钟耗时下降%(参考)", "耗时(ms)",
    ]
    rows: list[list[str]] = []
    for rank, row in enumerate(benefit_rows, start=1):
        rows.append([
            str(rank),
            _label(PIPELINE_LABELS, str(row["pipeline"])),
            _label(ORDER_LABELS, str(row["draw_order"])),
            f"{row['overdraw_pixels_drop_pct']:.1f}",
            f"{row['shader_invocations_drop_pct']:.1f}",
            f"{row['model_cycles_drop_pct']:.1f}",
            f"{row['elapsed_drop_pct']:.1f}",
            f"{float(row['elapsed_ms']):.3f}",
        ])
    return "## 收益排序（按确定性模型周期下降，前→后；墙钟仅参考）\n\n" + \
        _markdown_table(headers, rows)


def boundary_section(
        parameter_rows: list[dict[str, float | int | str]]) -> str:
    headers = [
        "用例", "seed", "宽", "高", "四边形数", "重叠模式",
        "混合透明比例", "alpha-test 比例", "说明",
    ]
    rows = [[
        str(row["case_id"]),
        str(row["seed"]),
        str(row["width"]),
        str(row["height"]),
        str(row["quad_count"]),
        str(row["overlap"]),
        f"{float(row['transparent_fraction']):.2f}",
        f"{float(row['alpha_test_fraction']):.2f}",
        str(row["description"]),
    ] for row in parameter_rows]
    return "## 边界用例输入参数表（可复现）\n\n" + \
        _markdown_table(headers, rows)


def histogram_section(title: str, results: list[RunResult]) -> str:
    lines = [f"## {title}：每像素着色次数分布（着色 overdraw）", ""]
    for result in results:
        histogram = result.metrics.shading_histogram()
        distribution = ", ".join(
            f"{draws}次×{pixels}px" for draws, pixels in histogram.items())
        lines.append(
            f"- {_label(PIPELINE_LABELS, result.pipeline)} / "
            f"{_label(ORDER_LABELS, result.draw_order)}: {distribution}")
    return "\n".join(lines)


def write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_markdown_report(
        parameter_rows: list[dict[str, float | int | str]],
        sections: list[tuple[str, list[RunResult]]],
        benefit_by_scene: dict[str, list[dict[str, float | str]]],
        conclusions: list[str]) -> str:
    parts = [
        "# Early-Z / Overdraw 优化实验报告",
        "",
        "管线说明：`forward_no_early_z` 先着色后深度测试（基线）；"
        "`forward_early_z` 深度测试通过后才着色；"
        "`z_prepass` 先跑只写深度的预通道，第二遍按深度结果着色。",
        "",
        "指标定义：访问片元/每像素平均绘制是几何覆盖（与管线无关）；"
        "重复绘制像素=实际着色次数-最终覆盖像素，即被浪费的着色 overdraw；"
        "模型周期由固定成本模型确定性累加，用于收益排序；"
        "墙钟耗时为多次运行最小值，仅作参考。",
        "",
        boundary_section(parameter_rows),
        "",
    ]
    for title, results in sections:
        parts.extend([scene_section(title, results), "",
                      histogram_section(title, results), ""])
    for scene_name, rows in benefit_by_scene.items():
        parts.extend([f"### {scene_name}", "", benefit_section(rows), ""])
    parts.append("## 结论")
    parts.extend(f"- {item}" for item in conclusions)
    parts.append("")
    return "\n".join(parts)
