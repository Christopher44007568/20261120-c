"""Static graph analysis: cycle detection, topo order, dead node pruning."""

from collections import deque
import heapq
from typing import Dict, List, Optional, Set, Tuple

from .errors import CycleError
from .graph import Graph


def find_cycle(graph: Graph) -> Optional[List[str]]:
    """Return one directed cycle as a node-id list, or ``None``.

    Iterative DFS with white/gray/black coloring so deep graphs do not
    overflow Python's recursion limit.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {node_id: WHITE for node_id in graph.nodes}
    parent: Dict[str, Optional[str]] = {
        node_id: None for node_id in graph.nodes
    }

    for start in sorted(graph.nodes):
        if color[start] != WHITE:
            continue
        stack: List[Tuple[str, int]] = [(start, 0)]
        color[start] = GRAY
        while stack:
            node_id, idx = stack[-1]
            succ = graph.successors(node_id)
            if idx < len(succ):
                stack[-1] = (node_id, idx + 1)
                nxt = succ[idx]
                if color[nxt] == GRAY:
                    cycle = [nxt]
                    cur = node_id
                    while cur != nxt:
                        cycle.append(cur)
                        cur = parent[cur]  # type: ignore[assignment]
                    cycle.reverse()
                    return cycle
                if color[nxt] == WHITE:
                    color[nxt] = GRAY
                    parent[nxt] = node_id
                    stack.append((nxt, 0))
            else:
                color[node_id] = BLACK
                stack.pop()
    return None


def topo_sort(graph: Graph) -> List[str]:
    """Return node ids in dependency order (producers before consumers).

    Kahn's algorithm with alphabetical tie-breaking makes the order fully
    deterministic for stable code generation. Raises :class:`CycleError`.
    """
    cycle = find_cycle(graph)
    if cycle is not None:
        raise CycleError(cycle)

    indegree: Dict[str, int] = {node_id: 0 for node_id in graph.nodes}
    for edge in graph.edges:
        indegree[edge[2]] += 1

    ready = [node_id for node_id, deg in indegree.items() if deg == 0]
    heapq.heapify(ready)
    order: List[str] = []
    while ready:
        node_id = heapq.heappop(ready)
        order.append(node_id)
        for edge in graph.output_edges(node_id):
            succ = edge[2]
            indegree[succ] -= 1
            if indegree[succ] == 0:
                heapq.heappush(ready, succ)
    if len(order) != len(graph.nodes):
        remaining = sorted(set(graph.nodes) - set(order))
        raise CycleError(remaining)
    return order


def prune_dead_nodes(graph: Graph) -> Tuple[Graph, List[str]]:
    """Return a pruned copy plus the ids of removed dead nodes.

    A node is live when it is a graph output node, or it (transitively)
    feeds one. Everything else cannot affect the shader and is removed
    together with its dangling edges.
    """
    live: Set[str] = set()
    queue = deque(node.id for node in graph.output_nodes())
    while queue:
        node_id = queue.popleft()
        if node_id in live:
            continue
        live.add(node_id)
        for pred in graph.predecessors(node_id):
            if pred not in live:
                queue.append(pred)

    dead = sorted(node_id for node_id in graph.nodes if node_id not in live)
    pruned = graph.clone()
    for node_id in dead:
        pruned.remove_node(node_id)
    return pruned, dead
