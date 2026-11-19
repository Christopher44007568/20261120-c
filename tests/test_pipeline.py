"""Smoke tests for the Poisson reconstruction pipeline."""

import numpy as np

from poisson_surface_recon import (
    sample_sphere,
    sample_torus,
    estimate_normals,
    make_normals_inconsistent,
    orient_normals_consistent,
    normal_consistency_rate,
    poisson_reconstruct,
    reconstruction_errors,
    mesh_smoothness,
)


def test_normals_are_unit_vectors():
    rng = np.random.default_rng(0)
    points, normals = sample_sphere(1000, noise_sigma=0.01, rng=rng)
    assert points.shape == (1000, 3)
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0)


def test_torus_sampling():
    rng = np.random.default_rng(1)
    points, normals = sample_torus(1500, rng=rng)
    assert points.shape == normals.shape == (1500, 3)
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0)


def test_alignment_restores_consistency():
    rng = np.random.default_rng(2)
    points, gt_normals = sample_sphere(2500, noise_sigma=0.02, rng=rng)
    _, estimated = estimate_normals(points)
    inconsistent, flip_mask = make_normals_inconsistent(
        estimated, 0.4, rng
    )
    assert flip_mask.sum() == 1000
    aligned = orient_normals_consistent(points, inconsistent)
    assert normal_consistency_rate(aligned, gt_normals) > 0.97


def test_poisson_reduces_error_after_alignment():
    rng = np.random.default_rng(3)
    points, gt_normals = sample_sphere(3000, noise_sigma=0.02, rng=rng)
    _, estimated = estimate_normals(points)
    inconsistent, _ = make_normals_inconsistent(estimated, 0.35, rng)
    aligned = orient_normals_consistent(points, inconsistent)

    mesh_before, info_before = poisson_reconstruct(
        points, inconsistent, depth=7
    )
    mesh_after, info_after = poisson_reconstruct(points, aligned, depth=7)

    assert info_before["n_vertices"] > 0
    assert info_before["elapsed_sec"] > 0
    err_before = reconstruction_errors(mesh_before, points, 5000, rng)
    err_after = reconstruction_errors(mesh_after, points, 5000, rng)
    assert err_after["chamfer"] < err_before["chamfer"]

    smooth = mesh_smoothness(mesh_after)
    assert smooth["normal_variation_deg"] > 0
    assert smooth["edge_length_cv"] > 0
