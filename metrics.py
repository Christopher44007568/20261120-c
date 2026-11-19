"""Reconstruction error and sharp-feature metrics."""
import numpy as np
from scipy.spatial import cKDTree


def sample_mesh(verts, faces, n_samples, rng=None):
    """Area-weighted uniform point sampling on a triangle mesh."""
    rng = rng or np.random.default_rng(0)
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    areas = 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1)
    total = areas.sum()
    if total <= 0:
        return verts.copy()
    prob = areas / total
    idx = rng.choice(len(faces), size=n_samples, p=prob)
    r1 = np.sqrt(rng.random(n_samples))[:, None]
    r2 = rng.random(n_samples)[:, None]
    p = (1 - r1) * v0[idx] + r1 * (1 - r2) * v1[idx] + r1 * r2 * v2[idx]
    return p


def chamfer(pa, pb):
    """Symmetric chamfer distance between two point sets."""
    ta = cKDTree(pa)
    tb = cKDTree(pb)
    da = ta.query(pb)[0]
    db = tb.query(pa)[0]
    d = np.concatenate([da, db])
    return {
        "chamfer_mean": float(d.mean()),
        "chamfer_rms": float(np.sqrt((d ** 2).mean())),
        "chamfer_max": float(d.max()),
    }


def sdf_error(f, verts):
    """How far mesh vertices are from the true zero level set."""
    e = np.abs(f(verts))
    return {
        "sdf_mean": float(e.mean()),
        "sdf_rms": float(np.sqrt((e ** 2).mean())),
        "sdf_max": float(e.max()),
    }


def edge_distance(edge_pts, verts, faces, n_mesh_samples=60000):
    """Distance from true sharp-edge samples to the reconstructed mesh.

    Approximated with a dense point sampling of the mesh (KD-tree).
    """
    mp = sample_mesh(verts, faces, n_mesh_samples, rng=np.random.default_rng(1))
    tree = cKDTree(mp)
    d = tree.query(edge_pts)[0]
    return {
        "edge_mean": float(d.mean()),
        "edge_rms": float(np.sqrt((d ** 2).mean())),
        "edge_max": float(d.max()),
    }


def save_obj(path, verts, faces):
    with open(path, "w") as fh:
        for v in verts:
            fh.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for t in faces:
            fh.write(f"f {t[0]+1} {t[1]+1} {t[2]+1}\n")
