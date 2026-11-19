"""Built-in arithmetic, vector math and comparison nodes."""

from . import vector as vec
from .registry import NodeSpec, PortSpec, register_node
from .types import infer_binary, make_vector, scalar_base, vector_components


def _binary_infer(node, input_types):
    return {"out": infer_binary(input_types["a"], input_types["b"])}


def _binary_eval(operator):
    def evaluate(node, inputs):
        return {
            "out": vec.map_components(operator, inputs["a"], inputs["b"])
        }
    return evaluate


def _binary_emit(op_token):
    def emit(node, ctx):
        expr = f"({ctx.input_expr(node, 'a')} {op_token} " \
               f"{ctx.input_expr(node, 'b')})"
        return [ctx.assign(node, "out", expr)]
    return emit


for _kind, _op, _token in (
    ("Add", lambda a, b: a + b, "+"),
    ("Subtract", lambda a, b: a - b, "-"),
    ("Multiply", lambda a, b: a * b, "*"),
    ("Divide", lambda a, b: a / b, "/"),
):
    register_node(NodeSpec(
        kind=_kind,
        category="math",
        inputs=[PortSpec("a", "any"), PortSpec("b", "any")],
        outputs=[PortSpec("out", "any")],
        infer=_binary_infer,
        evaluate=_binary_eval(_op),
        emit=_binary_emit(_token),
    ))


# ------------------------------------------------------------------- unary
def _unary_infer(node, input_types):
    return {"out": input_types["in"]}


_UNARY = {
    "Negate": (lambda x: -x, "-"),
    "Abs": (abs, None),
    "Saturate": (lambda x: vec.clamp(x, 0.0, 1.0), None),
    "Normalize": (vec.normalize, None),
}


def _unary_emit(node, ctx):
    kind = node.kind
    inner = ctx.input_expr(node, "in")
    if kind == "Negate":
        expr = f"(-{inner})"
    elif kind == "Abs":
        expr = f"abs({inner})"
    elif kind == "Saturate":
        expr = f"clamp({inner}, 0.0, 1.0)"
    else:
        expr = f"normalize({inner})"
    return [ctx.assign(node, "out", expr)]


for _kind, (_py, _token) in _UNARY.items():
    register_node(NodeSpec(
        kind=_kind,
        category="math",
        inputs=[PortSpec("in", "any")],
        outputs=[PortSpec("out", "any")],
        infer=_unary_infer,
        evaluate=(lambda fn: lambda node, inputs:
                  {"out": vec.map_unary(fn, inputs["in"])})(_py),
        emit=_unary_emit,
    ))


# ------------------------------------------------------------ scalar math
def _float1_infer(node, input_types):
    if scalar_base(input_types["in"]) not in ("float", "int"):
        raise TypeError(f"{node.kind} requires numeric input")
    return {"out": input_types["in"]}


_FLOAT1_FUNCS = {
    "Sin": (lambda x: vec.map_unary(__import__("math").sin, x), "sin"),
    "Cos": (lambda x: vec.map_unary(__import__("math").cos, x), "cos"),
    "Sqrt": (lambda x: vec.map_unary(__import__("math").sqrt, x), "sqrt"),
    "Fract": (vec.fract, "fract"),
    "Floor": (lambda x: vec.map_unary(
        lambda i: float(__import__("math").floor(i)), x), "floor"),
}


def _float1_emit(node, ctx):
    token = ctx.func(_FLOAT1_FUNCS[node.kind][1])
    return [ctx.assign(
        node, "out", f"{token}({ctx.input_expr(node, 'in')})"
    )]


for _kind, (_py, _glsl) in _FLOAT1_FUNCS.items():
    register_node(NodeSpec(
        kind=_kind,
        category="math",
        inputs=[PortSpec("in", "any")],
        outputs=[PortSpec("out", "any")],
        infer=_float1_infer,
        evaluate=(lambda fn: lambda node, inputs:
                  {"out": fn(inputs["in"])})(_py),
        emit=_float1_emit,
    ))


# ------------------------------------------------------------ vector math
register_node(NodeSpec(
    kind="Dot",
    category="vector",
    inputs=[PortSpec("a", "any"), PortSpec("b", "any")],
    outputs=[PortSpec("out", "float")],
    infer=lambda node, inputs: {"out": "float"},
    evaluate=lambda node, inputs: {"out": vec.dot(inputs["a"], inputs["b"])},
    emit=lambda node, ctx: [ctx.assign(
        node, "out",
        f"dot({ctx.input_expr(node, 'a')}, {ctx.input_expr(node, 'b')})"
    )],
))


