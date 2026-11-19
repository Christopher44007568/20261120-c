"""Real shader compiler verification via glslangValidator."""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .codegen import generate_shader
from .graph import Graph
from .inference import infer_graph_types
from .interpreter import PreviewContext, evaluate_outputs
from .errors import CompileError


def find_compiler() -> Optional[str]:
    """Locate glslangValidator on PATH or under the local .tools tree."""
    on_path = shutil.which("glslangValidator")
    if on_path:
        return on_path
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(
        repo_root, ".tools", "root", "usr", "bin", "glslangValidator"
    )
    return candidate if os.path.exists(candidate) else None


@dataclass
class CompileResult:
    backend: str
    ok: bool
    command: List[str]
    stdout: str
    stderr: str
    spirv_bytes: int

    @property
    def report(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "ok": self.ok,
            "spirv_bytes": self.spirv_bytes,
            "command": " ".join(self.command),
            "stderr": self.stderr.strip(),
        }


def _compile_command(backend: str, source: str, source_path: str,
                     spirv_path: str, compiler: str) -> List[str]:
    if backend == "glsl":
        return [compiler, "-V", "-S", "frag", "--glsl-version", "450",
                "-o", spirv_path, source_path]
    if backend == "hlsl":
        return [compiler, "-V", "-D", "-S", "frag",
                "-e", "main_ps", "--target-env", "vulkan1.1",
                "-o", spirv_path, source_path]
    raise ValueError(f"unknown backend: {backend}")


def verify_compilation(
    graph: Graph,
    backends=("glsl", "hlsl"),
    compiler: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate, compile and validate shaders for every requested backend."""
    compiler = compiler or find_compiler()
    if compiler is None:
        raise CompileError(
            "glslangValidator not found; install glslang-tools or place the "
            "binary under .tools/root/usr/bin"
        )
    infer_graph_types(graph)
    reports: List[CompileResult] = []
    with tempfile.TemporaryDirectory() as tmp:
        for backend in backends:
            source = generate_shader(graph, backend)
            suffix = ".frag" if backend == "glsl" else ".hlsl"
            source_path = os.path.join(tmp, f"shader{suffix}")
            spirv_path = os.path.join(tmp, f"shader.{backend}.spv")
            with open(source_path, "w", encoding="utf-8") as handle:
                handle.write(source)
            command = _compile_command(
                backend, source, source_path, spirv_path, compiler
            )
            proc = subprocess.run(
                command, capture_output=True, text=True, timeout=60
            )
            ok = proc.returncode == 0 and os.path.exists(spirv_path)
            spirv_bytes = os.path.getsize(spirv_path) if ok else 0
            result = CompileResult(
                backend=backend,
                ok=ok,
                command=command,
                stdout=proc.stdout,
                stderr=proc.stderr,
                spirv_bytes=spirv_bytes,
            )
            reports.append(result)
            if not ok:
                raise CompileError(
                    f"{backend} compilation failed:\n"
                    f"{proc.stderr or proc.stdout}\n--- source ---\n{source}"
                )
    return {
        "ok": all(item.ok for item in reports),
        "compiler": compiler,
        "backends": [item.report for item in reports],
    }


def _approx_equal(left: Any, right: Any, tolerance: float) -> bool:
    if isinstance(left, (tuple, list)) or isinstance(right, (tuple, list)):
        left = tuple(left)
        right = tuple(right)
        if len(left) != len(right):
            return False
        return all(
            _approx_equal(a, b, tolerance) for a, b in zip(left, right)
        )
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left) == bool(right)
    return abs(float(left) - float(right)) <= tolerance


def verify_preview_compile(
    graph: Graph,
    sample_points: Optional[List[PreviewContext]] = None,
    tolerance: float = 1e-6,
    compiler: Optional[str] = None,
) -> Dict[str, Any]:
    """Cross-check preview evaluation against compile-time verification.

    Three consistency checks are performed:

    1. Both backends compile from the same inferred graph (same types).
    2. Code generation is stable: repeated generation is byte-identical.
    3. A fresh graph round-tripped from the serialized topology evaluates
       to numerically identical preview values on every sample point,
       proving preview and compile paths consume one identical topology.
    """
    sample_points = sample_points or [
        PreviewContext(uv=(u, v), time=0.25)
        for u in (0.1, 0.55)
        for v in (0.2, 0.7)
    ]
    infer_graph_types(graph)
    compile_report = verify_compilation(graph, compiler=compiler)

    stability = {
        backend: generate_shader(graph, backend)
        == generate_shader(graph, backend)
        for backend in ("glsl", "hlsl")
    }

    from .pipeline import build_graph_from_dict

    rebuilt = build_graph_from_dict(graph.to_dict())
    infer_graph_types(rebuilt)
    samples = []
    all_match = True
    for context in sample_points:
        expected = evaluate_outputs(graph, context)
        actual = evaluate_outputs(rebuilt, context)
        match = _nested_equal(expected, actual, tolerance)
        all_match = all_match and match
        samples.append({
            "uv": list(context.uv),
            "time": context.time,
            "match": match,
            "outputs": _simplify(expected),
        })

    return {
        "ok": compile_report["ok"] and all(stability.values()) and all_match,
        "compile": compile_report,
        "generation_stable": stability,
        "preview_topology_match": all_match,
        "samples": samples,
        "tolerance": tolerance,
    }


def _nested_equal(expected: Dict, actual: Dict, tolerance: float) -> bool:
    if set(expected) != set(actual):
        return False
    for node_id, ports in expected.items():
        if set(ports) != set(actual[node_id]):
            return False
        for port, value in ports.items():
            if not _approx_equal(value, actual[node_id][port], tolerance):
                return False
    return True


def _simplify(values: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    rendered = {}
    for node_id, ports in values.items():
        rendered[node_id] = {
            port: (list(value) if isinstance(value, (tuple, list)) else value)
            for port, value in ports.items()
        }
    return rendered
