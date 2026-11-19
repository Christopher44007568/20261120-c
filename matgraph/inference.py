"""Recursive/iterative type inference over the node graph."""

from typing import Dict

from .analysis import topo_sort
from .errors import TypeInferenceError
from .graph import Graph
from .types import coerce_input


def infer_graph_types(graph: Graph) -> Dict[str, Dict[str, str]]:
    """Infer and store concrete port types for every node.

    Returns a mapping ``{node_id: {port_name: type}}`` covering both input
    and output ports. Nodes are visited in topological order, so each
    input port's driver type is already known.
    """
    order = topo_sort(graph)
    resolved: Dict[str, Dict[str, str]] = {}

    for node_id in order:
        node = graph.nodes[node_id]
        spec = node.spec
        port_types: Dict[str, str] = {}
        input_types: Dict[str, str] = {}

        for port in spec.inputs:
            edge = graph.driver(node_id, port.name)
            if edge is None:
                if port.required and port.default is None:
                    raise TypeInferenceError(
                        f"node {node_id!r} ({spec.kind}): required input "
                        f"{port.name!r} is unconnected"
                    )
                if not port.required and port.default is None:
                    continue
                # Static default value: trust the declared port type.
                input_types[port.name] = port.type
                port_types[port.name] = port.type
                continue

            src_node, src_port, _, _ = edge
            try:
                source_type = resolved[src_node][src_port]
            except KeyError as exc:
                raise TypeInferenceError(
                    f"node {node_id!r}: cannot resolve driver "
                    f"{src_node}.{src_port}"
                ) from exc
            try:
                concrete = coerce_input(source_type, port.type)
            except TypeError as exc:
                raise TypeInferenceError(
                    f"node {node_id!r} ({spec.kind}) input {port.name!r}: "
                    f"{exc}"
                ) from exc
            input_types[port.name] = concrete
            port_types[port.name] = concrete

        try:
            output_types = spec.infer(node, input_types) if spec.infer else {}
        except TypeError as exc:
            raise TypeInferenceError(
                f"node {node_id!r} ({spec.kind}): {exc}"
            ) from exc

        for port in spec.outputs:
            if port.name not in output_types:
                raise TypeInferenceError(
                    f"node {node_id!r} ({spec.kind}): inference did not "
                    f"resolve output {port.name!r}"
                )
        port_types.update(output_types)
        resolved[node_id] = port_types
        node.types = dict(port_types)

    return resolved
