"""Graph data structure: nodes, typed ports and directed edges."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .errors import ConnectionError
from .registry import get_spec

Edge = Tuple[str, str, str, str]


@dataclass
class Node:
    """A concrete node instance inside a graph."""

    id: str
    kind: str
    params: Dict[str, Any] = field(default_factory=dict)
    position: Tuple[float, float] = (0.0, 0.0)
    # Filled in by inference: {port_name: concrete_type}
    types: Dict[str, str] = field(default_factory=dict)

    @property
    def spec(self):
        return get_spec(self.kind)


class Graph:
    """Directed graph of material nodes.

    Edges run from an output port to an input port:
    ``(src_node, src_port, dst_node, dst_port)``.
    """

    def __init__(self, name: str = "material"):
        self.name = name
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []

    # ------------------------------------------------------------------ nodes
    def add_node(
        self,
        node_id: str,
        kind: str,
        params: Optional[Dict[str, Any]] = None,
        position: Tuple[float, float] = (0.0, 0.0),
    ) -> Node:
        if node_id in self.nodes:
            raise ValueError(f"duplicate node id: {node_id}")
        spec = get_spec(kind)
        merged = dict(spec.params)
        if params:
            merged.update(params)
        node = Node(node_id, kind, merged, position)
        self.nodes[node_id] = node
        return node

    def remove_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            raise KeyError(f"unknown node: {node_id}")
        self.edges = [
            edge
            for edge in self.edges
            if edge[0] != node_id and edge[2] != node_id
        ]
        del self.nodes[node_id]

    # ------------------------------------------------------------------ edges
    def connect(
        self,
        src_node: str,
        src_port: str,
        dst_node: str,
        dst_port: str,
    ) -> None:
        """Add an edge from an output port to an input port."""
        self._require_port(src_node, src_port, output=True)
        self._require_port(dst_node, dst_port, output=False)
        if src_node == dst_node:
            raise ConnectionError(
                f"self connection rejected on node {src_node!r}"
            )
        for edge in self.edges:
            if edge[2] == dst_node and edge[3] == dst_port:
                raise ConnectionError(
                    f"input {dst_node}.{dst_port} already driven by "
                    f"{edge[0]}.{edge[1]}"
                )
        edge = (src_node, src_port, dst_node, dst_port)
        if edge in self.edges:
            raise ConnectionError(f"duplicate edge: {edge}")
        self.edges.append(edge)

    def disconnect(
        self, src_node: str, src_port: str, dst_node: str, dst_port: str
    ) -> None:
        edge = (src_node, src_port, dst_node, dst_port)
        if edge not in self.edges:
            raise KeyError(f"no such edge: {edge}")
        self.edges.remove(edge)

    def _require_port(self, node_id, port_name, output):
        node = self.nodes.get(node_id)
        if node is None:
            raise ConnectionError(f"unknown node: {node_id}")
        ports = node.spec.outputs if output else node.spec.inputs
        if not any(port.name == port_name for port in ports):
            direction = "output" if output else "input"
            raise ConnectionError(
                f"node {node_id!r} ({node.kind}) has no {direction} port "
                f"{port_name!r}"
            )

    # --------------------------------------------------------------- topology
    def driver(self, node_id: str, port: str) -> Optional[Edge]:
        """Return the edge driving an input port, if any."""
        for edge in self.edges:
            if edge[2] == node_id and edge[3] == port:
                return edge
        return None

    def input_edges(self, node_id: str) -> List[Edge]:
        return [edge for edge in self.edges if edge[2] == node_id]

    def output_edges(self, node_id: str) -> List[Edge]:
        return [edge for edge in self.edges if edge[0] == node_id]

    def predecessors(self, node_id: str) -> List[str]:
        seen = {}
        for edge in self.input_edges(node_id):
            seen.setdefault(edge[0], None)
        return list(seen)

    def successors(self, node_id: str) -> List[str]:
        seen = {}
        for edge in self.output_edges(node_id):
            seen.setdefault(edge[2], None)
        return list(seen)

    def output_nodes(self) -> List[Node]:
        return [
            node
            for node in self.nodes.values()
            if node.spec.is_output
        ]

    def clone(self) -> "Graph":
        copy = Graph(self.name)
        for node in self.nodes.values():
            copy.add_node(
                node.id,
                node.kind,
                dict(node.params),
                node.position,
            )
            copy.nodes[node.id].types = dict(node.types)
        copy.edges = list(self.edges)
        return copy

    # ------------------------------------------------------------- serializing
    def to_dict(self) -> Dict[str, Any]:
        """Serialize graph topology for reporting and round-tripping."""
        return {
            "name": self.name,
            "nodes": [
                {
                    "id": node.id,
                    "kind": node.kind,
                    "params": dict(node.params),
                    "position": list(node.position),
                    "types": dict(node.types),
                }
                for node in sorted(self.nodes.values(), key=lambda n: n.id)
            ],
            "edges": [
                {
                    "from": f"{edge[0]}.{edge[1]}",
                    "to": f"{edge[2]}.{edge[3]}",
                }
                for edge in self.edges
            ],
        }
