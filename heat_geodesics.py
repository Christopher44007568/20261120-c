"""Heat-method geodesic distances on a gridded surface with obstacles.

Pipeline (Crane et al., 2013):
  1. diffuse a Dirac delta:  (M + t*K) u = delta
  2. evaluate per-face gradients, normalize -> X
  3. solve Poisson:          K phi = div(X)
Reference distances come from Dijkstra on the mesh graph.
"""

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.sparse.csgraph import dijkstra as cs_dijkstra


OBSTACLES = [((0.50, 0.48), 0.13), ((0.68, 0.66), 0.09)]


def build_mesh(n=60):
    """Grid surface over [0,1]^2 with two bumps; obstacle disks are cut out."""
    xs = np.linspace(0.0, 1.0, n)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    Z = (0.18 * np.exp(-((X - 0.30) ** 2 + (Y - 0.72) ** 2) / 0.015)
         + 0.12 * np.exp(-((X - 0.75) ** 2 + (Y - 0.25) ** 2) / 0.020))
    verts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])

    def vid(i, j):
        return i * n + j

    faces = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b = vid(i, j), vid(i + 1, j)
            c, d = vid(i, j + 1), vid(i + 1, j + 1)
            faces.append((a, b, d))
            faces.append((a, d, c))
    faces = np.array(faces)

    keep = np.ones(len(faces), dtype=bool)
    for (cx, cy), r in OBSTACLES:
        inside = (verts[:, 0] - cx) ** 2 + (verts[:, 1] - cy) ** 2 <= r ** 2
        keep &= ~inside[faces].any(axis=1)
    faces = faces[keep]

    used = np.unique(faces)
    remap = np.full(len(verts), -1)
    remap[used] = np.arange(len(used))
    return verts[used], remap[faces]


def mesh_operators(verts, faces):
    """Lumped mass matrix M and positive-semidefinite cotan stiffness K."""
    i0, i1, i2 = faces.T
    p0, p1, p2 = verts[i0], verts[i1], verts[i2]
    e0, e1, e2 = p2 - p1, p0 - p2, p1 - p0  # edge opposite p0, p1, p2

    cross = np.cross(p1 - p0, p2 - p0)
    area2 = np.linalg.norm(cross, axis=1)
    area = 0.5 * area2

    # cotangents of angles at p0, p1, p2
    cot0 = np.einsum("ij,ij->i", -e1, e2) / area2
    cot1 = np.einsum("ij,ij->i", -e2, e0) / area2
    cot2 = np.einsum("ij,ij->i", -e0, e1) / area2

    rows = np.concatenate([i0, i1, i1, i2, i2, i0])
    cols = np.concatenate([i1, i0, i2, i1, i0, i2])
    vals = 0.5 * np.concatenate([cot2, cot2, cot0, cot0, cot1, cot1])
    K = sp.coo_matrix((vals, (rows, cols)),
                      shape=(len(verts), len(verts))).tocsr()
    K = K + sp.diags(-np.asarray(K.sum(axis=1)).ravel())
    K = -K  # positive semidefinite stiffness form

    M = sp.diags(np.bincount(faces.ravel(), weights=np.repeat(area / 3.0, 3),
                             minlength=len(verts)))
    return M, K, area


def face_gradients(verts, faces, area):
    """Per-face gradient bases: grad of hat function at each corner."""
    i0, i1, i2 = faces.T
    p0, p1, p2 = verts[i0], verts[i1], verts[i2]
    n = np.cross(p1 - p0, p2 - p0)
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    g0 = np.cross(n, p2 - p1) / (2.0 * area)[:, None]
    g1 = np.cross(n, p0 - p2) / (2.0 * area)[:, None]
    g2 = np.cross(n, p1 - p0) / (2.0 * area)[:, None]
    return g0, g1, g2


