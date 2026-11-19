"""Anisotropic Gaussian-mixture fitting with under-fit diagnostics."""
import numpy as np
from scipy.spatial import cKDTree


def box_surface_samples(half=0.7, n_per_face=1500, rng=None):
    """Uniform samples on the 6 faces of a box, with a face label each."""
    rng = rng or np.random.default_rng(0)
    pts, labels = [], []
    for axis in range(3):
        for sign in (-1.0, 1.0):
            p = (rng.random((n_per_face, 3)) * 2 - 1) * half
            p[:, axis] = sign * half
            pts.append(p)
            labels.append(np.full(n_per_face, f"{'xyz'[axis]}{'+' if sign > 0 else '-'}"))
    return np.concatenate(pts), np.concatenate(labels)


def fit_gmm(x, k, n_iter=80, reg=1e-6, rng=None):
    """Plain EM for a full-covariance Gaussian mixture."""
    rng = rng or np.random.default_rng(0)
    n, d = x.shape
    idx = rng.choice(n, size=k, replace=False)
    means = x[idx].copy()
    covs = np.tile(np.eye(d) * x.var(axis=0).mean(), (k, 1, 1))
    weights = np.full(k, 1.0 / k)
    for _ in range(n_iter):
        resp = np.zeros((n, k))
        for c in range(k):
            cov = covs[c] + reg * np.eye(d)
            _, logdet = np.linalg.slogdet(cov)
            inv = np.linalg.inv(cov)
            diff = x - means[c]
            maha = np.einsum("ij,jk,ik->i", diff, inv, diff)
            resp[:, c] = np.log(weights[c] + 1e-300) - 0.5 * (maha + logdet)
        resp -= resp.max(axis=1, keepdims=True)
        resp = np.exp(resp)
        resp /= resp.sum(axis=1, keepdims=True)
        nk = resp.sum(axis=0) + 1e-12
        weights = nk / n
        means = (resp.T @ x) / nk[:, None]
        for c in range(k):
            diff = x - means[c]
            covs[c] = (resp[:, c][:, None] * diff).T @ diff / nk[c]
    return means, covs, weights


def sample_gmm(means, covs, weights, n, rng=None):
    rng = rng or np.random.default_rng(0)
    counts = rng.multinomial(n, weights)
    out = []
    for c in range(len(weights)):
        if counts[c]:
            out.append(rng.multivariate_normal(means[c], covs[c], size=counts[c]))
    return np.concatenate(out)


def diagnose(samples, labels, means, covs, weights, k):
    """Error report plus directional-artefact detection for a fitted GMM."""
    rng = np.random.default_rng(1)
    gen = sample_gmm(means, covs, weights, len(samples), rng)
    tree = cKDTree(gen)
    dist = tree.query(samples)[0]
    per_dir = {}
    for lab in np.unique(labels):
        per_dir[lab] = float(dist[labels == lab].mean())
    vals = np.array(list(per_dir.values()))
    anisotropy = float(vals.max() / max(vals.min(), 1e-12))
    return {
        "k": k,
        "err_mean": float(dist.mean()),
        "err_max": float(dist.max()),
        "per_direction_error": per_dir,
        "anisotropy": anisotropy,
        # A box has 6 planar faces; fewer Gaussians cannot represent them.
        "insufficient": k < 6,
        "directional_artifact": bool(anisotropy > 2.0),
    }
