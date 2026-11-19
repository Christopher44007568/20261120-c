"""GLSL and HLSL code generation from an inferred material graph."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from . import nodes_builtins  # noqa: F401  ensure node kinds are registered
from . import nodes_math  # noqa: F401
from .analysis import topo_sort
from .graph import Graph
from .types import hlsl_name
from .vector import is_vec


@dataclass
class EmitContext:
    """Backend-aware helper passed to every node emission hook."""

    backend: str
    graph: Graph
    variables: Dict[Tuple[str, str], str] = field(default_factory=dict)
    statements: List[str] = field(default_factory=list)
    needs_checker: bool = False

    # ------------------------------------------------------------- naming
    def var_name(self, node_id: str, port: str) -> str:
        key = (node_id, port)
        if key not in self.variables:
            safe = "".join(ch if ch.isalnum() else "_" for ch in node_id)
            self.variables[key] = f"v_{safe}_{port}"
        return self.variables[key]

    def type_name(self, type_name: str) -> str:
        return type_name if self.backend == "glsl" else hlsl_name(type_name)

    # ---------------------------------------------------------- expressions
    def input_expr(self, node, port_name: str) -> str:
        edge = self.graph.driver(node.id, port_name)
        if edge is None:
            spec = node.spec.input_spec(port_name)
            return self.literal(spec.default, spec.type)
        src_node, src_port, _, _ = edge
        return self.var_name(src_node, src_port)

    def literal(self, value: Any, type_name: str) -> str:
        if self.backend == "hlsl":
            return self._hlsl_literal(value, type_name)
        return self._glsl_literal(value, type_name)

    def _number(self, number: Any) -> str:
        if isinstance(number, bool):
            return "true" if number else "false"
        if isinstance(number, int):
            return str(number)
        text = f"{float(number):.7g}"
        if "." not in text and "e" not in text and "inf" not in text:
            text += ".0"
        return text

    def _glsl_literal(self, value: Any, type_name: str) -> str:
        if not is_vec(value):
            return self._number(value)
        parts = ", ".join(self._number(item) for item in value)
        return f"{self.type_name(type_name)}({parts})"

    def _hlsl_literal(self, value: Any, type_name: str) -> str:
        if not is_vec(value):
            return self._number(value)
        parts = ", ".join(self._number(item) for item in value)
        return f"{self.type_name(type_name)}({parts})"

    def construct(self, base: str, width: int, parts: List[str]) -> str:
        from .types import make_vector
        return f"{self.type_name(make_vector(base, width))}({', '.join(parts)})"

    # ------------------------------------------------------------ built-ins
    def uv_expr(self) -> str:
        return "v_uv"

    def time_expr(self) -> str:
        return "u_time"

    def normal_expr(self) -> str:
        return "v_normal"

    def func(self, glsl_name: str) -> str:
        """Translate a GLSL intrinsic name to the active backend spelling."""
        if self.backend != "hlsl":
            return glsl_name
        return {
            "mix": "lerp",
            "fract": "frac",
            "mod": "fmod",
        }.get(glsl_name, glsl_name)

    def checker_expr(self, uv: str, scale: float, color_a: str,
                     color_b: str) -> str:
        self.needs_checker = True
        return f"mg_checker({uv}, {self._number(scale)}, {color_a}, {color_b})"

    # ------------------------------------------------------------- emission
    def assign(self, node, port: str, expression: str) -> str:
        target = self.var_name(node.id, port)
        type_name = self.type_name(node.types[port])
        return f"    {type_name} {target} = {expression};"

    def surface_output(self, node, color: str, roughness: str,
                       metallic: str, emission: str) -> List[str]:
        if self.backend == "glsl":
            return [
                f"    out_base_color = {color};",
                f"    out_roughness = {roughness};",
                f"    out_metallic = {metallic};",
                f"    out_emission = {emission};",
            ]
        return [
            f"    result.base_color = {color};",
            f"    result.roughness = {roughness};",
            f"    result.metallic = {metallic};",
            f"    result.emission = {emission};",
            "    return result;",
        ]


def _emit_body(graph: Graph, backend: str) -> Tuple[EmitContext, List[str]]:
    context = EmitContext(backend=backend, graph=graph)
    body: List[str] = []
    for node_id in topo_sort(graph):
        node = graph.nodes[node_id]
        spec = node.spec
        if spec.emit is None:
            raise ValueError(f"node kind {spec.kind!r} cannot emit shader code")
        lines = spec.emit(node, context)
        for line in lines:
            if isinstance(line, (list, tuple)):
                body.extend(line)
            else:
                body.append(line)
    return context, body


def generate_glsl(graph: Graph) -> str:
    """Generate a standalone GLSL 450 fragment shader from the graph."""
    context, body = _emit_body(graph, "glsl")
    helpers = _glsl_helpers(context)
    lines = [
        "#version 450",
        "// Generated by matgraph - do not edit by hand.",
        "layout(location = 0) in vec2 v_uv;",
        "layout(location = 1) in vec3 v_normal;",
        "layout(location = 0) out vec3 out_base_color;",
        "layout(location = 1) out float out_roughness;",
        "layout(location = 2) out float out_metallic;",
        "layout(location = 3) out vec3 out_emission;",
        "layout(set = 0, binding = 0) uniform MaterialBlock {",
        "    float u_time;",
        "};",
        "",
    ]
    lines.extend(helpers)
    lines.extend(["void main()", "{"])
    lines.extend(body)
    lines.extend(["}", ""])
    return "\n".join(lines)


def _glsl_helpers(context: EmitContext) -> List[str]:
    if not context.needs_checker:
        return []
    return [
        "vec3 mg_checker(vec2 uv, float scale, vec3 a, vec3 b) {",
        "    ivec2 cell = ivec2(floor(uv * scale));",
        "    float pick = mod(float(cell.x + cell.y), 2.0);",
        "    return mix(a, b, step(0.5, pick));",
        "}",
        "",
    ]


def generate_hlsl(graph: Graph) -> str:
    """Generate a standalone HLSL shader model 6.0 pixel shader."""
    context, body = _emit_body(graph, "hlsl")
    helpers = _hlsl_helpers(context)
    lines = [
        "// Generated by matgraph - do not edit by hand.",
        "struct MaterialVsOut {",
        "    float4 position : SV_Position;",
        "    float2 uv : TEXCOORD0;",
        "    float3 normal : NORMAL0;",
        "};",
        "struct SurfaceResult {",
        "    float3 base_color;",
        "    float roughness;",
        "    float metallic;",
        "    float3 emission;",
        "};",
        "cbuffer MaterialConstants : register(b0) {",
        "    float u_time;",
        "};",
        "",
    ]
    lines.extend(helpers)
    lines.extend([
        "SurfaceResult mg_surface(MaterialVsOut input) {",
        "    float2 v_uv = input.uv;",
        "    float3 v_normal = input.normal;",
        "    SurfaceResult result;",
    ])
    lines.extend(body)
    lines.extend(["}", "",
                  "SurfaceResult main_ps(MaterialVsOut input) : SV_Target0 {",
                  "    return mg_surface(input);",
                  "}", ""])
    return "\n".join(lines)


def _hlsl_helpers(context: EmitContext) -> List[str]:
    if not context.needs_checker:
        return []
    return [
        "float3 mg_checker(float2 uv, float scale, float3 a, float3 b) {",
        "    int2 cell = int2(floor(uv * scale));",
        "    float pick = fmod(float(cell.x + cell.y), 2.0);",
        "    return lerp(a, b, step(0.5, pick));",
        "}",
        "",
    ]


def generate_shader(graph: Graph, backend: str = "glsl") -> str:
    """Dispatch shader generation for ``backend`` in ``{glsl, hlsl}``."""
    if backend == "glsl":
        return generate_glsl(graph)
    if backend == "hlsl":
        return generate_hlsl(graph)
    raise ValueError(f"unknown shader backend: {backend}")