register_node(NodeSpec(
    kind="Cross",
    category="vector",
    inputs=[PortSpec("a", "vec3"), PortSpec("b", "vec3")],
    outputs=[PortSpec("out", "vec3")],
    infer=lambda node, inputs: {"out": "vec3"},
    evaluate=lambda node, inputs: {
        "out": vec.cross(inputs["a"], inputs["b"])
    },
    emit=lambda node, ctx: [ctx.assign(
        node, "out",
        f"cross({ctx.input_expr(node, 'a')}, {ctx.input_expr(node, 'b')})"
    )],
))


register_node(NodeSpec(
    kind="Length",
    category="vector",
    inputs=[PortSpec("in", "any")],
    outputs=[PortSpec("out", "float")],
    infer=lambda node, inputs: {"out": "float"},
    evaluate=lambda node, inputs: {"out": vec.length_of(inputs["in"])},
    emit=lambda node, ctx: [ctx.assign(
        node, "out", f"length({ctx.input_expr(node, 'in')})"
    )],
))


# ------------------------------------------------------------- interpolation
def _mix_infer(node, input_types):
    return {"out": infer_binary(input_types["a"], input_types["b"])}


register_node(NodeSpec(
    kind="Mix",
    category="math",
    inputs=[
        PortSpec("a", "any"),
        PortSpec("b", "any"),
        PortSpec("t", "float"),
    ],
    outputs=[PortSpec("out", "any")],
    infer=_mix_infer,
    evaluate=lambda node, inputs: {
        "out": vec.mix(inputs["a"], inputs["b"], inputs["t"])
    },
    emit=lambda node, ctx: [ctx.assign(
        node, "out",
        f"{ctx.func('mix')}({ctx.input_expr(node, 'a')}, "
        f"{ctx.input_expr(node, 'b')}, {ctx.input_expr(node, 't')})"
    )],
))


register_node(NodeSpec(
    kind="Step",
    category="math",
    inputs=[PortSpec("edge", "any"), PortSpec("x", "any")],
    outputs=[PortSpec("out", "any")],
    infer=lambda node, inputs: {
        "out": infer_binary(inputs["edge"], inputs["x"])
    },
    evaluate=lambda node, inputs: {
        "out": vec.step(inputs["edge"], inputs["x"])
    },
    emit=lambda node, ctx: [ctx.assign(
        node, "out",
        f"step({ctx.input_expr(node, 'edge')}, "
        f"{ctx.input_expr(node, 'x')})"
    )],
))


register_node(NodeSpec(
    kind="SmoothStep",
    category="math",
    inputs=[
        PortSpec("edge0", "any"),
        PortSpec("edge1", "any"),
        PortSpec("x", "any"),
    ],
    outputs=[PortSpec("out", "any")],
    infer=lambda node, inputs: {
        "out": infer_binary(inputs["edge0"], inputs["edge1"])
    },
    evaluate=lambda node, inputs: {
        "out": vec.smoothstep(
            inputs["edge0"], inputs["edge1"], inputs["x"]
        )
    },
    emit=lambda node, ctx: [ctx.assign(
        node, "out",
        f"smoothstep({ctx.input_expr(node, 'edge0')}, "
        f"{ctx.input_expr(node, 'edge1')}, {ctx.input_expr(node, 'x')})"
    )],
))


# ------------------------------------------------------------- comparisons
def _compare_infer(node, input_types):
    left, right = input_types["a"], input_types["b"]
    if scalar_base(left) != scalar_base(right):
        raise TypeError(f"cannot compare {left} with {right}")
    width = max(vector_components(left), vector_components(right))
    return {"out": make_vector("bool", width)}


_COMPARE_OPS = {
    "Less": ("<", lambda a, b: a < b),
    "LessEqual": ("<=", lambda a, b: a <= b),
    "Greater": (">", lambda a, b: a > b),
    "GreaterEqual": (">=", lambda a, b: a >= b),
    "Equal": ("==", lambda a, b: a == b),
}


def _make_compare(token, pyop):
    def emit(node, ctx):
        return [ctx.assign(
            node, "out",
            f"({ctx.input_expr(node, 'a')} {token} "
            f"{ctx.input_expr(node, 'b')})"
        )]

    def evaluate(node, inputs):
        return {
            "out": vec.map_components(pyop, inputs["a"], inputs["b"])
        }
    return emit, evaluate


for _kind, (_token, _py) in _COMPARE_OPS.items():
    _emit, _eval = _make_compare(_token, _py)
    register_node(NodeSpec(
        kind=_kind,
        category="logic",
        inputs=[PortSpec("a", "any"), PortSpec("b", "any")],
        outputs=[PortSpec("out", "any")],
        infer=_compare_infer,
        evaluate=_eval,
        emit=_emit,
    ))
