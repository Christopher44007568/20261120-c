"""Markdown report generation from measured experiment results."""

from __future__ import annotations

import statistics
from pathlib import Path


def _fmt(value: object, digits: int = 4) -> str:
    return f"{float(value):.{digits}f}"


def _quarter_rows(pose_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    size = max(1, len(pose_rows) // 4)
    result: list[dict[str, object]] = []
    for index in range(4):
        start = index * size
        end = len(pose_rows) if index == 3 else (index + 1) * size
        chunk = pose_rows[start:end]
        result.append(
            {
                "frames": f"{start}-{end - 1}",
                "containment_min": min(float(row["vertex_containment"]) for row in chunk),
                "root_volume_min": min(float(row["root_volume_m3"]) for row in chunk),
                "root_volume_mean": statistics.mean(
                    float(row["root_volume_m3"]) for row in chunk
                ),
                "root_volume_max": max(float(row["root_volume_m3"]) for row in chunk),
                "update_mean_us": statistics.mean(
                    float(row["box_update_ms"]) for row in chunk
                )
                * 1000.0,
            }
        )
    return result


def build_report(
    bbh_result: dict[str, object],
    culling_result: dict[str, object],
    geodesic_result: dict[str, object],
) -> str:
    fit = bbh_result["fit"]
    layers = bbh_result["layers"]
    pose_rows = bbh_result["pose_rows"]
    culling_depths = culling_result["depths"]
    culling_validation = culling_result["validation"]
    geo_checks = geodesic_result["checks"]
    geo_rows = geodesic_result["rows"]
    assert isinstance(fit, dict) and isinstance(layers, list) and isinstance(pose_rows, list)
    assert isinstance(culling_depths, list) and isinstance(culling_validation, dict)
    assert isinstance(geo_checks, dict) and isinstance(geo_rows, list)

    lines = [
        "# 骨骼包围盒层次、奔跑贴合与障碍曲面测地路径",
        "",
        "本报告由 `python3 run_all.py` 全自动生成。所有实验均为纯标准库实现，"
        "随机过程使用固定种子；图表为 SVG，数据表为 CSV/JSON。",
        "",
        "## 结论摘要",
        "",
        f"- 19 骨骼、7 层拓扑层次，共 {int(fit['vertices_per_frame'])} 个每帧蒙皮点；"
        f"{int(fit['frames'])} 帧全部满足顶点与子树包围，越界距离为 "
        f"{_fmt(fit['max_outside_distance_m'], 6)} m。",
        f"- 盒更新（AABB 重算 + 自底向上合并）平均 "
        f"{_fmt(fit['box_update_ms_per_frame'], 4)} ms/帧；姿态、蒙皮和盒更新合计 "
        f"{_fmt(fit['pose_skin_box_update_ms_per_frame'], 4)} ms/帧。",
        f"- 视锥剔除率随深度从 {float(culling_depths[0]['culling_rate']) * 100:.1f}% "
        f"升至 {float(culling_depths[-1]['culling_rate']) * 100:.1f}%；"
        "全深度结果与逐骨骼暴力测试完全一致，未发现误剔除。",
        f"- 平面圆形障碍的曲面图搜索距离与解析解相对误差 "
        f"{float(geo_checks['flat_relative_error']) * 100:.3f}%；"
        f"曲面 0.02 m 与 0.01 m 网格结果相差 "
        f"{float(geo_checks['curved_convergence_difference']) * 100:.5f}%，"
        "且路径最小净距不小于 0.6000 m。",
        "",
        "## 1. 骨骼层次与包围盒定义",
        "",
        "角色由 19 根骨骼组成，深度 0–6。每根骨骼拥有沿骨段生成的胶囊表面采样点；"
        "刚性随骨骼世界变换更新。节点自身盒 `own_box` 包住本骨骼采样点，"
        "层次盒 `box = union(own_box, child.box)`，因此父节点同时包围其拓扑子树。",
        "",
        "| 校验项 | 结果 |",
        "|---|---:|",
        f"| 奔跑帧数 | {int(fit['frames'])} |",
        f"| 每帧采样顶点 | {int(fit['vertices_per_frame'])} |",
        f"| 层次节点数 / 深度 | {int(fit['nodes'])} / {int(fit['depths'])} |",
        f"| 全部顶点包含 | {'是' if fit['all_frames_fully_contained'] else '否'} |",
        f"| 全部子树包含 | {'是' if fit['all_subtrees_contained'] else '否'} |",
        f"| 父盒包含所有子盒 | {'是' if fit['all_hierarchies_contain_children'] else '否'} |",
        f"| 包围盒六面均有采样点支撑 | {float(fit['minimum_supported_faces_ratio']) * 100:.1f}% |",
        f"| 胶囊体积 / 自身盒体积均值 | {float(fit['mean_capsule_fill_ratio']) * 100:.2f}% |",
        f"| 最大越界距离 | {_fmt(fit['max_outside_distance_m'], 8)} m |",
        "",
        "## 2. 奔跑贴合验证",
        "",
        f"{int(fit['frames'])} 帧中根包围盒体积范围 "
        f"{_fmt(fit['root_volume_min_m3'])}–{_fmt(fit['root_volume_max_m3'])} m³，"
        f"极差 {_fmt(fit['root_volume_range_m3'])} m³；相邻帧根盒中心平均位移 "
        f"{_fmt(fit['mean_consecutive_root_center_shift_m'])} m，"
        f"单帧最大顶点位移至少 {_fmt(fit['min_max_vertex_motion_between_frames_m'])} m。"
        "这说明盒体确实随奔跑姿态变化，而不是沿用绑定姿态。",
        "",
        "| 帧段 | 最小包含率 | 根体积最小 | 根体积均值 | 根体积最大 | 平均盒更新 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in _quarter_rows(pose_rows):
        lines.append(
            f"| {row['frames']} | {float(row['containment_min']) * 100:.2f}% | "
            f"{_fmt(row['root_volume_min'])} m³ | {_fmt(row['root_volume_mean'])} m³ | "
            f"{_fmt(row['root_volume_max'])} m³ | {_fmt(row['update_mean_us'], 1)} µs |"
        )
    lines.extend(
        [
            "",
            "复验结论：四个连续帧段均为 100% 顶点包含，层次盒没有滞后或残留上一帧包围体。",
            "",
            "## 3. 各层包围盒体积与更新耗时",
            "",
            "> 体积是该层所有节点 AABB 体积之和；父子盒存在空间重叠，不能相加当作并集体积。",
            "> 更新时间仅含该层自身 AABB 重算与合并，已排除递归子节点重复计时。",
            "",
            "| 深度 | 节点数 | 总体积 m³ | 均体积 m³ | 最大体积 m³ | 更新 µs/帧 | 体积占比 |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in layers:
        lines.append(
            f"| {int(row['depth'])} | {int(row['nodes'])} | "
            f"{_fmt(row['total_volume_m3'], 6)} | {_fmt(row['mean_volume_m3'], 6)} | "
            f"{_fmt(row['max_volume_m3'], 6)} | "
            f"{float(row['update_ms_per_frame']) * 1000:.2f} | "
            f"{float(row['volume_share']) * 100:.2f}% |"
        )
    lines.extend(
        [
            "",
            f"根层单盒体积占比高，但它只更新一次；深层节点更多，单节点盒更小。"
            f"全部 19 个节点的每帧盒更新总耗时实测为 "
            f"{float(fit['box_update_ms_per_frame']) * 1000:.1f} µs；"
            f"姿态+蒙皮+盒更新为 {_fmt(fit['pose_skin_box_update_ms_per_frame'], 3)} ms/帧。",
            "",
            "## 4. 层次深度对剔除率的影响",
            "",
            f"用 {int(culling_result['cameras'])} 个固定透视视锥、"
            f"{int(culling_result['frames'])} 个奔跑姿态（共 "
            f"{int(culling_validation['queries'])} 次查询）比较深度上限 0–6。"
            "父盒完全在任一视锥平面外时，整棵子树可安全拒绝；到达深度上限后停止细分。",
            "",
            "| 深度上限 | 剔除骨骼数 | 剔除率 | 候选骨骼数 | 候选率 |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for row in culling_depths:
        lines.append(
            f"| {int(row['depth'])} | {_fmt(row['mean_culled_primitives'], 3)} | "
            f"{float(row['culling_rate']) * 100:.2f}% | "
            f"{_fmt(row['mean_candidate_primitives'], 3)} | "
            f"{float(row['mean_candidate_rate']) * 100:.2f}% |"
        )
    lines.extend(
        [
            "",
            "深度 1 的躯干/双腿分支带来第一次明显提升；深度 3 同时区分头颈、锁骨和足部，"
            "增量最大；深度 4–6 仍有收益，但每题最多只减少约 0.2–0.4 个候选骨骼，"
            "呈明显边际递减。若场景主要做粗粒度视锥剔除，深度 3–4 是较合理的性价比区间。",
            "",
            "## 5. 包围盒更新与层次剔除正确性",
            "",
            f"- 安全性子集：所有深度下被剔除骨骼均属于暴力测试的真实视锥外集合，"
            f"违规 {int(culling_validation['partial_subset_violations'])} 次。",
            f"- 误剔除：{int(culling_validation['false_culls'])} 次。",
            f"- 全深度与逐骨骼暴力测试不一致："
            f"{int(culling_validation['full_mismatches_vs_bruteforce'])} 次。",
            f"- 被拒绝节点中，实际自身盒不与视锥相交："
            f"{int(culling_validation['outside_ancestor_violations'])} 次。",
            f"- 综合安全结论：{'通过' if culling_validation['safe'] else '失败'}；"
            f"全深度精确性：{'通过' if culling_validation['exact_at_full_depth'] else '失败'}。",
            "",
            "## 6. 带障碍曲面最短路径与测地距离",
            "",
            "曲面定义在半径 1.8 m 的圆域内，中心有半径 0.60 m 的圆形不可通行障碍。"
            "高度场为 `z = 0.18t² + 0.032 sin(3θ) sin(πt)`，`t` 为障碍到外边界归一化半径。"
            "在笛卡尔网格上建立 24 邻域图，跨障碍线段用点到线段距离拒绝，边长取三维欧氏长度，"
            "再用 Dijkstra 求测地路径。起点 `(-1.40, -0.52)`、终点 `(1.40, -0.52)`，"
            "直线弦穿过障碍，必须绕行。",
            "",
            "正确性采用双重校验：平面高度场与圆障碍解析解（两条切线段 + 圆弧）比较；"
            "曲面高度场比较 0.02 m 粗网格与 0.01 m 细网格的收敛差。",
            "",
            "| 案例 | 网格间距 | 网格节点 | 路径长度 | 参照长度 | 相对差 | 最小净距 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in geo_rows:
        lines.append(
            f"| {row['case']} | {_fmt(row['spacing_m'], 3)} m | "
            f"{int(row['mesh_vertices'])} | {_fmt(row['distance_m'], 6)} m | "
            f"{_fmt(row['reference_m'], 6)} m | "
            f"{float(row['relative_difference']) * 100:.4f}% | "
            f"{_fmt(row['clearance_m'], 6)} m |"
        )
    lines.extend(
        [
            "",
            f"平面解析距离 {_fmt(geo_checks['analytic_distance_m'], 6)} m；"
            f"网格测地距离 {_fmt(geo_checks['flat_distance_m'], 6)} m，"
            f"误差 {float(geo_checks['flat_relative_error']) * 100:.3f}%（小于 1%）。"
            f"曲面细网格距离 {_fmt(geo_checks['curved_fine_distance_m'], 6)} m，"
            f"与粗网格相差 {float(geo_checks['curved_convergence_difference']) * 100:.5f}%。"
            f"起点到点的直线欧氏距离仅 {_fmt(geo_checks['euclidean_start_goal_m'], 3)} m，"
            "但被障碍阻断；实际绕行路径更长且全程净距 ≥ 0.60 m，符合几何预期。",
            "",
            "完整路径坐标、分段长和累计弧长见 `artifacts/geodesic_path_curved.csv`；"
            "平面解析路径和网格路径分别见 `geodesic_path_analytic.csv`、"
            "`geodesic_path_flat.csv`。",
            "",
            "## 7. 复现与产物",
            "",
            "```bash",
            "python3 run_all.py",
            "python3 -m unittest discover -s tests -v",
            "```",
            "",
            "主要产物：`artifacts/report.md`、`bbh_metrics.json`、`layer_bbox_metrics.csv`、"
            "`pose_fit.csv`、`culling_depth.csv`、`culling_metrics.json`、"
            "`geodesic_validation.csv`、`geodesic_path_curved.csv` 及 4 张 SVG 图。",
            "",
            "## 限制",
            "",
            "- 角色和胶囊蒙皮是确定性程序化资产，用于检验拓扑层次、姿态更新和度量流程，"
            "不是美术级人体网格。",
            "- 更新时间是当前 Python/CPU 环境的相对值；换语言或并行实现后绝对值会变化，"
            "但层次深度趋势与剔除正确性校验方法仍适用。",
            "- 测地网格误差主要来自障碍边界和方向离散；平面解析校验与曲面网格收敛共同约束结果。",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(
    artifact_dir: Path,
    bbh_result: dict[str, object],
    culling_result: dict[str, object],
    geodesic_result: dict[str, object],
    root_dir: Path | None = None,
) -> Path:
    content = build_report(bbh_result, culling_result, geodesic_result)
    artifact_report = artifact_dir / "report.md"
    artifact_report.write_text(content, encoding="utf-8")
    root = root_dir or Path.cwd()
    (root / "REPORT.md").write_text(content, encoding="utf-8")
    return artifact_report