def heat_distance(verts, faces, M, K, area, src, t, substeps=1):
    """Geodesic distance from vertex `src` via the heat method."""
    rhs = np.zeros(len(verts))
    rhs[src] = 1.0
    A = M + (t / substeps) * K
    solve = spla.factorized(A.tocsc())
    u = rhs
    for _ in range(substeps):
        u = solve(u)

    g0, g1, g2 = face_gradients(verts, faces, area)
    grad_u = u[faces[:, 0, None]] * g0 + u[faces[:, 1, None]] * g1 \
        + u[faces[:, 2, None]] * g2
    norm = np.linalg.norm(grad_u, axis=1)
    norm[norm < 1e-12] = 1.0
    Xf = -grad_u / norm[:, None]

    # weak-form integrated divergence: div_i = sum_f A_f * grad(hat_i) . X_f
    div = np.zeros(len(verts))
    for corner, g in enumerate((g0, g1, g2)):
        np.add.at(div, faces[:, corner],
                  area * np.einsum("ij,ij->i", g, Xf))

    # Poisson solve with phi pinned to 0 at the source
    free = np.arange(len(verts)) != src
    Kf = K[free][:, free].tocsc()
    phi = np.zeros(len(verts))
    phi[free] = spla.spsolve(Kf, div[free])
    phi -= phi.min()
    return phi


def dijkstra_distance(verts, faces, src):
    """Exact graph geodesic (reference) via Dijkstra on mesh edges."""
    i0, i1, i2 = faces.T
    edges = np.vstack([np.column_stack([i0, i1]),
                       np.column_stack([i1, i2]),
                       np.column_stack([i2, i0])])
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    w = np.linalg.norm(verts[edges[:, 0]] - verts[edges[:, 1]], axis=1)
    G = sp.coo_matrix((w, (edges[:, 0], edges[:, 1])),
                      shape=(len(verts), len(verts))).tocsr()
    G = G + G.T
    return cs_dijkstra(G, directed=False, indices=src)


def adjacency(faces, nverts):
    adj = [set() for _ in range(nverts)]
    for a, b, c in faces:
        adj[a].update((b, c))
        adj[b].update((a, c))
        adj[c].update((a, b))
    return [sorted(s) for s in adj]


def trace_path(verts, adj, dist, src, tgt):
    """Descend the distance field from tgt to src (geodesic path)."""
    path = [tgt]
    while path[-1] != src:
        cur = path[-1]
        nxt = min(adj[cur], key=lambda v: dist[v])
        if dist[nxt] >= dist[cur]:
            raise RuntimeError("descent stalled")
        path.append(nxt)
        if len(path) > len(verts):
            raise RuntimeError("descent looped")
    return np.array(path)


def path_length(verts, path):
    seg = verts[path[1:]] - verts[path[:-1]]
    return float(np.linalg.norm(seg, axis=1).sum())


def dijkstra_path(verts, faces, src, tgt):
    i0, i1, i2 = faces.T
    edges = np.vstack([np.column_stack([i0, i1]),
                       np.column_stack([i1, i2]),
                       np.column_stack([i2, i0])])
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    w = np.linalg.norm(verts[edges[:, 0]] - verts[edges[:, 1]], axis=1)
    G = sp.coo_matrix((w, (edges[:, 0], edges[:, 1])),
                      shape=(len(verts), len(verts))).tocsr()
    G = G + G.T
    _, pred = cs_dijkstra(G, directed=False, indices=src,
                          return_predecessors=True)
    path = [tgt]
    while path[-1] != src:
        path.append(int(pred[path[-1]]))
    return np.array(path[::-1])


def segment_hits_obstacle(p, q, obstacles):
    """Does xy segment p->q cross any obstacle disk?"""
    p2, q2 = p[:2], q[:2]
    d = q2 - p2
    dd = float(d @ d)
    for (cx, cy), r in obstacles:
        c = np.array([cx, cy])
        t = 0.0 if dd == 0 else np.clip(((c - p2) @ d) / dd, 0.0, 1.0)
        if np.linalg.norm(p2 + t * d - c) < r:
            return True
    return False


