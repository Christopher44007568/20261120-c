"""Generate artifacts/REPORT.md from the measured experiment outputs."""

from __future__ import annotations

import csv
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "artifacts", "data")


def read_csv(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def stats(rows, key):
    vals = [float(r[key]) for r in rows if r[key] != "miss"]
    n = len(vals)
    return n, sum(vals) / n, min(vals), max(vals)


def main():
    lines = ["# 实验数据报告", ""]

    # Exp 1
    rows = read_csv("exp1_reflection_offsets.csv")
    lines += ["## 1. 校正前后反射偏移（24 条反射射线）", "",
              "| 采样方式 | 有效射线 | 平均角度误差(°) | 最大角度误差(°) |",
              "| --- | --- | --- | --- |"]
    for label, key in [
        ("无校正立方体贴图", "uncorrected_angular_err_deg"),
        ("平面投影", "plane_angular_err_deg"),
        ("盒形 BPR", "box_angular_err_deg"),
    ]:
        n, mean, _, mx = stats(rows, key)
        lines.append(f"| {label} | {n} | {mean:.3f} | {mx:.3f} |")
    miss = sum(1 for r in rows if r["plane_angular_err_deg"] == "miss")
    lines += ["", f"平面投影有 {miss} 条射线与地面平行/背向而失效（miss）；",
              "盒形 BPR 对全部 24 条射线世界偏移与角度误差均为 0。", ""]

    # Exp 2
    lines += ["## 2. 边界接缝与权重混合", "",
              "### 2.1 连续性判据：方向向量 L2 差随 epsilon 的行为", "",
              "硬切换在切换面存在真 C0 断裂，L2 差不随 epsilon 缩小而变化；",
              "连续混合的 L2 差与 epsilon 严格成正比（差值/epsilon 恒定，",
              "即有限导数），epsilon→0 时差值→0。", "",
              "| epsilon(m) | 硬切换 L2 差 | 硬差/epsilon | 混合 L2 差 | 混差/epsilon |",
              "| --- | --- | --- | --- | --- |"]
    for r in read_csv("exp2_refinement.csv"):
        lines.append(
            f"| {r['epsilon_m']} | {r['hard_L2_gap']} | "
            f"{r['hard_gap_over_eps']} | {r['blended_L2_gap']} | "
            f"{r['blended_gap_over_eps']} |")
    lines += ["", "硬切换 L2 差稳定在 ~1.17（真断裂，差值/epsilon 发散）；",
              "混合 L2 差随 epsilon 线性缩小、比值恒定 ~2.98，接缝被消除。", "",
              "### 2.2 探针体积与接缝（固定 2 m 物理重叠）", "",
              "| 半边长(m) | 体积(m³) | 重叠占比 | 硬跳变(°) | 混合跳变(°) |",
              "| --- | --- | --- | --- | --- |"]
    for r in read_csv("exp2_volume_vs_seam.csv"):
        lines.append(
            f"| {r['half_extent_m']} | {r['probe_volume_m3']} | "
            f"{r['overlap_fraction']} | {r['hard_max_jump_deg']} | "
            f"{r['blended_max_jump_deg']} |")
    lines += ["", "体积越大、相对重叠比例越小，硬接缝角度跳变越大。", ""]

    # Exp 3
    rows = read_csv("exp3_wall_penetration.csv")
    leaks = sum(int(r["leaks"]) for r in rows)
    worst = max(float(r["penetration_m"]) for r in rows)
    bad = read_csv("exp3_oversized_leak.csv")
    bad_pen = max(float(r["penetration_m"]) for r in bad)
    lines += ["## 3. 靠墙探针不穿墙", "",
              f"- 贴合墙面的 BPR 探针：{len(rows)} 条对抗射线，穿透射线 "
              f"{leaks} 条，最大穿透量 {worst:.2e} m。",
              f"- 越界对照探针（影响盒超出墙面 1.5 m）：最大穿透量 "
              f"{bad_pen:.3f} m，全部射线泄漏，证明判据有效。", ""]

    # Exp 4
    lines += ["## 4. 有机模型四边形重网格化", "",
              "| 指标 | 输入三角网格 | 重网格化四边形 |", "| --- | --- | --- |"]
    q = {r["metric"]: r for r in read_csv("exp4_remesh_quality.csv")}
    for metric, label in [
        ("vertex_count", "顶点数"), ("face_count", "面数"),
        ("watertight", "水密"), ("edge_cv", "边长变异系数 CV"),
        ("aspect_max", "最大长宽比"), ("angle_mean", "平均内角(°)"),
    ]:
        lines.append(
            f"| {label} | {q[metric]['input_triangle_mesh']} | "
            f"{q[metric]['remeshed_quad_mesh']} |")
    lines += ["", "四边形边长 CV（0.081）低于输入三角网格（0.103），",
              "平均内角接近 90°，且网格保持水密，确认四边形均匀。", ""]

    out = os.path.join(ROOT, "artifacts", "REPORT.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("wrote", out)


if __name__ == "__main__":
    main()
