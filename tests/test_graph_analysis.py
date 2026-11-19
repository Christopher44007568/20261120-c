import unittest

from matgraph import (
    Graph,
    CycleError,
    ConnectionError,
    TypeInferenceError,
    infer_graph_types,
    prune_dead_nodes,
    topo_sort,
    find_cycle,
)


def build_simple_graph():
    graph = Graph("simple")
    graph.add_node("uv", "UV")
    graph.add_node("scale", "Const", {"value": 2.0, "type": "float"})
    graph.add_node("mul", "Multiply")
    graph.add_node("checker", "Checker", {"scale": 4.0})
    graph.add_node("out", "SurfaceOutput")
    graph.connect("uv", "out", "mul", "a")
    graph.connect("scale", "out", "mul", "b")
    graph.connect("mul", "out", "checker", "uv")
    graph.connect("checker", "rgb", "out", "base_color")
    return graph


class AnalysisTests(unittest.TestCase):
    def test_topo_sort_respects_dependencies(self):
        graph = build_simple_graph()
        order = topo_sort(graph)
        position = {node_id: i for i, node_id in enumerate(order)}
        self.assertLess(position["uv"], position["mul"])
        self.assertLess(position["scale"], position["mul"])
        self.assertLess(position["mul"], position["checker"])
        self.assertLess(position["checker"], position["out"])

    def test_topo_sort_is_deterministic(self):
        graph = build_simple_graph()
        self.assertEqual(topo_sort(graph), topo_sort(graph.clone()))

    def test_cycle_is_detected_and_rejected(self):
        graph = Graph("cyclic")
        graph.add_node("a", "Add")
        graph.add_node("b", "Multiply")
        graph.add_node("c", "Subtract")
        graph.connect("a", "out", "b", "a")
        graph.connect("b", "out", "c", "a")
        graph.connect("c", "out", "a", "b")
        cycle = find_cycle(graph)
        self.assertIsNotNone(cycle)
        self.assertEqual(len(cycle), 3)
        with self.assertRaises(CycleError):
            topo_sort(graph)
        with self.assertRaises(CycleError):
            infer_graph_types(graph)

    def test_self_connection_rejected(self):
        graph = Graph("self")
        graph.add_node("a", "Add")
        with self.assertRaises(ConnectionError):
            graph.connect("a", "out", "a", "b")

    def test_unknown_port_rejected(self):
        graph = Graph("bad-port")
        graph.add_node("a", "Add")
        graph.add_node("b", "Multiply")
        with self.assertRaises(ConnectionError):
            graph.connect("a", "nope", "b", "a")

    def test_double_driver_rejected(self):
        graph = Graph("double")
        graph.add_node("a", "Const", {"value": 1.0, "type": "float"})
        graph.add_node("b", "Const", {"value": 2.0, "type": "float"})
        graph.add_node("add", "Add")
        graph.connect("a", "out", "add", "a")
        with self.assertRaises(ConnectionError):
            graph.connect("b", "out", "add", "a")

    def test_dead_nodes_are_pruned(self):
        graph = build_simple_graph()
        graph.add_node("dead_const", "Const",
                       {"value": 9.0, "type": "float"})
        graph.add_node("dead_add", "Add")
        graph.add_node("live_other", "Const",
                       {"value": 0.3, "type": "float"})
        graph.connect("dead_const", "out", "dead_add", "a")
        graph.connect("live_other", "out", "out", "roughness")
        pruned, dead = prune_dead_nodes(graph)
        self.assertEqual(dead, ["dead_add", "dead_const"])
        self.assertNotIn("dead_add", pruned.nodes)
        self.assertIn("live_other", pruned.nodes)
        self.assertEqual(
            len(pruned.edges),
            len(graph.edges) - 1,
        )


class InferenceTests(unittest.TestCase):
    def test_scalar_broadcast_and_vector_types(self):
        graph = build_simple_graph()
        types = infer_graph_types(graph)
        self.assertEqual(types["uv"]["out"], "vec2")
        self.assertEqual(types["mul"]["out"], "vec2")
        self.assertEqual(types["checker"]["rgb"], "vec3")
        self.assertEqual(types["out"]["base_color"], "vec3")

    def test_incompatible_types_rejected(self):
        graph = Graph("bad-types")
        graph.add_node("flag", "Const",
                       {"value": True, "type": "bool"})
        graph.add_node("number", "Const",
                       {"value": 1.0, "type": "float"})
        graph.add_node("add", "Add")
        graph.connect("flag", "out", "add", "a")
        graph.connect("number", "out", "add", "b")
        with self.assertRaises(TypeInferenceError):
            infer_graph_types(graph)

    def test_unconnected_required_port_rejected(self):
        graph = Graph("missing-input")
        graph.add_node("a", "Add")
        graph.add_node("out", "SurfaceOutput")
        graph.connect("a", "out", "out", "roughness")
        with self.assertRaises(TypeInferenceError):
            infer_graph_types(graph)

    def test_same_width_vector_passes(self):
        graph = Graph("vec-mul")
        graph.add_node("a", "Const",
                       {"value": (1.0, 2.0, 3.0), "type": "vec3"})
        graph.add_node("b", "Const",
                       {"value": (2.0, 3.0, 4.0), "type": "vec3"})
        graph.add_node("dot", "Dot")
        graph.connect("a", "out", "dot", "a")
        graph.connect("b", "out", "dot", "b")
        types = infer_graph_types(graph)
        self.assertEqual(types["dot"]["out"], "float")


if __name__ == "__main__":
    unittest.main()
