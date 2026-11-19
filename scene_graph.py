"""Scene graph with dirty-flag world-matrix propagation.

A node owns a local 4x4 transform and a cached world matrix.
When a local transform changes, only that node is marked dirty;
the world pass recomputes a node only if it (or an ancestor) is
dirty, and skips clean subtrees entirely.
"""

import math


def mat_identity():
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def mat_mul(a, b):
    out = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        ai = a[i]
        oi = out[i]
        for k in range(4):
            aik = ai[k]
            if aik == 0.0:
                continue
            bk = b[k]
            oi[0] += aik * bk[0]
            oi[1] += aik * bk[1]
            oi[2] += aik * bk[2]
            oi[3] += aik * bk[3]
    return out


def mat_translation(x, y, z):
    m = mat_identity()
    m[0][3] = x
    m[1][3] = y
    m[2][3] = z
    return m


def mat_rotation_y(angle):
    c = math.cos(angle)
    s = math.sin(angle)
    return [
        [c, 0.0, s, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [-s, 0.0, c, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


class Node:
    __slots__ = ("name", "local", "world", "children", "parent", "dirty")

    def __init__(self, name, local=None, parent=None):
        self.name = name
        self.local = local if local is not None else mat_identity()
        self.world = mat_identity()
        self.children = []
        self.parent = None
        self.dirty = True
        if parent is not None:
            parent.add_child(self)

    def add_child(self, child):
        child.parent = self
        self.children.append(child)

    def set_local(self, local):
        """Edit the local transform; only this node becomes dirty."""
        self.local = local
        self.dirty = True


class UpdateStats:
    __slots__ = ("matrix_updates", "nodes_visited")

    def __init__(self):
        self.matrix_updates = 0
        self.nodes_visited = 0


def update_world_dirty(root, stats):
    """Traverse once; recompute world matrices only along dirty paths."""
    stack = [(root, None, root.dirty)]
    while stack:
        node, parent_world, ancestor_dirty = stack.pop()
        stats.nodes_visited += 1
        if node.dirty or ancestor_dirty:
            node.world = (
                node.local if parent_world is None else mat_mul(parent_world, node.local)
            )
            stats.matrix_updates += 1
            node.dirty = False
            child_world = node.world
            child_dirty = True
        else:
            child_world = node.world
            child_dirty = False
        for child in node.children:
            stack.append((child, child_world, child_dirty))


def update_world_naive(root, stats):
    """Baseline: recompute every world matrix on every traversal."""
    stack = [(root, None)]
    while stack:
        node, parent_world = stack.pop()
        stats.nodes_visited += 1
        node.world = (
            node.local if parent_world is None else mat_mul(parent_world, node.local)
        )
        stats.matrix_updates += 1
        node.dirty = False
        for child in node.children:
            stack.append((child, node.world))


def build_chain(depth, breadth=1):
    """Deep cascade: a chain of `depth` nodes, each level with `breadth` leaves."""
    root = Node("n0")
    node = root
    for level in range(1, depth + 1):
        nxt = Node(f"n{level}", mat_translation(0.5, 0.0, 0.0), parent=node)
        for s in range(breadth):
            Node(f"n{level}s{s}", mat_translation(0.0, 0.1 * (s + 1), 0.0), parent=node)
        node = nxt
    return root, node  # root and deepest chain node


def count_nodes(root):
    stack = [root]
    total = 0
    while stack:
        node = stack.pop()
        total += 1
        stack.extend(node.children)
    return total
