"""Built-in source, constant, vector and surface output nodes."""

from . import vector as v
from .registry import NodeSpec, PortSpec, register_node
from .types import make_vector, type_rank


# --------------------------------------------------------------- constants
def _const_infer(node, input_types):
    return {"out": node.params["type"]}


def _const_eval(node, inputs):
    value = node.params["value"]
    type_name = node.params["type"]
    if type_rank(type_name) > 1 and not isinstance(value, (tuple, list)):
        value = tuple([value] * type_rank(type_name))
    return {"out": value}


def _const_emit(node, ctx):
    return [ctx.assign(node, "out", ctx.literal(node.params["value"],
                                                node.params["type"]))]


register_node(NodeSpec(
    kind="Const",
    category="source",
    outputs=[PortSpec("out", "any")],
    params={"value": 0.0, "type": "float"},
    infer=_const_infer,
    evaluate=_const_eval,
    emit=_const_emit,
))


def _uv_infer(node, input_types):
    return {"out": "vec2"}


def _uv_emit(node, ctx):
    return [ctx.assign(node, "out", ctx.uv_expr())]


register_node(NodeSpec(
    kind="UV",
    category="input",
    outputs=[PortSpec("out", "vec2")],
    infer=_uv_infer,
    evaluate=lambda node, inputs: {"out": tuple(node.params["uv"])},
    emit=_uv_emit,
    params={"uv": (0.0, 0.0)},
))


def _time_infer(node, input_types):
    return {"out": "float"}


register_node(NodeSpec(
    kind="Time",
    category="input",
    outputs=[PortSpec("out", "float")],
    infer=_time_infer,
    evaluate=lambda node, inputs: {"out": float(node.params["time"])},
    emit=lambda node, ctx: [ctx.assign(node, "out", ctx.time_expr())],
    params={"time": 0.0},
))


def _normal_infer(node, input_types):
    return {"out": "vec3"}


register_node(NodeSpec(
    kind="Normal",
    category="input",
    outputs=[PortSpec("out", "vec3")],
    infer=_normal_infer,
    evaluate=lambda node, inputs: {"out": (0.0, 0.0, 1.0)},
    emit=lambda node, ctx: [ctx.assign(node, "out", ctx.normal_expr())],
))


# ------------------------------------------------------------- constructors
def _combine_infer(node, input_types):
    width = node.params["components"]
    return {"out": make_vector("float", width)}


def _combine_emit(node, ctx):
    width = node.params["components"]
    parts = [ctx.input_expr(node, f"c{i}") for i in range(width)]
    return [ctx.assign(node, "out", ctx.construct("float", width, parts))]


register_node(NodeSpec(
    kind="Combine",
    category="vector",
    inputs=[PortSpec(f"c{i}", "float", required=False) for i in range(4)],
    outputs=[PortSpec("out", "any")],
    params={"components": 4},
    infer=_combine_infer,
    evaluate=lambda node, inputs: {
        "out": v.construct([inputs[f"c{i}"]
                            for i in range(node.params["components"])
                            if f"c{i}" in inputs])
    },
    emit=_combine_emit,
))


def _swizzle_infer(node, input_types):
    channels = node.params["channels"]
    width = len(channels)
    return {"out": make_vector("float", width)}


register_node(NodeSpec(
    kind="Swizzle",
    category="vector",
    inputs=[PortSpec("in", "any")],
    outputs=[PortSpec("out", "any")],
    params={"channels": "x"},
    infer=_swizzle_infer,
    evaluate=lambda node, inputs: {
        "out": v.swizzle(inputs["in"], node.params["channels"])
    },
    emit=lambda node, ctx: [
        ctx.assign(
            node, "out",
            f"{ctx.input_expr(node, 'in')}.{node.params['channels']}"
        )
    ],
))


# ------------------------------------------------------------- procedural
def _checker_eval(node, inputs):
    uv = v.as_vec(inputs["uv"], 2)
    scale = node.params["scale"]
    cells = (math_floor(uv[0] * scale), math_floor(uv[1] * scale))
    flag = (cells[0] + cells[1]) % 2 == 0
    color_a = node.params["color_a"]
    color_b = node.params["color_b"]
    return {"rgb": tuple(color_a if flag else color_b)}


def math_floor(value):
    import math
    return int(math.floor(value))


def _checker_emit(node, ctx):
    return [
        ctx.assign(
            node, "rgb",
            ctx.checker_expr(
                ctx.input_expr(node, "uv"),
                node.params["scale"],
                ctx.literal(tuple(node.params["color_a"]), "vec3"),
                ctx.literal(tuple(node.params["color_b"]), "vec3"),
            )
        )
    ]


register_node(NodeSpec(
    kind="Checker",
    category="procedural",
    inputs=[PortSpec("uv", "vec2", required=False, default=(0.0, 0.0))],
    outputs=[PortSpec("rgb", "vec3")],
    params={"scale": 8.0,
            "color_a": (0.9, 0.9, 0.9),
            "color_b": (0.1, 0.1, 0.1)},
    infer=lambda node, inputs: {"rgb": "vec3"},
    evaluate=_checker_eval,
    emit=_checker_emit,
))


# ----------------------------------------------------------------- output
def _surface_infer(node, input_types):
    return {}


def _surface_emit(node, ctx):
    return [ctx.surface_output(
        node,
        ctx.input_expr(node, "base_color"),
        ctx.input_expr(node, "roughness"),
        ctx.input_expr(node, "metallic"),
        ctx.input_expr(node, "emission"),
    )]


register_node(NodeSpec(
    kind="SurfaceOutput",
    category="output",
    inputs=[
        PortSpec("base_color", "vec3", required=False,
                 default=(0.8, 0.8, 0.8)),
        PortSpec("roughness", "float", required=False, default=0.5),
        PortSpec("metallic", "float", required=False, default=0.0),
        PortSpec("emission", "vec3", required=False, default=(0.0, 0.0, 0.0)),
    ],
    outputs=[],
    infer=_surface_infer,
    evaluate=lambda node, inputs: {
        "base_color": inputs["base_color"],
        "roughness": inputs["roughness"],
        "metallic": inputs["metallic"],
        "emission": inputs["emission"],
    },
    emit=_surface_emit,
    is_output=True,
))
