"""End-to-end orchestration of the material graph pipeline."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import nodes_builtins  # noqa: F401  register built-in node kinds
from . import nodes_math  # noqa: F401
from .analysis import find_cycle, prune_dead_nodes, topo_sort
from .codegen import generate_shader
from .compiler import verify_preview_compile
from .errors import CycleError
from .graph import Graph
from .inference import infer_graph_types


def build_graph_from_dict(data: Dict[str, Any]) -> Graph:
    """Rebuild a graph from the topology produced by ``Graph.to_dict``."""
    graph = Graph(data.get("name", "material"))
    for node in data["nodes"]:
        params = dict(node.get("params", {}))
        position = tuple(node.get("position", (0.0, 0.0)))
        graph.add_node(node["id"], node["kind"], params, position)
    for edge in data.get("edges", []):
        src_node, src_port = edge["from"].split(".", 1)
        dst_node, dst_port = edge["to"].split(".", 1)
        graph.connect(src_node, src_port, dst_node, dst_port)
    return graph


@dataclass
class PipelineResult:
    graph: Graph
    cycle: Optional[List[str]]
    dead_nodes: List[str]
    topo_order: List[str]
    types: Dict[str, Dict[str, str]]
    shaders: Dict[str, str]
    verification: Dict[str, Any]

    def to_report(self) -> Dict[str, Any]:
        return {
            "topological_order": self.topo_order,
            "dead_nodes_removed": self.dead_nodes,
            "cycle_detected": self.cycle,
            "inferred_types": self.types,
            "topology": self.graph.to_dict(),
            "verification": self.verification,
        }


def run_pipeline(
    graph: Graph,
    verify: bool = True,
    sample_points=None,
) -> PipelineResult:
    """Run the full analysis/codegen/verification pipeline.

    Raises :class:`CycleError` when a directed cycle is present; nothing
    downstream (pruning, inference, codegen) runs for cyclic graphs.
    """
    cycle = find_cycle(graph)
    if cycle is not None:
        raise CycleError(cycle)

    pruned, dead_nodes = prune_dead_nodes(graph)
    order = topo_sort(pruned)
    types = infer_graph_types(pruned)
    shaders = {
        "glsl": generate_shader(pruned, "glsl"),
        "hlsl": generate_shader(pruned, "hlsl"),
    }
    verification: Dict[str, Any] = {}
    if verify:
        verification = verify_preview_compile(
            pruned, sample_points=sample_points
        )
    return PipelineResult(
        graph=pruned,
        cycle=None,
        dead_nodes=dead_nodes,
        topo_order=order,
        types=types,
        shaders=shaders,
        verification=verification,
    )
