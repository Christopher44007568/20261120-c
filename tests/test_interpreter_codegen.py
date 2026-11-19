import math
import unittest

from matgraph import (
    Graph,
    evaluate_graph,
    evaluate_outputs,
    generate_glsl,
    generate_hlsl,
    infer_graph_types,
)
from matgraph.interpreter import PreviewContext


def build_math_graph():
    graph = Graph("math")
    graph.add_node("uv", "UV")
    graph.add_node("u", "Swizzle", {"channels": "x"})
    graph.add_node("half", "Const", {"value": 0.5, "type": "float"})
    graph.add_node("mix", "Mix")
    graph.add_node("sin", "Sin")
    graph.add_node("out", "SurfaceOutput")
    graph.connect("uv", "out", "u", "in")
    graph.connect("u", "out", "mix", "a")
    graph.connect("half", "out", "mix", "b")
    graph.connect("half", "out", "mix", "t")
    graph.connect("mix", "out", "sin", "in")
    graph.connect("sin", "out", "out", "roughness")
    return graph


class InterpreterTests(unittest.TestCase):
    def test_mix_and_sin_evaluation(self):
        graph = build_math_graph()
        infer_graph_types(graph)
        ctx = PreviewContext(uv=(0.25, 0.75), time=0.0)
        values = evaluate_graph(graph, ctx)
        mixed = 0.25 * 0.5 + 0.5 * 0.5
        sin_value = values["sin"]["out"]
        self.assertIsInstance(sin_value, float)
        self.assertAlmostEqual(sin_value, math.sin(mixed), places=12)
        outputs = evaluate_outputs(graph, ctx)
        self.assertIn("out", outputs)
        self.assertEqual(len(outputs["out"]["base_color"]), 3)

    def test_checker_pattern_matches_manual_calculation(self):
        graph = Graph("checker")
        graph.add_node("uv", "UV")
        graph.add_node("checker", "Checker", {"scale": 4.0})
        graph.add_node("rough", "Const", {"value": 0.6, "type": "float"})
        graph.add_node("out", "SurfaceOutput")
        graph.connect("checker", "rgb", "out", "base_color")
        graph.connect("rough", "out", "out", "roughness")
        infer_graph_types(graph)
        values = evaluate_outputs(
            graph, PreviewContext(uv=(0.9, 0.9), time=0.0)
        )
        color = values["out"]["base_color"]
        # floor(0.9*4) = 3 on both axes; 3+3 even -> color_a.
        self.assertEqual(color, (0.9, 0.9, 0.9))
        values_light = evaluate_outputs(
            graph, PreviewContext(uv=(0.6, 0.9), time=0.0)
        )
        # floor(0.6*4)=2, floor(0.9*4)=3; 2+3 odd -> color_b.
        self.assertEqual(
            values_light["out"]["base_color"], (0.1, 0.1, 0.1)
        )

    def test_vector_construct_and_dot(self):
        graph = Graph("vectors")
        graph.add_node("x", "Const", {"value": 1.0, "type": "float"})
        graph.add_node("y", "Const", {"value": 2.0, "type": "float"})
        graph.add_node("z", "Const", {"value": 3.0, "type": "float"})
        graph.add_node("combine", "Combine", {"components": 3})
        graph.add_node("length", "Length")
        graph.add_node("out", "SurfaceOutput")
        graph.connect("x", "out", "combine", "c0")
        graph.connect("y", "out", "combine", "c1")
        graph.connect("z", "out", "combine", "c2")
        graph.connect("combine", "out", "length", "in")
        graph.connect("length", "out", "out", "metallic")
        graph.connect("combine", "out", "out", "base_color")
        infer_graph_types(graph)
        values = evaluate_graph(graph)
        self.assertAlmostEqual(
            values["length"]["out"], math.sqrt(14.0), places=12
        )


class CodegenTests(unittest.TestCase):
    def test_glsl_contains_expected_symbols(self):
        graph = build_math_graph()
        infer_graph_types(graph)
        source = generate_glsl(graph)
        self.assertIn("#version 450", source)
        self.assertIn("float u_time;", source)
        self.assertIn("uniform MaterialBlock", source)
        self.assertIn("mix(", source)
        self.assertIn("sin(", source)
        self.assertIn("out_base_color", source)
        self.assertIn("void main()", source)

    def test_hlsl_contains_expected_symbols(self):
        graph = build_math_graph()
        infer_graph_types(graph)
        source = generate_hlsl(graph)
        self.assertIn("float2 v_uv", source)
        self.assertIn("lerp(", source)
        self.assertIn("SurfaceResult mg_surface", source)
        self.assertIn("main_ps", source)

    def test_generation_is_deterministic(self):
        graph = build_math_graph()
        infer_graph_types(graph)
        self.assertEqual(generate_glsl(graph), generate_glsl(graph))
        self.assertEqual(generate_hlsl(graph), generate_hlsl(graph))

    def test_checker_helper_emitted_once(self):
        graph = Graph("checker-code")
        graph.add_node("uv", "UV")
        graph.add_node("checker", "Checker")
        graph.add_node("out", "SurfaceOutput")
        graph.connect("checker", "rgb", "out", "base_color")
        infer_graph_types(graph)
        glsl = generate_glsl(graph)
        hlsl = generate_hlsl(graph)
        self.assertEqual(glsl.count("mg_checker("), 2)  # helper + call
        self.assertIn("fmod", hlsl)


if __name__ == "__main__":
    unittest.main()
