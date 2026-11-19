"""Artifact serialization and human-readable benchmark summaries."""

from __future__ import annotations

import json
from pathlib import Path

from .benchmark import BenchmarkResult
from .dependency import DependencyGraph
from .model import SCENE_MATERIALS


def write_artifacts(result: BenchmarkResult, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    graph = DependencyGraph.keyword_graph()
    payload = result.to_dict()
    payload["scene"] = {
        "materials": [
            {
                "name": material.name,
                "required": sorted(material.required),
                "optional": list(material.optional),
                "paths": list(material.paths),
            }
            for material in SCENE_MATERIALS
        ],
        "material_count": len(SCENE_MATERIALS),
        "path_count": len({path for material in SCENE_MATERIALS for path in material.paths}),
        "variant_count": result.pruned_count,
    }
    payload["dependency_graph"] = {
        "acyclic": result.dependency_graph_acyclic,
        "nodes": list(graph.nodes),
        "edges": [list(edge) for edge in graph.edges],
        "topological_order": list(graph.topological_order()),
    }
    payload["validation"]["all_checks_pass"] = all_validation_passed(result)

    report_path = output_dir / "report.json"
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    invalid_path = output_dir / "invalid-combinations.json"
    invalid_path.write_text(
        json.dumps(
            {
                "candidate_count": result.baseline_count,
                "invalid_variant_count": result.invalid_removed,
                "reason_occurrences": result.invalid_reason_counts,
                "samples": list(result.invalid_samples),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    dot_path = output_dir / "dependency-graph.dot"
    dot_path.write_text(graph.to_dot(), encoding="utf-8")
    mermaid_path = output_dir / "dependency-graph.mmd"
    mermaid_path.write_text(graph.to_mermaid(), encoding="utf-8")
    summary_path = output_dir / "summary.md"
    summary_path.write_text(render_summary(result), encoding="utf-8")
    return {
        "report": report_path,
        "invalid": invalid_path,
        "dot": dot_path,
        "mermaid": mermaid_path,
        "summary": summary_path,
    }


def all_validation_passed(result: BenchmarkResult) -> bool:
    validation = result.to_dict()["validation"]
    required_checks = (
        "invalid_removed",
        "permutation_accounting_balanced",
        "scene_variants_covered",
        "first_frame_improved",
        "dependency_graph_acyclic",
    )
    return all(validation[name] for name in required_checks)


def render_summary(result: BenchmarkResult) -> str:
    before_frame = result.baseline_first_frame
    after_frame = result.pruned_first_frame
    validation = result.to_dict()["validation"]
    reduction = 100.0 * (
        1.0 - result.pruned_count / result.baseline_count
    )
    invalid_reasons = "\n".join(
        f"- `{reason}`: {count}"
        for reason, count in result.invalid_reason_counts.items()
    )
    check_names = (
        "invalid_removed",
        "permutation_accounting_balanced",
        "scene_variants_covered",
        "first_frame_improved",
        "dependency_graph_acyclic",
        "cache_hit_rate_improved",
    )
    checks = "\n".join(
        f"- [{'x' if validation[name] else ' '}] `{name}`" for name in check_names
    )
    return f"""# 着色器排列裁剪报告

## 裁剪结果

| 指标 | 裁剪前 | 裁剪后 |
| --- | ---: | ---: |
| 排列数量 | {result.baseline_count} | {result.pruned_count} |
| 编译数量 | {result.baseline_compile.compile_count} | {result.pruned_compile.compile_count} |
| 全量编译耗时 | {result.baseline_compile.elapsed_ms:.3f} ms | {result.pruned_compile.elapsed_ms:.3f} ms |
| 首帧耗时 | {before_frame.elapsed_ms:.3f} ms | {after_frame.elapsed_ms:.3f} ms |
| 缓存命中率 | {before_frame.hit_rate:.2%} | {after_frame.hit_rate:.2%} |
| 缓存请求命中/总数 | {before_frame.hits}/{before_frame.requests} | {after_frame.hits}/{after_frame.requests} |
| 缓存驻留条目 | {before_frame.cache_entries} | {after_frame.cache_entries} |

排列数量下降 **{reduction:.2f}%**，全量编译耗时下降
**{_reduction(result.baseline_compile.elapsed_ms, result.pruned_compile.elapsed_ms):.2f}%**，
首帧耗时下降 **{_reduction(before_frame.elapsed_ms, after_frame.elapsed_ms):.2f}%**。

## 裁剪审计

- 基线笛卡尔积：{result.baseline_count}
- 语义有效基线：{result.semantically_valid_raw}
- 已删除无效组合：{result.invalid_removed}
- 最小化合并重复项：{result.duplicate_variants_merged}
- 场景未使用的有效组合：{result.unused_valid_removed}
- 最终最小排列：{result.pruned_count}
- 无效组合与最终排列交集：{result.invalid_overlap_with_pruned}

无效原因按出现次数统计（同一排列可能有多个原因）：

{invalid_reasons}

## 验收

{checks}

## 口径

- 场景包含 {len(SCENE_MATERIALS)} 种材质，共 {result.config.draws_per_variant} 轮请求。
- 编译耗时是同一进程内对本仓库小模型着色器编译器的实测值，不包含 GPU 驱动编译。
- LRU 缓存容量为 {result.config.cache_capacity}；首帧耗时等于预热编译耗时加场景请求缺失编译耗时。
- 依赖图见 `dependency-graph.dot` 与 `dependency-graph.mmd`，环检测结果：
  {'无环' if result.dependency_graph_acyclic else '存在环'}。
"""


def _reduction(before: float, after: float) -> float:
    return (1.0 - after / before) * 100.0 if before else 0.0
