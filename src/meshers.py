"""Marching tetrahedra and marching cubes meshers with welded vertices.

Grid convention (VTK hexahedron ordering):
  v0=(0,0,0) v1=(1,0,0) v2=(1,1,0) v3=(0,1,0)
  v4=(0,0,1) v5=(1,0,1) v6=(1,1,1) v7=(0,1,1)  (local offsets)
Inside means field value > iso.
"""
from mc_table import MC_TRI_TABLE

CUBE_OFFSETS = [
    (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
    (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
]

CUBE_EDGES = [
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (3, 7), (2, 6),
]

# 6 tetrahedra around the main diagonal v0-v6; face diagonals match across
# neighbouring cells, so the decomposition is globally consistent.
TETS = [
    (0, 6, 1, 2), (0, 6, 2, 3), (0, 6, 3, 7),
    (0, 6, 7, 4), (0, 6, 4, 5), (0, 6, 5, 1),
]


def _node_id(x, y, z, n):
    return x + n * (y + n * z)


class MeshBuilder:
    def __init__(self, data, n, iso):
        self.data = data
        self.n = n
        self.iso = iso
        self.verts = []
        self.vert_map = {}
        self.tris = []

    def edge_vertex(self, id_a, id_b):
        """Welded intersection vertex on the grid edge (id_a, id_b)."""
        key = (id_a, id_b) if id_a < id_b else (id_b, id_a)
        idx = self.vert_map.get(key)
        if idx is not None:
            return idx
        n = self.n
        ax, ay, az = key[0] % n, (key[0] // n) % n, key[0] // (n * n)
        bx, by, bz = key[1] % n, (key[1] // n) % n, key[1] // (n * n)
        fa, fb = self.data[key[0]], self.data[key[1]]
        denom = fb - fa
        t = 0.5 if denom == 0.0 else (self.iso - fa) / denom
        h = 2.0 / (n - 1)
        px = -1.0 + (ax + (bx - ax) * t) * h
        py = -1.0 + (ay + (by - ay) * t) * h
        pz = -1.0 + (az + (bz - az) * t) * h
        idx = len(self.verts)
        self.vert_map[key] = idx
        self.verts.append((px, py, pz))
        return idx

    def node_pos(self, nid):
        n = self.n
        h = 2.0 / (n - 1)
        x, y, z = nid % n, (nid // n) % n, nid // (n * n)
        return (-1.0 + x * h, -1.0 + y * h, -1.0 + z * h)

    def add_tri(self, a, b, c):
        if a != b and b != c and a != c:
            self.tris.append((a, b, c))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _orient_out(mb, tri, inside_pts):
    """Order triangle so its normal points away from the inside reference."""
    p = [mb.verts[i] for i in tri]
    normal = _cross(_sub(p[1], p[0]), _sub(p[2], p[0]))
    centroid = ((p[0][0] + p[1][0] + p[2][0]) / 3.0,
                (p[0][1] + p[1][1] + p[2][1]) / 3.0,
                (p[0][2] + p[1][2] + p[2][2]) / 3.0)
    ref = tuple(sum(q[i] for q in inside_pts) / len(inside_pts) for i in range(3))
    if _dot(normal, _sub(centroid, ref)) < 0.0:
        return (tri[0], tri[2], tri[1])
    return tri


def _cell_nodes(x, y, z, n):
    return [_node_id(x + dx, y + dy, z + dz, n) for dx, dy, dz in CUBE_OFFSETS]


def marching_tetrahedra(data, n, iso=0.0):
    """Extract isosurface; returns (mesh, tet_count)."""
    mb = MeshBuilder(data, n, iso)
    tet_count = 0
    for z in range(n - 1):
        for y in range(n - 1):
            for x in range(n - 1):
                nodes = _cell_nodes(x, y, z, n)
                vals = [data[v] for v in nodes]
                for tet in TETS:
                    tet_count += 1
                    ids = [nodes[i] for i in tet]
                    inside = [i for i in range(4) if vals[tet[i]] > iso]
                    k = len(inside)
                    if k == 0 or k == 4:
                        continue
                    if k == 1 or k == 3:
                        # one vertex cut off -> single triangle
                        lone = inside[0] if k == 1 else [i for i in range(4) if i not in inside][0]
                        others = [i for i in range(4) if i != lone]
                        pts = [mb.edge_vertex(ids[lone], ids[o]) for o in others]
                        in_pts = [mb.node_pos(ids[lone])] if k == 1 else \
                            [mb.node_pos(ids[o]) for o in inside]
                        mb.add_tri(*_orient_out(mb, pts, in_pts))
                    else:
                        # two inside, two outside -> quad split into 2 triangles
                        a, b = inside
                        c, d = [i for i in range(4) if i not in inside]
                        p_ac = mb.edge_vertex(ids[a], ids[c])
                        p_ad = mb.edge_vertex(ids[a], ids[d])
                        p_bc = mb.edge_vertex(ids[b], ids[c])
                        p_bd = mb.edge_vertex(ids[b], ids[d])
                        in_pts = [mb.node_pos(ids[a]), mb.node_pos(ids[b])]
                        mb.add_tri(*_orient_out(mb, (p_ac, p_ad, p_bd), in_pts))
                        mb.add_tri(*_orient_out(mb, (p_ac, p_bd, p_bc), in_pts))
    return (mb.verts, mb.tris), tet_count


def marching_cubes(data, n, iso=0.0):
    """Classic Lorensen-Cline marching cubes (VTK case table)."""
    mb = MeshBuilder(data, n, iso)
    for z in range(n - 1):
        for y in range(n - 1):
            for x in range(n - 1):
                nodes = _cell_nodes(x, y, z, n)
                case = 0
                for i, v in enumerate(nodes):
                    if data[v] > iso:
                        case |= 1 << i
                if case == 0 or case == 255:
                    continue
                table = MC_TRI_TABLE[case]
                edge_vert = {}
                def ev(e):
                    if e not in edge_vert:
                        a, b = CUBE_EDGES[e]
                        edge_vert[e] = mb.edge_vertex(nodes[a], nodes[b])
                    return edge_vert[e]
                for t in range(0, len(table), 3):
                    # VTK table is oriented for inside = f > iso already
                    mb.add_tri(ev(table[t]), ev(table[t + 2]), ev(table[t + 1]))
    return mb.verts, mb.tris