def path_clear_of_obstacles(verts, path, obstacles, tol=1e-9):
    xy = verts[path][:, :2]
    for (cx, cy), r in obstacles:
        if np.any((xy[:, 0] - cx) ** 2 + (xy[:, 1] - cy) ** 2 < (r - tol) ** 2):
            return False
    return True


def heat_distance_cg(verts, faces, M, K, area, src, t, maxiter):
    """Heat distance with the diffusion solve limited to `maxiter` CG steps."""
    rhs = np.zeros(len(verts))
    rhs[src] = 1.0
    u, _ = spla.cg(M + t * K, rhs, rtol=0.0, atol=0.0, maxiter=maxiter)
    g0, g1, g2 = face_gradients(verts, faces, area)
    grad_u = u[faces[:, 0, None]] * g0 + u[faces[:, 1, None]] * g1 \
        + u[faces[:, 2, None]] * g2
    norm = np.linalg.norm(grad_u, axis=1)
    norm[norm < 1e-12] = 1.0
    Xf = -grad_u / norm[:, None]
    div = np.zeros(len(verts))
    for corner, g in enumerate((g0, g1, g2)):
        np.add.at(div, faces[:, corner],
                  area * np.einsum("ij,ij->i", g, Xf))
    free = np.arange(len(verts)) != src
    phi = np.zeros(len(verts))
    phi[free] = spla.spsolve(K[free][:, free].tocsc(), div[free])
    phi -= phi.min()
    return phi


def cg_error_curve(verts, faces, M, K, area, src, t, d_ref, iters):
    """Relative L2 error of the heat distance vs CG iteration count."""
    mask = d_ref > 1e-3
    out = []
    for k in iters:
        phi = heat_distance_cg(verts, faces, M, K, area, src, t, k)
        rel = np.linalg.norm(phi[mask] - d_ref[mask]) \
            / np.linalg.norm(d_ref[mask])
        out.append(rel)
    return out


def tile_stats(verts, faces, tile_size, visible_center, visible_radius):
    """Per-tile triangle counts and frustum-style culling benefit."""
    cent = verts[faces].mean(axis=1)[:, :2]
    tidx = np.floor(cent / tile_size).astype(int)
    keys, inv = np.unique(tidx, axis=0, return_inverse=True)
    counts = np.bincount(inv)
    # a tile is culled if its AABB does not intersect the visible disk
    lo = keys * tile_size
    hi = lo + tile_size
    c = np.asarray(visible_center)
    closest = np.clip(c, lo, hi)
    tile_visible = ((closest - c) ** 2).sum(axis=1) <= visible_radius ** 2
    drawn = int(counts[tile_visible].sum())
    exact = int((((cent - c) ** 2).sum(axis=1) <= visible_radius ** 2).sum())
    return {"tile_size": tile_size, "n_tiles": len(keys),
            "counts": counts, "keys": keys,
            "drawn": drawn, "exact_visible": exact,
            "overdraw": drawn / max(exact, 1)}


