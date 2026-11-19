import unittest

from shader_permutations.cache import LruCache
from shader_permutations.dependency import DependencyGraph


class DependencyAndCacheTests(unittest.TestCase):
    def test_keyword_graph_is_acyclic(self) -> None:
        graph = DependencyGraph.keyword_graph()
        self.assertEqual(graph.cycle(), ())
        order = graph.topological_order()
        self.assertEqual(set(order), set(graph.nodes))
        positions = {node: index for index, node in enumerate(order)}
        for source, target in graph.edges:
            self.assertLess(positions[source], positions[target])

    def test_graph_renderers_contain_every_edge(self) -> None:
        graph = DependencyGraph.keyword_graph()
        dot = graph.to_dot()
        mermaid = graph.to_mermaid()
        for source, target in graph.edges:
            self.assertIn(f'"{source}" -> "{target}"', dot)
            self.assertIn(f"{source} -->|implies| {target}", mermaid)

    def test_lru_cache_reports_hits_and_evictions(self) -> None:
        cache = LruCache[str, int](capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertEqual(cache.get("a"), 1)
        cache.put("c", 3)
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("a"), 1)
        self.assertEqual(cache.get("c"), 3)
        self.assertEqual(cache.hits, 3)
        self.assertEqual(cache.misses, 1)
        self.assertEqual(cache.evictions, 1)


if __name__ == "__main__":
    unittest.main()
