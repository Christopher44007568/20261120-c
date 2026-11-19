"""Topological validation of triangle meshes."""


def analyze(verts, tris):
    """Return dict with boundary/non-manifold counts, Euler characteristic,
    connected components and per-component genus (closed orientable assumed)."""
    edge_count = {}
    edge_dir = {}
    for a, b, c in tris:
        for e0, e1 in ((a, b), (b, c), (c, a)):
            key = (e0, e1) if e0 < e1 else (e1, e0)
            edge_count[key] = edge_count.get(key, 0) + 1
            edge_dir.setdefault(key, set()).add((e0, e1))
    boundary = sum(1 for v in edge_count.values() if v == 1)
    nonmanifold = sum(1 for v in edge_count.values() if v > 2)
    # orientation consistency: every shared edge must appear in both directions
    misoriented = sum(1 for k, v in edge_count.items()
                      if v == 2 and len(edge_dir[k]) != 2)

    used = set()
    for a, b, c in tris:
        used.update((a, b, c))
    v_count = len(used)
    e_count = len(edge_count)
    f_count = len(tris)
    chi = v_count - e_count + f_count

    # connected components via union-find over vertices
    parent = {v: v for v in used}

    def find(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b, c in tris:
        union(a, b)
        union(a, c)

    comp_verts = {}
    for v in used:
        comp_verts.setdefault(find(v), set()).add(v)
    comp_edges = {}
    comp_faces = {}
    for (e0, e1) in edge_count:
        r = find(e0)
        comp_edges[r] = comp_edges.get(r, 0) + 1
    for a, b, c in tris:
        r = find(a)
        comp_faces[r] = comp_faces.get(r, 0) + 1

    components = []
    for r, vs in comp_verts.items():
        c_chi = len(vs) - comp_edges.get(r, 0) + comp_faces.get(r, 0)
        genus = (2 - c_chi) / 2.0
        components.append({"verts": len(vs), "chi": c_chi, "genus": genus})
    components.sort(key=lambda c: -c["verts"])

    return {
        "V": v_count, "E": e_count, "F": f_count, "chi": chi,
        "boundary_edges": boundary,
        "nonmanifold_edges": nonmanifold,
        "misoriented_edges": misoriented,
        "components": len(components),
        "component_detail": components,
        "watertight": boundary == 0 and nonmanifold == 0,
    }


def fmt_report(name, stats, extra=""):
    lines = [f"[{name}] {extra}",
             f"  V={stats['V']} E={stats['E']} F={stats['F']} "
             f"chi={stats['chi']} components={stats['components']}",
             f"  boundary_edges={stats['boundary_edges']} "
             f"nonmanifold_edges={stats['nonmanifold_edges']} "
             f"misoriented_edges={stats['misoriented_edges']} "
             f"watertight={stats['watertight']}"]
    for i, c in enumerate(stats["component_detail"][:4]):
        lines.append(f"  comp{i}: verts={c['verts']} chi={c['chi']} genus={c['genus']:.1f}")
    return "\n".join(lines)
