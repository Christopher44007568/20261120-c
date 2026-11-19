import unittest

from matgraph import (
    CycleError,
    Graph,
    generate_glsl,
    generate_hlsl,
    infer_graph_types,
    prune_dead_nodes,
    render_preview,
    run_pipeline,
    verify_compilation,
    verify_preview_compile,
)
from matgraph.compiler import find_compiler
from matgraph.interpreter import PreviewContext


def build_demo_graph():
    graph = Graph("demo_material")
    graph.add_node("uv", "UV")
    graph.add_node("time", "Time")
    graph.add_node("freq", "Const", {"value": 6.2831853, "type": "float"})
    graph.add_node("phase", "Multiply")
    graph.add_node("wave", "Sin")
    graph.add_node("half", "Const", {"value": 0.5, "type": "float"})
    graph.add_node("one", "Const", {"value": 1.0, "type": "float"})
    graph.add_node("shift", "Add")
    graph.add_node("scale_wave", "Multiply")
    graph.add_node("checker", "Checker", {"scale": 8.0})
    graph.add_node("tint", "Const",
                   {"value": (0.2, 0.5, 0.9), "type": "vec3"})
    graph.add_node("color", "Multiply")
    graph.add_node("roughness", "Saturate")
    graph.add_node("dead", "Const", {"value": 42.0, "type": "float"})
    graph.add_node("out", "SurfaceOutput")

    graph.connect("time", "out", "phase", "a")
    graph.connect("freq", "out", "phase", "b")
    graph.connect("phase", "out", "wave", "in")
    graph.connect("wave", "out", "shift", "a")
    graph.connect("one", "out", "shift", "b")
    graph.connect("shift", "out", "scale_wave", "a")
    graph.connect("half", "out", "scale_wave", "b")
    graph.connect("uv", "out", "checker", "uv")
    graph.connect("checker", "rgb", "color", "a")
    graph.connect("tint", "out", "color", "b")
    graph.connect("scale_wave", "out", "roughness", "in")
    graph.connect("color", "out", "out", "base_color")
    graph.connect("roughness", "out", "out", "roughness")
    return graph


@unittest.skipUnless(find_compiler(), "glslangValidator unavailable")
class CompilerTests(unittest.TestCase):
    def test_glsl_and_hlsl_compile_to_spirv(self):
        graph = build_demo_graph()
        report = verify_compilation(graph)
        self.assertTrue(report["ok"])
        backends = {item["backend"]: item for item in report["backends"]}
        self.assertEqual(set(backends), {"glsl", "hlsl"})
        self.assertGreater(backends["glsl"]["spirv_bytes"], 0)
        self.assertGreater(backends["hlsl"]["spirv_bytes"], 0)

    def test_preview_compile_consistency(self):
        graph = build_demo_graph()
        samples = [
            PreviewContext(uv=(0.13, 0.37), time=0.11),
            PreviewContext(uv=(0.81, 0.22), time=0.47),
            PreviewContext(uv=(0.5, 0.5), time=0.93),
        ]
        report = verify_preview_compile(graph, sample_points=samples)
        self.assertTrue(report["ok"])
        self.assertTrue(all(report["generation_stable"].values()))
        self.assertTrue(report["preview_topology_match"])
        self.assertEqual(len(report["samples"]), 3)
        self.assertTrue(all(item["match"] for item in report["samples"]))

    def test_full_pipeline_report_and_shaders(self):
        graph = build_demo_graph()
        result = run_pipeline(graph)
        self.assertEqual(result.dead_nodes, ["dead"])
        self.assertNotIn("dead", result.graph.nodes)
        self.assertIn("uv", result.topo_order)
        self.assertEqual(result.topo_order[-1], "out")
        self.assertTrue(result.verification["ok"])
        self.assertIn("#version 450", result.shaders["glsl"])
        self.assertIn("main_ps", result.shaders["hlsl"])
        report = result.to_report()
        self.assertEqual(report["dead_nodes_removed"], ["dead"])
        self.assertIsNone(report["cycle_detected"])
        self.assertEqual(
            report["inferred_types"]["color"]["out"], "vec3"
        )

    def test_cyclic_graph_rejected_before_codegen(self):
        graph = Graph("loop")
        graph.add_node("a", "Add")
        graph.add_node("b", "Multiply")
        graph.add_node("c", "Subtract")
        graph.connect("a", "out", "b", "a")
        graph.connect("b", "out", "c", "a")
        graph.connect("c", "out", "a", "b")
        with self.assertRaises(CycleError):
            run_pipeline(graph)

    def test_pruning_then_compilation_succeeds(self):
        graph = build_demo_graph()
        pruned, dead = prune_dead_nodes(graph)
        infer_graph_types(pruned)
        report = verify_compilation(pruned)
        self.assertTrue(report["ok"])
        self.assertEqual(dead, ["dead"])
        self.assertIn("mg_checker", generate_glsl(pruned))
        self.assertIn("mg_checker", generate_hlsl(pruned))

    def test_preview_grid_shape_and_values(self):
        graph = build_demo_graph()
        pruned, _ = prune_dead_nodes(graph)
        infer_graph_types(pruned)
        preview = render_preview(pruned, grid=4)
        self.assertEqual(preview["grid"], 4)
        self.assertEqual(len(preview["cells"]), 16)
        first = preview["cells"][0]
        self.assertEqual(first["uv"], [0.0, 0.0])
        self.assertEqual(len(first["out"]["base_color"]), 3)
        for cell in preview["cells"]:
            for channel in cell["out"]["base_color"]:
                self.assertGreaterEqual(channel, 0.0)
                self.assertLessEqual(channel, 1.0)


if __name__ == "__main__":
    unittest.main()
