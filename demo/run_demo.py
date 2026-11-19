"""End-to-end demonstration of the material graph pipeline.

Builds a graph with live and dead nodes, runs cycle detection, dead node
pruning, type inference, GLSL/HLSL generation, preview evaluation and
real compiler verification, then writes every artifact to ``artifacts/``.
Also demonstrates that a cyclic graph is rejected.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matgraph import (  # noqa: E402
    CycleError,
    Graph,
    PreviewContext,
    evaluate_outputs,
    generate_glsl,
    generate_hlsl,
    infer_graph_types,
    prune_dead_nodes,
    run_pipeline,
    topo_sort,
)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS = os.path.join(ROOT, "artifacts")


def build_graph() -> Graph:
    graph = Graph("demo_material")
    graph.add_node("uv", "UV", position=(0, 0))
    graph.add_node("time", "Time", position=(0, 80))
    graph.add_node("freq", "Const",
                   {"value": 6.2831853, "type": "float"}, position=(0, 160))
    graph.add_node("phase", "Multiply", position=(180, 80))
    graph.add_node("wave", "Sin", position=(360, 80))
    graph.add_node("one", "Const",
                   {"value": 1.0, "type": "float"}, position=(180, 180))
    graph.add_node("shift", "Add", position=(540, 80))
    graph.add_node("half", "Const",
                   {"value": 0.5, "type": "float"}, position=(540, 200))
    graph.add_node("wave_scaled", "Multiply", position=(720, 80))
    graph.add_node("roughness", "Saturate", position=(900, 80))
    graph.add_node("checker", "Checker", {"scale": 8.0}, position=(360, 0))
    graph.add_node("tint", "Const",
                   {"value": (0.2, 0.5, 0.9), "type": "vec3"},
                   position=(360, 200))
    graph.add_node("color", "Multiply", position=(720, 0))
    graph.add_node("metal_mask", "Swizzle", {"channels": "x"},
                   position=(180, -80))
    graph.add_node("out", "SurfaceOutput", position=(1080, 40))

    # Dead branch: never reaches the output node.
    graph.add_node("dead_const", "Const",
                   {"value": 42.0, "type": "float"}, position=(0, 320))
    graph.add_node("dead_add", "Add", position=(180, 320))

    graph.connect("time", "out", "phase", "a")
    graph.connect("freq", "out", "phase", "b")
    graph.connect("phase", "out", "wave", "in")
    graph.connect("wave", "out", "shift", "a")
    graph.connect("one", "out", "shift", "b")
    graph.connect("shift", "out", "wave_scaled", "a")
    graph.connect("half", "out", "wave_scaled", "b")
    graph.connect("wave_scaled", "out", "roughness", "in")
    graph.connect("uv", "out", "checker", "uv")
    graph.connect("checker", "rgb", "color", "a")
    graph.connect("tint", "out", "color", "b")
    graph.connect("uv", "out", "metal_mask", "in")
    graph.connect("color", "out", "out", "base_color")
    graph.connect("roughness", "out", "out", "roughness")
    graph.connect("metal_mask", "out", "out", "metallic")

    graph.connect("dead_const", "out", "dead_add", "a")
    graph.connect("dead_const", "out", "dead_add", "b")
    return graph


def demonstrate_cycle_rejection() -> dict:
    cyclic = Graph("cyclic_material")
    cyclic.add_node("a", "Add")
    cyclic.add_node("b", "Multiply")
    cyclic.add_node("c", "Subtract")
    cyclic.connect("a", "out", "b", "a")
    cyclic.connect("b", "out", "c", "a")
    cyclic.connect("c", "out", "a", "b")
    try:
        run_pipeline(cyclic, verify=False)
    except CycleError as exc:
        return {"rejected": True, "cycle": exc.cycle, "message": str(exc)}
    return {"rejected": False}


def main() -> int:
    os.makedirs(ARTIFACTS, exist_ok=True)
    graph = build_graph()

    print("== 1. cycle rejection ==")
    cycle_report = demonstrate_cycle_rejection()
    print(json.dumps(cycle_report, indent=2))

    print("\n== 2. dead node pruning ==")
    pruned, dead = prune_dead_nodes(graph)
    print(f"removed dead nodes: {dead}")

    print("\n== 3. topological order (deterministic, producers first) ==")
    order = topo_sort(pruned)
    for index, node_id in enumerate(order):
        print(f"  {index:2d}. {node_id} ({pruned.nodes[node_id].kind})")

    print("\n== 4. type inference ==")
    types = infer_graph_types(pruned)
    for node_id in order:
        print(f"  {node_id}: {types[node_id]}")

    print("\n== 5. shader generation ==")
    glsl_source = generate_glsl(pruned)
    hlsl_source = generate_hlsl(pruned)
    with open(os.path.join(ARTIFACTS, "material.frag"), "w") as handle:
        handle.write(glsl_source)
    with open(os.path.join(ARTIFACTS, "material.hlsl"), "w") as handle:
        handle.write(hlsl_source)
    print("  wrote artifacts/material.frag and artifacts/material.hlsl")

    print("\n== 6. preview samples (CPU interpreter) ==")
    samples = []
    for uv in ((0.13, 0.37), (0.62, 0.81), (0.5, 0.5)):
        ctx = PreviewContext(uv=uv, time=0.25)
        outputs = evaluate_outputs(pruned, ctx)
        samples.append({"uv": list(uv), "outputs": outputs["out"]})
        print(f"  uv={uv}: {outputs['out']}")

    print("\n== 7. full pipeline + real compiler verification ==")
    result = run_pipeline(graph)
    verification = result.verification
    print(f"  compile ok: {verification['compile']['ok']}")
    for backend in verification["compile"]["backends"]:
        print(f"    - {backend['backend']}: spirv_bytes="
              f"{backend['spirv_bytes']}")
    print(f"  generation stable: {verification['generation_stable']}")
    print(f"  preview/topology match: "
          f"{verification['preview_topology_match']}")

    report = {
        "cycle_rejection": cycle_report,
        "topological_order": result.topo_order,
        "dead_nodes_removed": result.dead_nodes,
        "inferred_types": result.types,
        "node_topology": result.graph.to_dict(),
        "preview_samples": [
            {
                "uv": sample["uv"],
                "outputs": {
                    key: (list(value) if isinstance(value, tuple) else value)
                    for key, value in sample["outputs"].items()
                },
            }
            for sample in samples
        ],
        "verification": verification,
    }
    with open(os.path.join(ARTIFACTS, "pipeline_report.json"), "w") as handle:
        json.dump(report, handle, indent=2)
    print("\nwrote artifacts/pipeline_report.json")
    return 0 if verification["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
