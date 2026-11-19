"""GLSL to SPIR-V transpile and reflection pipeline.

Steps: compile, validate, reflect, verify block layouts, merge stages
into a resource manifest and detect binding conflicts.
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "tools" / "root" / "usr" / "bin"
SHADERS = ROOT / "shaders"
SPV_OLD = ROOT / "artifacts" / "spv"
SPV_NEW = ROOT / "artifacts" / "spv_new"
REFLECT = ROOT / "artifacts" / "reflect"
REPORTS = ROOT / "artifacts" / "reports"

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import spirv  # noqa: E402
import reflect  # noqa: E402
import layout  # noqa: E402

STAGES = ["vert", "frag"]


def run(cmd):
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("failed: %s\n%s%s" % (cmd, proc.stdout, proc.stderr))
    return proc.stdout


def compile_shaders():
    SPV_NEW.mkdir(parents=True, exist_ok=True)
    for stage in STAGES:
        src = SHADERS / ("scene.%s" % stage)
        dst = SPV_NEW / ("scene.%s.spv" % stage)
        run([BIN / "glslangValidator", "-V", "--target-env", "vulkan1.0",
             src, "-o", dst])
        run([BIN / "spirv-val", dst])
    print("compile+validate: OK (%d modules)" % len(STAGES))


def reflect_all():
    REFLECT.mkdir(parents=True, exist_ok=True)
    results = {}
    for tag, directory in (("src", SPV_OLD), ("new", SPV_NEW)):
        for stage in STAGES:
            path = directory / ("scene.%s.spv" % stage)
            mod = spirv.parse(str(path))
            entry = reflect.reflect(mod, "scene.%s" % stage)
            results[(tag, stage)] = entry
            out = REFLECT / ("scene.%s.%s.json" % (stage, tag))
            out.write_text(json.dumps(entry, indent=1) + "\n")
    print("reflect: wrote %d json files" % len(results))
    return results


def validate_layouts():
    """Validate struct/array layout decorations for every block."""
    report = {}
    for stage in STAGES:
        path = SPV_NEW / ("scene.%s.spv" % stage)
        mod = spirv.parse(str(path))
        blocks = {}
        for var in mod.variables:
            if var["storage"] not in ("Uniform", "StorageBuffer",
                                      "PushConstant"):
                continue
            pointee = mod.types[var["type_id"]]["pointee"]
            if mod.types[pointee]["kind"] != "struct":
                continue
            decs = mod.decorations.get(pointee, {})
            if decs.get("Block"):
                blocks.setdefault(pointee, "std140")
            elif decs.get("BufferBlock"):
                blocks.setdefault(pointee, "std430")
        for struct_id, std in sorted(blocks.items()):
            name = mod.names.get(struct_id, "struct#%d" % struct_id)
            issues = layout.validate_block(mod, struct_id, std)
            engine = layout.LayoutEngine(mod, std)
            size, align = engine.type_layout(struct_id)
            member_decs = mod.member_decorations.get(struct_id, {})
            members = []
            for i, t, o in engine.struct_members(struct_id):
                entry = {"index": i, "offset": o,
                         "declaredOffset": member_decs.get(i, {}).get("Offset"),
                         "type": reflect.type_name(mod, t)}
                kind = mod.types[t]["kind"]
                if kind in ("array", "runtime_array"):
                    entry["stride"] = engine.array_stride(t)
                    entry["declaredStride"] = mod.decorations.get(
                        t, {}).get("ArrayStride")
                members.append(entry)
            report["%s:%s" % (stage, name)] = {
                "layout": std, "size": size, "align": align,
                "members": members,
                "issues": issues,
            }
    bad = {k: v for k, v in report.items() if v["issues"]}
    print("layout validation: %d blocks, %d with issues"
          % (len(report), len(bad)))
    return report


def build_manifest(results):
    """Merge per-stage reflections into a pipeline resource manifest."""
    merged = {}
    for (tag, stage), entry in results.items():
        if tag != "new":
            continue
        for desc in entry["descriptors"]:
            key = (desc["set"], desc["binding"])
            slot = merged.setdefault(key, {
                "set": desc["set"], "binding": desc["binding"],
                "type": desc["type"], "stages": [], "names": [],
                "size": desc.get("size"), "layout": desc.get("layout"),
            })
            slot["stages"].append(stage)
            slot["names"].append(desc["name"])
    manifest = {
        "descriptors": [merged[k] for k in sorted(merged)],
        "pushConstants": [],
        "interfaces": {},
    }
    for (tag, stage), entry in results.items():
        if tag != "new":
            continue
        for pc in entry["pushConstants"]:
            manifest["pushConstants"].append(
                {"stage": stage, "blockType": pc["blockType"],
                 "size": pc["size"]})
        manifest["interfaces"][stage] = {
            "inputs": entry["inputs"], "outputs": entry["outputs"]}
    return manifest


def find_conflicts(results, manifest):
    conflicts = []
    for (tag, stage), entry in results.items():
        if tag != "new":
            continue
        seen = {}
        for desc in entry["descriptors"]:
            key = (desc["set"], desc["binding"])
            if key in seen and seen[key] != desc["name"]:
                conflicts.append(
                    "%s: set=%d binding=%d used by both '%s' and '%s'"
                    % (stage, key[0], key[1], seen[key], desc["name"]))
            seen[key] = desc["name"]
    per_binding = {}
    for (tag, stage), entry in results.items():
        if tag != "new":
            continue
        for desc in entry["descriptors"]:
            key = (desc["set"], desc["binding"])
            prev = per_binding.setdefault(key, desc["type"])
            if prev != desc["type"]:
                conflicts.append(
                    "set=%d binding=%d type mismatch across stages: %s vs %s"
                    % (key[0], key[1], prev, desc["type"]))
    vout = {o["location"]: o for o in results[("new", "vert")]["outputs"]}
    fin = {i["location"]: i for i in results[("new", "frag")]["inputs"]}
    for loc in sorted(set(vout) & set(fin)):
        a, b = vout[loc], fin[loc]
        if a["type"] != b["type"] or a["flat"] != b["flat"]:
            conflicts.append(
                "location %d interface mismatch: vert %s(%s) vs frag %s(%s)"
                % (loc, a["type"], a["name"], b["type"], b["name"]))
    for loc in sorted(set(fin) - set(vout)):
        conflicts.append("fragment input location %d (%s) has no vertex output"
                         % (loc, fin[loc]["name"]))
    return conflicts


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    compile_shaders()
    results = reflect_all()
    layouts = validate_layouts()
    manifest = build_manifest(results)
    conflicts = find_conflicts(results, manifest)
    (REPORTS / "layouts.json").write_text(json.dumps(layouts, indent=1) + "\n")
    (REPORTS / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    (REPORTS / "conflicts.json").write_text(json.dumps(
        {"conflicts": conflicts}, indent=1) + "\n")
    print("manifest: %d descriptors, %d push constants"
          % (len(manifest["descriptors"]), len(manifest["pushConstants"])))
    print("conflicts: %d" % len(conflicts))
    for c in conflicts:
        print("  -", c)


if __name__ == "__main__":
    main()
