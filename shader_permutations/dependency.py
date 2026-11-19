"""Keyword dependency graph construction and cycle validation."""

from __future__ import annotations

from dataclasses import dataclass

from .model import IMPLIED_BY, KEYWORDS


@dataclass(frozen=True, slots=True)
class DependencyGraph:
    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]

    @classmethod
    def keyword_graph(cls) -> "DependencyGraph":
        edges = tuple(
            sorted(
                (keyword, dependency)
                for keyword in KEYWORDS
                for dependency in IMPLIED_BY[keyword]
            )
        )
        return cls(KEYWORDS, edges)

    def cycle(self) -> tuple[str, ...]:
        """Return one directed cycle, or an empty tuple when acyclic."""

        adjacency: dict[str, list[str]] = {node: [] for node in self.nodes}
        for source, target in self.edges:
            adjacency[source].append(target)

        state = {node: 0 for node in self.nodes}
        path: list[str] = []

        def visit(node: str) -> tuple[str, ...]:
            state[node] = 1
            path.append(node)
            for neighbor in adjacency[node]:
                if state[neighbor] == 0:
                    found = visit(neighbor)
                    if found:
                        return found
                elif state[neighbor] == 1:
                    start = path.index(neighbor)
                    return tuple(path[start:] + [neighbor])
            path.pop()
            state[node] = 2
            return ()

        for node in self.nodes:
            if state[node] == 0:
                found = visit(node)
                if found:
                    return found
        return ()

    def topological_order(self) -> tuple[str, ...]:
        """Kahn topological sort; raises if a cycle exists."""

        indegree = {node: 0 for node in self.nodes}
        adjacency: dict[str, list[str]] = {node: [] for node in self.nodes}
        for source, target in self.edges:
            adjacency[source].append(target)
            indegree[target] += 1
        ready = sorted(node for node, degree in indegree.items() if degree == 0)
        order: list[str] = []
        while ready:
            node = ready.pop(0)
            order.append(node)
            for neighbor in sorted(adjacency[node]):
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    ready.append(neighbor)
                    ready.sort()
        if len(order) != len(self.nodes):
            raise ValueError("dependency graph contains a cycle")
        return tuple(order)

    def to_dot(self) -> str:
        lines = [
            "digraph shader_keywords {",
            '  rankdir="LR";',
            '  node [shape=box, style="rounded,filled", fillcolor="#eef3f8"];',
        ]
        for node in self.nodes:
            lines.append(f'  "{node}";')
        for source, target in self.edges:
            lines.append(f'  "{source}" -> "{target}" [label="implies"];')
        lines.append("}")
        return "\n".join(lines) + "\n"

    def to_mermaid(self) -> str:
        lines = ["flowchart LR"]
        for node in self.nodes:
            lines.append(f'  {node}["{node}"]')
        for source, target in self.edges:
            lines.append(f"  {source} -->|implies| {target}")
        return "\n".join(lines) + "\n"
