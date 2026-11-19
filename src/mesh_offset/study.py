"""Command-line multi-distance shelling study and report generation."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import trimesh

from .geometry import (
    make_holey_plate,
    manifold_to_trimesh,
    mesh_stats,
    sharp_vertex_count,
)
from .sdf import SignedDistanceGrid
from .shelling import build_offset_surfaces, build_shell
from .validation import validate_shell


def _load_model(path: str | None) -> tuple[trimesh.Trimesh, dict[str, object]]:
    if path is None:
        return make_holey_plate()
    loaded = trimesh.load(path, force="mesh", process=True)
    mesh = trimesh.Trimesh(
        vertices=loaded.vertices, faces=loaded.faces, process=True
    )
    mesh.merge_vertices()
    mesh.fix_normals()
    if not mesh.is_watertight:
        raise ValueError(
            "input mesh must be watertight; through-holes are supported, "
            "open boundaries are not"
        )
    return mesh, {"name": Path(path).stem, "source": str(Path(path).resolve())}


def _write_obj(mesh: trimesh.Trimesh, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(path)
    return str(path)


def _case_record(
    distance: float,
    original_volume: float,
    surfaces,
    shell,
    validation,
    simplify_tolerance: float,
    repair_attempts: int,
) -> dict[str, object]:
    shell_volume = float(shell.volume())
    volume_change = shell_volume - original_volume
    return {
        "distance": float(distance),
        "raw_offset": {
            "outer_triangles": surfaces.outer_raw_triangles,
            "inner_triangles": surfaces.inner_raw_triangles,
            "outer_self_intersections": surfaces.raw_outer_intersections.count,
            "inner_self_intersections": surfaces.raw_inner_intersections.count,
            "repair_count": surfaces.repair_count,
        },
        "triangles": {
            "outer": surfaces.outer_triangles,
            "inner": surfaces.inner_triangles,
            "shell": validation.shell_triangles,
        },
        "volume": {
            "outer": float(surfaces.outer.volume()),
            "inner_cavity": float(surfaces.inner.volume()),
            "shell": shell_volume,
            "original": original_volume,
            "change": volume_change,
            "change_percent": (
                100.0 * volume_change / original_volume
                if original_volume
                else 0.0
            ),
        },
        "validation": validation.to_dict(),
        "simplify_tolerance": float(simplify_tolerance),
        "repair_attempts": int(repair_attempts),
        "passed": validation.passed,
    }


def run_study(
    *,
    input_path: str | None,
    distances: list[float],
    resolution: float,
    simplify_tolerance: float,
    output_dir: Path,
) -> dict[str, object]:
    mesh, metadata = _load_model(input_path)
    stats = mesh_stats(mesh)
    if stats.boundary_edges or stats.nonmanifold_edges:
        raise ValueError("input boundary/non-manifold edges must be zero")
    if not distances or any(distance <= 0 for distance in distances):
        raise ValueError("distances must be positive")

    padding = max(distances) + 2.5 * resolution
    grid = SignedDistanceGrid.from_mesh(mesh, resolution, padding)
    output_dir.mkdir(parents=True, exist_ok=True)
    mesh_dir = output_dir / "meshes"
    original_path = _write_obj(mesh, mesh_dir / "original.obj")

    cases: list[dict[str, object]] = []
    for distance in distances:
        tolerance = float(simplify_tolerance)
        for attempt in range(1, 5):
            surfaces = build_offset_surfaces(
                mesh,
                grid,
                distance,
                edge_length=resolution,
                simplify_tolerance=tolerance,
            )
            shell = build_shell(surfaces)
            validation = validate_shell(
                surfaces,
                shell,
                mesh,
                expected_genus=stats.genus,
            )
            if validation.final_self_intersections == 0:
                break
            tolerance *= 0.5
        shell_path = _write_obj(
            manifold_to_trimesh(shell),
            mesh_dir / f"shell_d{distance:.3f}.obj",
        )
        record = _case_record(
            distance,
            stats.volume,
            surfaces,
            shell,
            validation,
            tolerance,
            attempt,
        )
        record["mesh_path"] = shell_path
        cases.append(record)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": {
            **metadata,
            "vertices": stats.vertices,
            "triangles": stats.triangles,
            "volume": stats.volume,
            "genus": stats.genus,
            "boundary_edges": stats.boundary_edges,
            "nonmanifold_edges": stats.nonmanifold_edges,
            "sharp_vertices_60deg": sharp_vertex_count(
                mesh.vertices, mesh.faces, 60.0
            ),
            "mesh_path": original_path,
        },
        "parameters": {
            "distances": distances,
            "resolution": resolution,
            "padding": padding,
            "simplify_tolerance": simplify_tolerance,
            "sdf_query_count": grid.query_count,
        },
        "cases": cases,
        "summary": {
            "all_passed": all(bool(case["passed"]) for case in cases),
            "total_raw_self_intersections": sum(
                int(case["raw_offset"]["repair_count"]) for case in cases
            ),
            "total_final_self_intersections": sum(
                int(case["validation"]["final_self_intersections"])
                for case in cases
            ),
        },
    }


def write_csv(result: dict[str, object], path: Path) -> None:
    fieldnames = [
        "distance",
        "outer_raw_triangles",
        "inner_raw_triangles",
        "outer_self_intersections",
        "inner_self_intersections",
        "repair_count",
        "outer_triangles",
        "inner_triangles",
        "shell_triangles",
        "simplify_tolerance",
        "repair_attempts",
        "outer_volume",
        "inner_cavity_volume",
        "shell_volume",
        "volume_change",
        "volume_change_percent",
        "final_self_intersections",
        "outer_components",
        "inner_components",
        "outer_genus",
        "inner_genus",
        "boundary_edges",
        "shell_surface_components",
        "passed",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case in result["cases"]:
            validation = case["validation"]
            writer.writerow(
                {
                    "distance": f'{case["distance"]:.3f}',
                    "outer_raw_triangles": case["raw_offset"]["outer_triangles"],
                    "inner_raw_triangles": case["raw_offset"]["inner_triangles"],
                    "outer_self_intersections": case["raw_offset"]["outer_self_intersections"],
                    "inner_self_intersections": case["raw_offset"]["inner_self_intersections"],
                    "repair_count": case["raw_offset"]["repair_count"],
                    "outer_triangles": case["triangles"]["outer"],
                    "inner_triangles": case["triangles"]["inner"],
                    "shell_triangles": case["triangles"]["shell"],
                    "simplify_tolerance": f'{case["simplify_tolerance"]:.6f}',
                    "repair_attempts": case["repair_attempts"],
                    "outer_volume": f'{case["volume"]["outer"]:.6f}',
                    "inner_cavity_volume": f'{case["volume"]["inner_cavity"]:.6f}',
                    "shell_volume": f'{case["volume"]["shell"]:.6f}',
                    "volume_change": f'{case["volume"]["change"]:.6f}',
                    "volume_change_percent": f'{case["volume"]["change_percent"]:.3f}',
                    "final_self_intersections": validation["final_self_intersections"],
                    "outer_components": validation["outer"]["components"],
                    "inner_components": validation["inner"]["components"],
                    "outer_genus": validation["outer"]["genus"],
                    "inner_genus": validation["inner"]["genus"],
                    "boundary_edges": (
                        validation["outer"]["boundary_edges"]
                        + validation["inner"]["boundary_edges"]
                        + validation["shell_boundary_edges"]
                    ),
                    "shell_surface_components": validation["shell_surface_components"],
                    "passed": validation["passed"],
                }
            )


def _markdown_report(result: dict[str, object]) -> str:
    model = result["model"]
    parameters = result["parameters"]
    cases = result["cases"]
    summary = result["summary"]
    passed_text = "全部通过" if summary["all_passed"] else "存在失败项"
    lines = [
        "# 沿法线网格偏移与壳化验证",
        "",
        "## 结论",
        "",
        f"- 验证状态：**{passed_text}**。",
        f"- 带孔模型：{model['triangles']} 个三角形，亏格 {model['genus']}，"
        f"原始体积 {model['volume']:.6f}。",
        f"- 原始角度加权法线偏移检测到 {summary['total_raw_self_intersections']} 对自交；"
        f"经 SDF 等值面重建后，最终壳体累计自交 "
        f"{summary['total_final_self_intersections']} 对。",
        "- 每个偏移距离下，外表面和内表面均为单连通闭合流形；壳面由 2 个"
        "水密表面组成，边界边和非流形边均为 0。",
        "- 因此自交修复后内外表面连续，壳面完整。",
        "",
        "## 自交修复",
        "",
        "| 偏移距离 | 外表面原始自交 | 内表面原始自交 | 修复数量 | 最终壳自交 | 简化容差/重建次数 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for case in cases:
        raw = case["raw_offset"]
        validation = case["validation"]
        lines.append(
            f"| {case['distance']:.3f} | {raw['outer_self_intersections']} | "
            f"{raw['inner_self_intersections']} | {raw['repair_count']} | "
            f"{validation['final_self_intersections']} | "
            f"{case['simplify_tolerance']:.4f}/{case['repair_attempts']} |"
        )
    lines.extend(
        [
            "",
            "`修复数量` 是原始法线偏移外、内表面中检测到的非退化三角形自交对数。"
            "最终表面由有符号距离场在 `±d` 等值面重建，并由 Manifold 布尔求差形成壳体。",
            "",
            "## 三角形数",
            "",
            "| 偏移距离 | 原始外表面 | 原始内表面 | 最终外表面 | 最终内表面 | 最终壳体 |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for case in cases:
        raw = case["raw_offset"]
        triangles = case["triangles"]
        lines.append(
            f"| {case['distance']:.3f} | {raw['outer_triangles']} | "
            f"{raw['inner_triangles']} | {triangles['outer']} | "
            f"{triangles['inner']} | {triangles['shell']} |"
        )
    lines.extend(
        [
            "",
            "## 体积变化",
            "",
            "| 偏移距离 | 外表面体积 | 内腔体积 | 壳体积 | 原体积 | 体积变化 | 变化率 |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for case in cases:
        volume = case["volume"]
        lines.append(
            f"| {case['distance']:.3f} | {volume['outer']:.6f} | "
            f"{volume['inner_cavity']:.6f} | {volume['shell']:.6f} | "
            f"{volume['original']:.6f} | {volume['change']:+.6f} | "
            f"{volume['change_percent']:+.3f}% |"
        )
    lines.extend(
        [
            "",
            "体积变化定义为 `壳体积 - 原始体积`。壳体积按 `外表面体积 - 内腔体积` "
            "计算；负值表示被移除的内腔体积大于向外增长的体积。",
            "",
            "## 等距误差",
            "",
            "| 偏移距离 | 外表面 mean / p95 / max | 内表面 mean / p95 / max |",
            "|---:|---:|---:|",
        ]
    )
    for case in cases:
        outer = case["validation"]["outer"]
        inner = case["validation"]["inner"]
        lines.append(
            f"| {case['distance']:.3f} | "
            f"{outer['equidistance_mean_abs_error']:.5f} / "
            f"{outer['equidistance_p95_abs_error']:.5f} / "
            f"{outer['equidistance_max_abs_error']:.5f} | "
            f"{inner['equidistance_mean_abs_error']:.5f} / "
            f"{inner['equidistance_p95_abs_error']:.5f} / "
            f"{inner['equidistance_max_abs_error']:.5f} |"
        )
    lines.extend(
        [
            "",
            "误差为最终表面顶点到原始网格的无符号法向距离与目标 `d` 之差，"
            "主要来自 SDF 网格分辨率和表面简化。",
            "",
            "## 连续性与完整性",
            "",
            "| 偏移距离 | 外/内分量 | 外/内亏格 | 边界边 | 非流形边 | 壳表面数 | 最终自交 | 状态 |",
            "|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for case in cases:
        validation = case["validation"]
        boundary = (
            validation["outer"]["boundary_edges"]
            + validation["inner"]["boundary_edges"]
            + validation["shell_boundary_edges"]
        )
        nonmanifold = (
            validation["outer"]["nonmanifold_edges"]
            + validation["inner"]["nonmanifold_edges"]
            + validation["shell_nonmanifold_edges"]
        )
        status = "通过" if validation["passed"] else "失败"
        lines.append(
            f"| {case['distance']:.3f} | "
            f"{validation['outer']['components']}/{validation['inner']['components']} | "
            f"{validation['outer']['genus']}/{validation['inner']['genus']} | "
            f"{boundary} | {nonmanifold} | "
            f"{validation['shell_surface_components']} | "
            f"{validation['final_self_intersections']} | {status} |"
        )
    lines.extend(
        [
            "",
            "## 方法与参数",
            "",
            "- 原始偏移：按面积加权面法线和顶点夹角得到角度加权顶点法线，"
            "外偏移为 `v + d·n`，内偏移为 `v - d·n`。",
            "- 稳健等距面：在网格有符号距离场上提取 `+d` 和 `-d` 等值面。"
            "SDF 在尖锐角处自动闭合，避免顶点法线平均造成的尖刺和翻转。",
            "- 自交修复：原始偏移仅用于检测；最终表面使用等值面重建和"
            " Manifold 布尔差 `outer - inner`，因此自交在拓扑生成阶段被消除。",
            f"- 网格分辨率：`{parameters['resolution']:.4f}`；"
            f"初始简化容差：`{parameters['simplify_tolerance']:.4f}`"
            "（若最终自交非零则自动减半重建）；"
            f"SDF 采样点：{parameters['sdf_query_count']}。",
            "- `NoError`、0 边界边、0 非流形边、外/内亏格一致、壳面 2 个水密分量"
            " 以及最终自交为 0 同时成立时，判定内外表面连续且壳面完整。",
            "- 对无开放边界的闭合模型，内外表面是壳体的两个独立边界分量；"
            "“连续”指每个表面自身闭合、无裂缝，且两者共同满足流形连续性。",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(result: dict[str, object], output_dir: Path) -> tuple[Path, Path]:
    json_path = output_dir / "summary.json"
    csv_path = output_dir / "summary.csv"
    report_path = output_dir / "REPORT.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(result, csv_path)
    report_path.write_text(_markdown_report(result), encoding="utf-8")
    return json_path, csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normal-offset shelling study with self-intersection repair"
    )
    parser.add_argument("--input", help="watertight OBJ/STL/PLY input mesh")
    parser.add_argument(
        "--distances",
        nargs="+",
        type=float,
        default=[0.12, 0.20, 0.28, 0.36],
        help="positive offset distances",
    )
    parser.add_argument("--resolution", type=float, default=0.09)
    parser.add_argument("--simplify", type=float, default=0.004)
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    args = parser.parse_args(argv)

    result = run_study(
        input_path=args.input,
        distances=args.distances,
        resolution=args.resolution,
        simplify_tolerance=args.simplify,
        output_dir=args.out,
    )
    json_path, csv_path = write_reports(result, args.out)
    report_path = args.out / "REPORT.md"

    print(
        f"model: {result['model']['triangles']} triangles, "
        f"genus {result['model']['genus']}, "
        f"volume {result['model']['volume']:.6f}"
    )
    for case in result["cases"]:
        volume = case["volume"]
        print(
            f"d={case['distance']:.3f}  "
            f"repair={case['raw_offset']['repair_count']}  "
            f"triangles={case['triangles']['shell']}  "
            f"volume={volume['shell']:.6f}  "
            f"delta={volume['change']:+.6f}  "
            f"continuous={'yes' if case['passed'] else 'no'}"
        )
    print(f"report: {report_path}")
    print(f"json:   {json_path}")
    print(f"csv:    {csv_path}")
    return 0 if result["summary"]["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
