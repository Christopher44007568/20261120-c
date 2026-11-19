import unittest

from gpupool.residency import ResidencyManager
from gpupool.workload import compare_strategies, stability_run, pressure_run, \
    fragmentation_demo, churn_frag_curve


class ResidencyTest(unittest.TestCase):
    def test_transient_cache_reuse(self):
        manager = ResidencyManager(capacity=64, strategy="recycle")
        self.assertTrue(manager.create_transient("a", 8))
        manager.destroy("a")
        self.assertEqual(manager.cached_bytes, 8)
        self.assertTrue(manager.create_transient("b", 8))
        self.assertEqual(manager.cache_reuses, 1)
        self.assertEqual(manager.pool.allocations[
            next(iter(manager.pool.allocations))].size, 8)

    def test_naive_never_caches(self):
        manager = ResidencyManager(capacity=64, strategy="naive")
        manager.create_transient("a", 8)
        manager.destroy("a")
        self.assertEqual(manager.cached_bytes, 0)

    def test_eviction_of_inactive_persistent_resource(self):
        manager = ResidencyManager(capacity=64, strategy="recycle")
        manager.create_persistent("p1", 16)
        manager.create_persistent("p2", 30)
        manager.make_inactive("p1")
        self.assertTrue(manager.create_persistent("p3", 24))
        self.assertEqual(manager.evictions, 1)
        self.assertFalse(manager.resources["p1"].resident)
        manager.destroy("p3")
        self.assertTrue(manager.make_active("p1"))
        self.assertEqual(manager.reupload_bytes, 16)

    def test_compare_strategies_keeps_pool_stable(self):
        _, results = compare_strategies(capacity=256, ticks=25)
        self.assertEqual(results["naive"]["failures"], 0)
        self.assertLessEqual(results["recycle_compact"]["final_frag"],
                             results["naive"]["final_frag"])
        self.assertEqual(results["recycle_compact"]["free_segments"], 1)

    def test_pressure_run_recycle_reduces_failures(self):
        pressure = pressure_run(ticks=25, capacity=128)
        self.assertLessEqual(pressure["recycle_compact"]["failures"],
                             pressure["naive"]["failures"])

    def test_long_stability_run(self):
        stats = stability_run(ticks=120, seed=99)
        self.assertEqual(stats["failures"], 0)
        self.assertLess(stats["final_frag"], 0.3)
        self.assertLessEqual(stats["peak_committed"], 256)

    def test_fragmentation_demo_compaction_lowers_peak(self):
        demo = fragmentation_demo(capacity=192)
        self.assertLess(demo["recycle_compact"]["final_frag"],
                        demo["naive"]["final_frag"])
        self.assertLess(demo["recycle_compact"]["peak_committed"],
                        demo["naive"]["peak_committed"])
        self.assertLess(demo["recycle_compact"]["steady_committed"],
                        demo["naive"]["steady_committed"])
        self.assertLessEqual(demo["recycle_compact"]["failures"],
                             demo["naive"]["failures"])

    def test_churn_curve_stays_bounded(self):
        curve = churn_frag_curve(ticks=120, sample_every=20)
        self.assertEqual(len(curve), 6)
        for point in curve:
            self.assertLessEqual(point["frag"], 0.01)
            self.assertLessEqual(point["heap_blocks"], 8)
            self.assertLessEqual(point["committed"], 256)
        self.assertGreaterEqual(min(p["active_blocks"] for p in curve), 1)


if __name__ == "__main__":
    unittest.main()
