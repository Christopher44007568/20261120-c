import tempfile
import unittest
from pathlib import Path

import numpy as np

from poisson_recon.benchmark import BenchmarkConfig, run_benchmark
from poisson_recon.clouds import (
    estimate_normals_pca,
    radial_error_metrics,
    sample_shape,
    sphere_shape,
)
from poisson_recon.reconstruct import (
    _screened_poisson,
    safe_poisson_reconstruct,
)


class PoissonReconstructionTests(unittest.TestCase):
    def test_pca_normals_point_outward(self) -> None:
        shape = sphere_shape(0.5)
        rng = np.random.default_rng(7)
        points, _ = sample_shape(shape, 3000, rng, noise_sigma=0.005)
        normals = estimate_normals_pca(points, neighbors=25, center=np.zeros(3))
        dots = np.einsum("ij,ij->i", normals, points)
        self.assertGreater(float(np.mean(dots > 0.0)), 0.99)

    def test_screened_poisson_fallback_reconstructs_sphere(self) -> None:
        shape = sphere_shape(0.5)
        rng = np.random.default_rng(8)
        points, _ = sample_shape(shape, 5000, rng, noise_sigma=0.0)
        normals = estimate_normals_pca(points, neighbors=25, center=np.zeros(3))
        result = _screened_poisson(points, normals, grid_n=96)
        self.assertGreater(len(result.vertices), 1000)
        self.assertGreater(len(result.faces), 1000)
        metrics = radial_error_metrics(result.vertices, shape)
        self.assertLess(metrics["radial_rmse_mm"], 10.0)

    def test_poisson_smooths_noise(self) -> None:
        shape = sphere_shape(0.5)
        rng = np.random.default_rng(9)
        clean, _ = sample_shape(shape, 6000, rng, noise_sigma=0.0)
        clean_normals = estimate_normals_pca(clean, neighbors=25, center=np.zeros(3))
        clean_recon = safe_poisson_reconstruct(clean, clean_normals)
        clean_metrics = radial_error_metrics(clean_recon.vertices, shape)

        noisy, _ = sample_shape(shape, 6000, rng, noise_sigma=0.02)
        noisy_normals = estimate_normals_pca(
            noisy, neighbors=25, center=np.zeros(3)
        )
        noisy_recon = safe_poisson_reconstruct(noisy, noisy_normals)
        noisy_metrics = radial_error_metrics(noisy_recon.vertices, shape)
        raw_metrics = radial_error_metrics(noisy, shape)

        self.assertLess(clean_metrics["radial_rmse_mm"], 2.0)
        self.assertLess(noisy_metrics["radial_rmse_mm"], raw_metrics["radial_rmse_mm"])
        self.assertLess(noisy_metrics["radial_rmse_mm"], 12.0)

    def test_quick_benchmark_reports_robustness(self) -> None:
        config = BenchmarkConfig(
            n_points=4000,
            n_ground_truth=8000,
            seeds=(0,),
            noise_fractions=(0.0, 0.02, 0.04),
            depth=7,
        )
        with tempfile.TemporaryDirectory() as directory:
            payload = run_benchmark(directory, config, make_plots=False)
            self.assertTrue(Path(directory, "poisson_summary.json").exists())
        for shape, check in payload["checks"].items():
            self.assertTrue(check["clean_rmse_pass"], shape)
            self.assertTrue(check["always_better_than_raw"], shape)
            self.assertTrue(check["graceful_degradation_pass"], shape)


if __name__ == "__main__":
    unittest.main()
