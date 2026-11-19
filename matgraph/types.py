"""Shader type system shared by inference, interpreter and code generation."""

FLOAT_TYPES = ("float", "vec2", "vec3", "vec4")
INT_TYPES = ("int", "ivec2", "ivec3", "ivec4")
BOOL_TYPES = ("bool", "bvec2", "bvec3", "bvec4")

SCALAR_TYPES = ("float", "int", "bool")
VECTOR_TYPES = FLOAT_TYPES[1:] + INT_TYPES[1:] + BOOL_TYPES[1:]
ALL_TYPES = FLOAT_TYPES + INT_TYPES[1:] + BOOL_TYPES

_RANK = {name: i + 1 for i, name in enumerate(ALL_TYPES)}
_BASE = {}
for group in (FLOAT_TYPES, INT_TYPES, BOOL_TYPES):
    for name in group:
        _BASE[name] = group[0]
_COMPONENTS = {
    name: 1 if name in SCALAR_TYPES else int(name[-1]) for name in ALL_TYPES
}

# Shader spelling per backend (HLSL uses vector<T,N> style names).
HLSL_NAMES = {
    "float": "float",
    "vec2": "float2",
    "vec3": "float3",
    "vec4": "float4",
    "int": "int",
    "ivec2": "int2",
    "ivec3": "int3",
    "ivec4": "int4",
    "bool": "bool",
    "bvec2": "bool2",
    "bvec3": "bool3",
    "bvec4": "bool4",
}


def type_rank(name):
    """Return the 1..4 component rank of a type."""
    try:
        return _COMPONENTS[name]
    except KeyError as exc:
        raise ValueError(f"unknown type: {name}") from exc


def scalar_base(name):
    """Return the scalar base type: float, int or bool."""
    try:
        return _BASE[name]
    except KeyError as exc:
        raise ValueError(f"unknown type: {name}") from exc


def vector_components(name):
    """Return how many components the type has (1..4)."""
    return type_rank(name)


def is_vector(name):
    return type_rank(name) > 1


def is_numeric(name):
    return scalar_base(name) in ("float", "int")


def make_vector(base, components):
    """Build a vector type name from a scalar base and component count."""
    if components == 1:
        return base
    prefix = {"float": "v", "int": "ivec", "bool": "bvec"}[base]
    if base == "float":
        return f"vec{components}"
    return f"{prefix}{components}"


def infer_binary(left, right):
    """Infer the result type of an arithmetic/multiply expression.

    Rules (mirroring GLSL/HLSL constructor-based promotion):

    * both operands must share the same scalar base (float/int/bool);
    * a scalar is broadcast to the vector width of the other operand;
    * same-width vectors keep their width.
    """
    base_l, base_r = scalar_base(left), scalar_base(right)
    if base_l != base_r:
        raise TypeError(
            f"cannot combine {left} with {right}: scalar bases differ"
        )
    width = max(vector_components(left), vector_components(right))
    return make_vector(base_l, width)


def coerce_input(value_type, expected):
    """Check whether ``value_type`` can feed a port typed ``expected``.

    ``expected`` may be a concrete type or the wildcard ``"any"``.
    Numeric scalars are broadcast to the port width; same-width numeric
    vectors are accepted directly. Returns the concrete port type.
    """
    if expected == "any":
        return value_type
    if value_type == expected:
        return expected
    base_v, base_e = scalar_base(value_type), scalar_base(expected)
    if base_v != base_e:
        raise TypeError(f"cannot coerce {value_type} to {expected}")
    if vector_components(value_type) == 1:
        return expected
    if vector_components(value_type) == vector_components(expected):
        return expected
    raise TypeError(
        f"cannot coerce {value_type} to {expected}: component width mismatch"
    )


def hlsl_name(name):
    """Translate a GLSL-style type name to its HLSL spelling."""
    return HLSL_NAMES.get(name, name)
