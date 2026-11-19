"""Render artifacts/reports/report.md from pipeline and compare outputs."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS = ROOT / "artifacts" / "reports"
REFLECT = ROOT / "artifacts" / "reflect"


def load(path):
    return json.loads(pathlib.Path(path).read_text())


def descriptor_table(manifest):
    lines = ["| set | binding | 类型 | 阶段 | 名称 | 大小/布局 |",
             "|---|---|---|---|---|---|"]
    for d in manifest["descriptors"]:
        size = d["size"] if d["size"] is not None else "-"
        layout = d["layout"] or "-"
        lines.append("| %d | %d | %s | %s | %s | %s / %s |" % (
            d["set"], d["binding"], d["type"], "+".join(d["stages"]),
            "/".join(sorted(set(d["names"]))), size, layout))
    for pc in manifest["pushConstants"]:
        lines.append("| - | push | push_constant | %s | %s | %d / std140 |"
                     % (pc["stage"], pc["blockType"], pc["size"]))
    return lines


def layout_tables(layouts):
    lines = []
    for block, info in layouts.items():
        lines.append("### `%s`（%s，size=%d，align=%d）" % (
            block, info["layout"], info["size"], info["align"]))
        lines.append("| 成员 | 类型 | 计算偏移 | 装饰偏移 | 数组步长(计算/装饰) | 结果 |")
        lines.append("|---|---|---|---|---|---|")
        for m in info["members"]:
            bad = any(i.startswith("member %d:" % m["index"])
                      for i in info["issues"])
            declared = m.get("declaredOffset")
            stride = "-"
            if "stride" in m:
                stride = "%d/%s" % (m["stride"], m.get("declaredStride"))
            lines.append("| %d | %s | %d | %s | %s | %s |" % (
                m["index"], m["type"], m["offset"],
                declared if declared is not None else "-", stride,
                "MISMATCH" if bad else "OK"))
        lines.append("")
    return lines


def main():
    manifest = load(REPORTS / "manifest.json")
    layouts = load(REPORTS / "layouts.json")
    conflicts = load(REPORTS / "conflicts.json")["conflicts"]
    compare = load(REPORTS / "compare.json")

    out = ["# GLSL → SPIR-V 转译与反射报告", ""]
    out.append("## 着色器资源清单")
    out += descriptor_table(manifest)
    out.append("")
    out.append("## 绑定冲突")
    if conflicts:
        out += ["- " + c for c in conflicts]
    else:
        out.append("- 无冲突：set/binding 全局唯一，跨阶段类型一致，"
                   "顶点输出与片段输入 location/类型/flat 完全匹配。")
    out.append("")
    out.append("## 结构体与数组布局对照（计算值 vs SPIR-V 装饰）")
    out += layout_tables(layouts)
    out.append("## 转译一致性")
    for c in compare["reflectionChecks"]:
        out.append("- `%s`：源SPIR-V vs 重编译反射一致=%s；"
                   "重编译 vs 往返(SPIR-V→GLSL→SPIR-V)反射一致=%s"
                   % (c["stage"], c["src_vs_new"], c["new_vs_roundtrip"]))
    for stage, d in compare["semanticDiff"].items():
        out.append("- `%s`：spirv-diff 逻辑变更数 = %d（0 表示渲染结果一致）"
                   % (stage, d["logicalChanges"]))
    out.append("")
    out.append("## 结论")
    ok = all(c["src_vs_new"] and c["new_vs_roundtrip"]
             for c in compare["reflectionChecks"]) and \
        all(d["logicalChanges"] == 0
            for d in compare["semanticDiff"].values()) and not conflicts
    out.append("转译后布局与绑定描述同源着色器完全一致，渲染结果无差异。"
               if ok else "存在不一致项，见上文。")
    (REPORTS / "report.md").write_text("\n".join(out) + "\n")
    print("wrote", REPORTS / "report.md")


if __name__ == "__main__":
    main()