def main():
    import os
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")
    os.makedirs(out, exist_ok=True)

    verts, faces = build_mesh()
    M, K, area = mesh_operators(verts, faces)
    h = float(np.sqrt(2.0 * area.mean()))
    print(f"mesh: {len(verts)} verts, {len(faces)} faces, h={h:.4f}")

    src = int(np.argmin((verts[:, 0] - 0.08) ** 2 + (verts[:, 1] - 0.08) ** 2))
    tgt = int(np.argmin((verts[:, 0] - 0.92) ** 2 + (verts[:, 1] - 0.92) ** 2))
    t = 4.0 * h * h

    d_ref = dijkstra_distance(verts, faces, src)
    phi = heat_distance(verts, faces, M, K, area, src, t=t, substeps=1)
    mask = d_ref > 1e-3
    rel = np.linalg.norm(phi[mask] - d_ref[mask]) / np.linalg.norm(d_ref[mask])
    print(f"heat vs dijkstra: rel L2 = {rel:.4%}")

    # ---- iteration / error study -------------------------------------
    t_mults = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0]
    t_errs = []
    for tm in t_mults:
        p = heat_distance(verts, faces, M, K, area, src, t=tm * h * h)
        t_errs.append(np.linalg.norm(p[mask] - d_ref[mask])
                      / np.linalg.norm(d_ref[mask]))
    cg_iters = [1, 2, 3, 5, 8, 12, 20, 40, 80, 160]
    cg_errs = cg_error_curve(verts, faces, M, K, area, src, t, d_ref, cg_iters)
    print("t mults :", t_mults)
    print("t errs  :", [f"{e:.4f}" for e in t_errs])
    print("cg iters:", cg_iters)
    print("cg errs :", [f"{e:.4f}" for e in cg_errs])

    # ---- shortest paths & obstacle-detour verification ----------------
    adj = adjacency(faces, len(verts))
    heat_path = trace_path(verts, adj, phi, src, tgt)
    dij_path = dijkstra_path(verts, faces, src, tgt)
    euclid = float(np.linalg.norm(verts[tgt] - verts[src]))
    len_heat, len_dij = path_length(verts, heat_path), path_length(verts, dij_path)
    straight_blocked = segment_hits_obstacle(verts[src], verts[tgt], OBSTACLES)
    heat_clear = path_clear_of_obstacles(verts, heat_path, OBSTACLES)
    dij_clear = path_clear_of_obstacles(verts, dij_path, OBSTACLES)
    print(f"straight src->tgt blocked by obstacle: {straight_blocked}")
    print(f"heat path: {len(heat_path)} verts, len={len_heat:.4f}, clear={heat_clear}")
    print(f"dijkstra : {len(dij_path)} verts, len={len_dij:.4f}, clear={dij_clear}")
    print(f"euclidean straight-line distance: {euclid:.4f}")
    print(f"detour ratio heat/euclid={len_heat/euclid:.3f} "
          f"heat/dijkstra={len_heat/len_dij:.3f}")

    # ---- tiles ---------------------------------------------------------
    vis_center, vis_radius = (0.32, 0.30), 0.32
    tiles = [tile_stats(verts, faces, s, vis_center, vis_radius)
             for s in (0.5, 0.25, 0.125, 0.0625)]
    for ts in tiles:
        print(f"tile={ts['tile_size']:.4f} tiles={ts['n_tiles']:3d} "
              f"tris/tile avg={ts['counts'].mean():6.1f} "
              f"max={ts['counts'].max():4d} drawn={ts['drawn']:5d} "
              f"overdraw={ts['overdraw']:.2f}x")

    # ---- outputs -------------------------------------------------------
    np.savetxt(os.path.join(out, "distance_field.csv"),
               np.column_stack([verts, phi, d_ref]),
               delimiter=",",
               header="x,y,z,phi_heat,d_dijkstra", comments="")
    hp = np.column_stack([verts[heat_path], phi[heat_path]])
    dp = np.column_stack([verts[dij_path], d_ref[dij_path]])
    np.savetxt(os.path.join(out, "shortest_path_heat.csv"), hp, delimiter=",",
               header="x,y,z,dist_along_field", comments="")
    np.savetxt(os.path.join(out, "shortest_path_dijkstra.csv"), dp,
               delimiter=",", header="x,y,z,dist_along_graph", comments="")
    for ts in tiles:
        np.savetxt(os.path.join(out, f"tile_counts_{ts['tile_size']}.csv"),
                   np.column_stack([ts["keys"], ts["counts"]]),
                   delimiter=",", header="tile_i,tile_j,n_triangles",
                   comments="", fmt="%d")
    print("wrote CSV outputs to", out)
    return dict(verts=verts, faces=faces, phi=phi, d_ref=d_ref, src=src,
                tgt=tgt, heat_path=heat_path, dij_path=dij_path,
                t_mults=t_mults, t_errs=t_errs,
                cg_iters=cg_iters, cg_errs=cg_errs, tiles=tiles,
                len_heat=len_heat, len_dij=len_dij, euclid=euclid,
                straight_blocked=straight_blocked, heat_clear=heat_clear,
                dij_clear=dij_clear, rel=rel, out=out)


if __name__ == "__main__":
    main()
