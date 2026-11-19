"""Small fixed-width vector helpers used by the CPU interpreter.

Values are plain Python numbers (scalar) or tuples of numbers. This
mirrors GLSL/HLSL semantics closely enough for material preview math.
"""

import math
from typing import Any, Sequence, Tuple

from .types import scalar_base, vector_components

Value = Any
SWIZZLE = {"x": 0, "y": 1, "z": 2, "w": 3,
           "r": 0, "g": 1, "b": 2, "a": 3}


def is_vec(value: Value) -> bool:
    return isinstance(value, (tuple, list))


def width(value: Value) -> int:
    return len(value) if is_vec(value) else 1


def as_vec(value: Value, components: int) -> Tuple:
    """Broadcast a scalar or resize a vector to ``components``."""
    if not is_vec(value):
        return tuple([value] * components)
    if len(value) == components:
        return tuple(value)
    if len(value) == 1:
        return tuple([value[0]] * components)
    raise TypeError(f"cannot resize vector of width {len(value)} to {components}")


def component_type(value: Value) -> str:
    sample = value[0] if is_vec(value) else value
    if isinstance(sample, bool):
        return "bool"
    if isinstance(sample, int):
        return "int"
    return "float"


def map_components(function, left: Value, right: Value) -> Value:
    """Apply a binary op component-wise with scalar broadcasting."""
    if is_vec(left) or is_vec(right):
        components = max(width(left), width(right))
        if components == 1:
            lv = left[0] if is_vec(left) else left
            rv = right[0] if is_vec(right) else right
            return function(lv, rv)
        lv = as_vec(left, components)
        rv = as_vec(right, components)
        return tuple(function(a, b) for a, b in zip(lv, rv))
    return function(left, right)


def map_unary(function, value: Value) -> Value:
    if is_vec(value):
        return tuple(function(item) for item in value)
    return function(value)


def swizzle(value: Value, channels: str) -> Value:
    indices = [SWIZZLE[ch] for ch in channels]
    if not is_vec(value):
        value = (value,)
    for index in indices:
        if index >= len(value):
            raise TypeError(f"swizzle .{channels} exceeds vector width")
    result = tuple(value[index] for index in indices)
    return result[0] if len(result) == 1 else result


def construct(components: Sequence[Value]) -> Value:
    """GLSL-style constructor: flatten scalars/vectors and take/size them."""
    flat = []
    for part in components:
        flat.extend(part if is_vec(part) else [part])
    if len(flat) == 1:
        return flat[0]
    return tuple(flat)


def value_type(value: Value) -> str:
    base = component_type(value)
    components = width(value)
    if components == 1:
        return base
    if base == "float":
        return f"vec{components}"
    if base == "int":
        return f"ivec{components}"
    return f"bvec{components}"


def clamp(value: Value, low: float, high: float) -> Value:
    return map_unary(lambda item: min(max(item, low), high), value)


def fract(value: Value) -> Value:
    return map_unary(lambda item: item - math.floor(item), value)


def mix(left: Value, right: Value, amount: Value) -> Value:
    def blend(a, b, t):
        return a * (1.0 - t) + b * t

    components = max(width(left), width(right))
    if components == 1:
        lv = left[0] if is_vec(left) else left
        rv = right[0] if is_vec(right) else right
        tv = amount[0] if is_vec(amount) else amount
        return blend(lv, rv, tv)
    lv = as_vec(left, components)
    rv = as_vec(right, components)
    tv = as_vec(amount, components)
    return tuple(blend(a, b, t) for a, b, t in zip(lv, rv, tv))


def step(edge: Value, value: Value) -> Value:
    return map_components(
        lambda e, v: 1.0 if v >= e else 0.0, edge, value
    )


def smoothstep(edge0: Value, edge1: Value, value: Value) -> Value:
    def core(a, b, x):
        if a == b:
            return 0.0
        t = min(max((x - a) / (b - a), 0.0), 1.0)
        return t * t * (3.0 - 2.0 * t)

    components = max(width(edge0), width(edge1), width(value))
    a = as_vec(edge0, components)
    b = as_vec(edge1, components)
    x = as_vec(value, components)
    return tuple(core(i, j, k) for i, j, k in zip(a, b, x))


def dot(left: Value, right: Value) -> float:
    components = max(width(left), width(right))
    lv = as_vec(left, components)
    rv = as_vec(right, components)
    return sum(a * b for a, b in zip(lv, rv))


def normalize(value: Value) -> Value:
    if not is_vec(value):
        return 1.0
    length = math.sqrt(sum(item * item for item in value))
    if length == 0.0:
        return tuple(0.0 for _ in value)
    return tuple(item / length for item in value)


def cross(left: Value, right: Value) -> Value:
    a, b = as_vec(left, 3), as_vec(right, 3)
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length_of(value: Value) -> float:
    if not is_vec(value):
        return abs(value)
    return math.sqrt(sum(item * item for item in value))


def type_matches(value: Value, type_name: str) -> bool:
    return scalar_base(type_name) == component_type(value) and (
        vector_components(type_name) == width(value)
    )
