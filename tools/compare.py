"""Consistency checks: source vs transpiled SPIR-V, and round-trip
(SPIR-V to GLSL to SPIR-V) reflection equivalence."""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "tools" / "root" / "usr" / "bin"
SPV_OLD = ROOT / "artifacts" / "spv"
SPV_NEW = ROOT / "artifacts" / "spv_new"
RT = ROOT / "artifacts" / "roundtrip"
REFLECT = ROOT / "artifacts" / "reflect"
REPORTS = ROOT / "artifacts" / "reports"

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import spirv  # noqa: E402
import reflect  # noqa: E402

STAGES = ["vert", "frag"]


def run(cmd, allow_fail=False):
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if proc.returncode != 0 and not allow_fail:
        raise RuntimeError("failed: %s\n%s%s" % (cmd, proc.stdout, proc.stderr))
    return proc


def canonical(entry):
    out = dict(entry)
    out.pop("module", None)
    out.pop("spirvVersion", None)
    return out


def roundtrip():
    RT.mkdir(parents=True, exist_ok=True)
    results = {}
    for stage in STAGES:
        spv = SPV_NEW / ("scene.%s.spv" % stage)
        glsl = RT / ("scene.%s.glsl" % stage)
        out = RT / ("scene.%s.spv" % stage)
        decompiled = run([BIN / "spirv-cross", spv, "--vulkan-semantics",
                          "--version", "450"]).stdout
        glsl.write_text(decompiled)
        run([BIN / "glslangValidator", "-V", "--target-env", "vulkan1.0",
             glsl, "-o", out])
        run([BIN / "spirv-val", out])
        mod = spirv.parse(str(out))
        results[stage] = reflect.reflect(mod, "scene.%s" % stage)
        (REFLECT / ("scene.%s.roundtrip.json" % stage)).write_text(
            json.dumps(results[stage], indent=1) + "\n")
    print("roundtrip: decompiled + recompiled %d modules" % len(STAGES))
    return results


def compare_reflections(rt_results):
    checks = []
    for stage in STAGES:
        src = json.loads((REFLECT / ("scene.%s.src.json" % stage)).read_text())
        new = json.loads((REFLECT / ("scene.%s.new.json" % stage)).read_text())
        rt = rt_results[stage]
        checks.append({
            "stage": stage,
            "src_vs_new": canonical(src) == canonical(new),
            "new_vs_roundtrip": canonical(new) == canonical(rt),
        })
    return checks


def semantic_diff():
    """spirv-diff on debug-stripped binaries: 0 logical changes means the
    modules compute identically (same rendering results)."""
    outcome = {}
    for stage in STAGES:
        stripped = []
        for tag, directory in (("src", SPV_OLD), ("new", SPV_NEW)):
            dst = RT / ("strip.%s.%s.spv" % (tag, stage))
            run([BIN / "spirv-opt", "--strip-debug",
                 directory / ("scene.%s.spv" % stage), "-o", dst])
            stripped.append(dst)
        proc = run([BIN / "spirv-diff", "--no-color", stripped[0],
                    stripped[1]])
        changes = [l for l in proc.stdout.splitlines()
                   if l.startswith("+") or l.startswith("-")]
        outcome[stage] = {"logicalChanges": len(changes)}
    return outcome


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    rt_results = roundtrip()
    checks = compare_reflections(rt_results)
    diff = semantic_diff()
    report = {"reflectionChecks": checks, "semanticDiff": diff}
    (REPORTS / "compare.json").write_text(json.dumps(report, indent=1) + "\n")
    ok = all(c["src_vs_new"] and c["new_vs_roundtrip"] for c in checks)
    ok = ok and all(d["logicalChanges"] == 0 for d in diff.values())
    print("reflection checks:", checks)
    print("semantic diff:", diff)
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
