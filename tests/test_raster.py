import unittest

from earlyz_overdraw.raster import (
    Metrics,
    Quad,
    run_pipeline,
)
from earlyz_overdraw.scenarios import make_scene, order_quads


def _stack(width=8, height=8, transparent=(), alpha_test=()):
    """Four fully overlapping quads with distinct depths."""
    quads = []
    for index, depth in enumerate((0.1, 0.2, 0.3, 0.4)):
        quads.append(Quad(
            quad_id=index, x0=0, y0=0, x1=width, y1=height, z=depth,
            transparent=index in transparent,
            alpha_test=index in alpha_test,
        ))
    return quads


class RasterCorrectnessTest(unittest.TestCase):
    def test_all_pipelines_shade_every_covered_pixel_without_early_z(self):
        quads = _stack()
        for order in ("front_to_back", "back_to_front", "random"):
            metrics = run_pipeline(
                "forward_no_early_z", 8, 8, quads, order)
            self.assertEqual(metrics.fragments_visited, 4 * 64)
            self.assertEqual(metrics.shader_invocations, 4 * 64)
            self.assertEqual(metrics.covered_pixels, 64)
            self.assertEqual(metrics.redundant_shaded, 3 * 64)

    def test_early_z_front_to_back_shades_once_per_pixel(self):
        quads = _stack()
        ordered = sorted(quads, key=lambda item: item.z)
        metrics = run_pipeline("forward_early_z", 8, 8, ordered,
                               "front_to_back")
        self.assertEqual(metrics.shader_invocations, 64)
        self.assertEqual(metrics.depth_rejects, 3 * 64)
        self.assertEqual(metrics.redundant_shaded, 0)

    def test_early_z_back_to_front_keeps_full_overdraw(self):
        quads = _stack()
        ordered = sorted(quads, key=lambda item: item.z, reverse=True)
        metrics = run_pipeline("forward_early_z", 8, 8, ordered,
                               "back_to_front")
        self.assertEqual(metrics.shader_invocations, 4 * 64)
        self.assertEqual(metrics.depth_rejects, 0)
        self.assertEqual(metrics.redundant_shaded, 3 * 64)

    def test_prepass_is_order_independent_and_shades_once(self):
        quads = _stack()
        results = []
        for order in ("front_to_back", "back_to_front", "random"):
            results.append(run_pipeline(
                "z_prepass", 8, 8, quads, order))
        for metrics in results:
            self.assertEqual(metrics.shader_invocations, 64)
            self.assertEqual(metrics.redundant_shaded, 0)
            self.assertEqual(metrics.pass_count, 2)
        self.assertEqual(results[0].model_cycles, results[1].model_cycles)

    def test_transparent_fragments_always_shaded(self):
        # Two blended quads in front of two opaque ones.
        quads = _stack(transparent=(0, 1))
        ordered = sorted(quads, key=lambda item: item.z)
        metrics = run_pipeline("forward_early_z", 8, 8, ordered,
                               "front_to_back")
        # Both transparent quads shade every pixel; opaque quads behind them
        # are rejected by the opaque depth buffer state only where applicable.
        self.assertEqual(metrics.blend_invocations, 2 * 64)
        self.assertGreaterEqual(metrics.shader_invocations, 2 * 64)

    def test_fully_transparent_scene_early_z_cannot_help(self):
        quads = _stack(transparent=(0, 1, 2, 3))
        for pipeline in ("forward_early_z", "z_prepass"):
            metrics = run_pipeline(pipeline, 8, 8, quads, "front_to_back")
            # Every blended fragment is shaded; no depth write means no reject.
            self.assertEqual(metrics.shader_invocations, 4 * 64)
            self.assertEqual(metrics.blend_invocations, 4 * 64)
            self.assertEqual(metrics.depth_rejects, 0)

    def test_alpha_test_quads_still_write_depth_and_benefit(self):
        quads = _stack(alpha_test=(0, 1, 2, 3))
        metrics = run_pipeline("z_prepass", 8, 8, quads, "front_to_back")
        self.assertEqual(metrics.shader_invocations, 64)
        self.assertEqual(metrics.redundant_shaded, 0)

    def test_shading_histogram_reflects_reduction(self):
        quads = _stack()
        baseline = run_pipeline(
            "forward_no_early_z", 8, 8, quads, "front_to_back")
        prepass = run_pipeline(
            "z_prepass", 8, 8, quads, "front_to_back")
        self.assertEqual(baseline.shading_histogram(), {4: 64})
        self.assertEqual(prepass.shading_histogram(), {1: 64})

    def test_unknown_pipeline_rejected(self):
        with self.assertRaises(ValueError):
            run_pipeline("nope", 8, 8, _stack(), "front_to_back")


class ScenarioTest(unittest.TestCase):
    def test_scene_is_seed_reproducible(self):
        first = make_scene("a", seed=7, count=10)
        second = make_scene("a", seed=7, count=10)
        self.assertEqual(first.quads, second.quads)

    def test_transparent_fractions_and_validation(self):
        scene = make_scene("a", seed=1, count=8,
                           transparent_fraction=0.5,
                           alpha_test_fraction=0.25)
        transparent = sum(quad.transparent for quad in scene.quads)
        alpha = sum(quad.alpha_test for quad in scene.quads)
        self.assertEqual(transparent, 4)
        self.assertEqual(alpha, 2)
        with self.assertRaises(ValueError):
            make_scene("bad", seed=1, transparent_fraction=0.8,
                       alpha_test_fraction=0.5)

    def test_heavy_scene_has_higher_overdraw_than_sparse(self):
        heavy = make_scene("heavy", seed=3, count=16, overlap="heavy")
        sparse = make_scene("sparse", seed=3, count=16, overlap="sparse")
        heavy_metrics: Metrics = run_pipeline(
            "forward_no_early_z", heavy.width, heavy.height,
            order_quads(heavy, "front_to_back"), "front_to_back")
        sparse_metrics: Metrics = run_pipeline(
            "forward_no_early_z", sparse.width, sparse.height,
            order_quads(sparse, "front_to_back"), "front_to_back")
        self.assertGreater(
            heavy_metrics.avg_draws_per_pixel(covered_only=True),
            sparse_metrics.avg_draws_per_pixel(covered_only=True))


if __name__ == "__main__":
    unittest.main()
