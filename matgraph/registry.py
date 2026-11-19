"""Declarative node specification registry.

A :class:`NodeSpec` describes a node kind independently of any concrete
graph instance: its ports, static parameters, a type-inference hook, a
CPU evaluation hook (used by the preview interpreter) and a shader
emission hook (used by both GLSL and HLSL backends).
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class PortSpec:
    """One input or output port on a node kind."""

    name: str
    type: str
    required: bool = True
    default: Any = None


@dataclass
class NodeSpec:
    """Full specification of a built-in node kind."""

    kind: str
    category: str
    inputs: List[PortSpec] = field(default_factory=list)
    outputs: List[PortSpec] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    # infer(node, input_types) -> {output_port: concrete_type}
    infer: Optional[Callable] = None
    # eval(node, inputs) -> {output_port: python value}
    evaluate: Optional[Callable] = None
    # emit(node, ctx) -> list of statement strings; ctx is an EmitContext.
    emit: Optional[Callable] = None
    is_output: bool = False

    def input_spec(self, name):
        for port in self.inputs:
            if port.name == name:
                return port
        raise KeyError(f"node {self.kind} has no input port {name!r}")

    def output_spec(self, name):
        for port in self.outputs:
            if port.name == name:
                return port
        raise KeyError(f"node {self.kind} has no output port {name!r}")


NODE_REGISTRY: Dict[str, NodeSpec] = {}


def register_node(spec: NodeSpec) -> NodeSpec:
    """Register a node kind globally and return the spec."""
    if spec.kind in NODE_REGISTRY:
        raise ValueError(f"duplicate node kind: {spec.kind}")
    NODE_REGISTRY[spec.kind] = spec
    return spec


def get_spec(kind: str) -> NodeSpec:
    try:
        return NODE_REGISTRY[kind]
    except KeyError as exc:
        raise KeyError(f"unknown node kind: {kind}") from exc
