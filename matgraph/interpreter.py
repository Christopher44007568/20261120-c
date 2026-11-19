"""CPU interpreter that evaluates a material graph for preview rendering."""

from typing import Any, Dict, Optional, Tuple

from .analysis import topo_sort
from .graph import Graph
from .vector import value_type


class PreviewContext:
    """Per-pixel evaluation context shared by UV/Time/... source nodes."""

    def __init__(self, uv: Tuple[float, float] = (0.0, 0.0),
                 time: float = 0.0):
        self.uv = uv
        self.time = time


def evaluate_graph(
    graph: Graph,
    context: Optional[PreviewContext] = None,
) -> Dict[str, Dict[str, Any]]:
    """Evaluate every node in topological order.

    Returns ``{node_id: {output_port: value}}``. Values are Python numbers
    or tuples of numbers, suitable both for preview pixels and for numeric
    cross-checking against generated shader semantics.
    """
    context = context or PreviewContext()
    order = topo_sort(graph)
    values: Dict[str, Dict[str, Any]] = {}

    for node_id in order:
        node = graph.nodes[node_id]
        spec = node.spec
        inputs: Dict[str, Any] = {}

        for port in spec.inputs:
            edge = graph.driver(node_id, port.name)
            if edge is None:
                if port.name == "uv" and port.type == "vec2":
                    inputs[port.name] = tuple(context.uv)
                    continue
                if not port.required and port.default is not None:
                    inputs[port.name] = port.default
                elif port.required:
                    raise ValueError(
                        f"node {node_id!r}: unconnected required input "
                        f"{port.name!r}"
                    )
                continue
            src_node, src_port, _, _ = edge
            inputs[port.name] = values[src_node][src_port]

        # Source nodes read the live preview context directly so node
        # parameters stay immutable across repeated evaluations.
        if spec.kind == "UV":
            values[node_id] = {"out": tuple(context.uv)}
            continue
        elif spec.kind == "Time":
            values[node_id] = {"out": float(context.time)}
            continue

        if spec.evaluate is None:
            raise ValueError(
                f"node kind {spec.kind!r} has no CPU evaluation hook"
            )
        result = spec.evaluate(node, inputs)
        values[node_id] = result

    return values


def evaluate_outputs(
    graph: Graph,
    context: Optional[PreviewContext] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return evaluated values keyed by output node id."""
    values = evaluate_graph(graph, context)
    return {
        node.id: values[node.id]
        for node in graph.output_nodes()
        if node.id in values
    }


def render_preview(graph: Graph, grid: int = 8,
                   time: float = 0.0) -> Dict[str, Any]:
    """Render an ``grid x grid`` CPU preview of the graph output node.

    Returns a dict with normalized UV coordinates and the evaluated
    surface output for every cell. This is the preview-side reference
    used for preview/compile consistency checks.
    """
    output_ids = [node.id for node in graph.output_nodes()]
    if not output_ids:
        raise ValueError("graph has no output node; cannot render preview")
    cells = []
    for row in range(grid):
        for col in range(grid):
            uv = (col / max(grid - 1, 1), row / max(grid - 1, 1))
            values = evaluate_outputs(graph, PreviewContext(uv=uv, time=time))
            cell = {"uv": list(uv)}
            for node_id in output_ids:
                cell[node_id] = {
                    port: (list(value) if isinstance(value, tuple) else value)
                    for port, value in values[node_id].items()
                }
            cells.append(cell)
    return {"grid": grid, "cells": cells}


def describe_values(values: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """Map evaluated values to their inferred type names for reporting."""
    return {
        node_id: {port: value_type(val) for port, val in ports.items()}
        for node_id, ports in values.items()
    }
