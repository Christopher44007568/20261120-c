"""Material graph editing, type inference and shader code generation.

The package turns a node graph into GLSL or HLSL, performing:

* connection validation and recursive type inference;
* directed cycle detection (cycles are rejected);
* dead node pruning from the graph outputs;
* stable topological ordering;
* CPU preview evaluation and shader compilation verification.
"""

from .errors import (
    GraphError,
    CycleError,
    ConnectionError,
    TypeInferenceError,
    CompileError,
)
from .types import (
    SCALAR_TYPES,
    VECTOR_TYPES,
    ALL_TYPES,
    type_rank,
    scalar_base,
    vector_components,
    is_vector,
    is_numeric,
    infer_binary,
    coerce_input,
)
from .graph import Graph, Node
from .registry import NODE_REGISTRY, NodeSpec, PortSpec, register_node
from .analysis import topo_sort, prune_dead_nodes, find_cycle
from .inference import infer_graph_types
from .interpreter import evaluate_graph, render_preview
from .interpreter import evaluate_outputs, PreviewContext
from .codegen import generate_glsl, generate_hlsl, generate_shader
from .compiler import verify_compilation, verify_preview_compile
from .pipeline import run_pipeline, build_graph_from_dict, PipelineResult

__all__ = [
    "Graph",
    "Node",
    "Port",
    "GraphError",
    "CycleError",
    "ConnectionError",
    "TypeInferenceError",
    "CompileError",
    "NODE_REGISTRY",
    "NodeSpec",
    "PortSpec",
    "register_node",
    "SCALAR_TYPES",
    "VECTOR_TYPES",
    "ALL_TYPES",
    "type_rank",
    "scalar_base",
    "vector_components",
    "is_vector",
    "is_numeric",
    "infer_binary",
    "coerce_input",
    "topo_sort",
    "prune_dead_nodes",
    "find_cycle",
    "infer_graph_types",
    "evaluate_graph",
    "render_preview",
    "evaluate_outputs",
    "PreviewContext",
    "generate_glsl",
    "generate_hlsl",
    "generate_shader",
    "verify_compilation",
    "verify_preview_compile",
    "run_pipeline",
    "build_graph_from_dict",
    "PipelineResult",
]
