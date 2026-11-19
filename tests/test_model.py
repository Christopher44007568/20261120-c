import unittest

import numpy as np

from asg_experiment.integration import (
    asg_brightness,
    asg_integral,
    asg_pair_integral,
    monte_carlo_brightness,
    real_sh_basis,
)
from asg_experiment.model import ASG, DirectionalEnvironment, fibonacci_sphere, normalize


class ASGIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = fibonacci_sphere(200000, offset=0.173)
        cls.solid_angle_weight = 4.0 * np.pi / cls.grid.shape[0]

    def test_single_asg_closed_form_integral(self):
        for sigma_u, sigma_v in ((0.08, 0.24), (0.15, 0.15), (0.30, 0.42)):
            lobe = ASG(np.array([0.0, 0.0, 1.0]), sigma_u, sigma_v, 0.0, 1.0)
            numerical = self.solid_angle_weight * np.sum(lobe.evaluate(self.grid))
            closed_form = asg_integral(1.0, lobe.lambda_u, lobe.lambda_v)
            self.assertLess(abs(closed_form / numerical - 1.0), 0.02)

    def test_asg_product_integral(self):
        first = ASG(normalize(np.array([0.1, 0.2, 1.0])), 0.12, 0.28, 0.2, 1.0)
        second = ASG(normalize(np.array([0.2, 0.0, 1.0])), 0.18, 0.22, -0.4, 0.8)
        numerical = (
            self.solid_angle_weight
            * np.sum(first.evaluate(self.grid) * second.evaluate(self.grid))
        )
        closed_form = asg_pair_integral(first, second)
        self.assertLess(abs(closed_form / numerical - 1.0), 0.06)

    def test_real_sh_is_orthonormal(self):
        small_grid = fibonacci_sphere(120000, offset=0.41)
        basis, _ = real_sh_basis(small_grid, 4)
        gram = (4.0 * np.pi / small_grid.shape[0]) * (basis.T @ basis)
        self.assertLess(np.max(np.abs(gram - np.eye(basis.shape[1]))), 2e-4)

    def test_asg_brightness_matches_monte_carlo(self):
        environment = DirectionalEnvironment.studio()
        normals = normalize(
            np.array(
                [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                    [-1.0, 0.0, 0.0],
                ]
            )
        )
        sigma_u, sigma_v = 0.14, 0.24
        monte_carlo, standard_error = monte_carlo_brightness(
            environment,
            normals,
            sigma_u,
            sigma_v,
            sample_count=1 << 18,
            seed=19,
        )
        analytic = asg_brightness(
            environment.lobes,
            normals,
            sigma_u,
            sigma_v,
            ambient=environment.ambient,
        )
        tolerance = np.maximum(0.05 * monte_carlo, 4.0 * standard_error)
        self.assertTrue(np.all(np.abs(analytic - monte_carlo) <= tolerance))


if __name__ == "__main__":
    unittest.main()
