import unittest

from proctree.texture import (
    build_checker,
    build_mip_chain,
    clamp_coord,
    oblique_render,
    verify_clamp_no_sparkle,
)


class TextureTests(unittest.TestCase):
    def test_checker_pattern(self):
        checker = build_checker(16, tiles=4)
        self.assertEqual(len(checker), 16)
        self.assertEqual(checker[0][0], 1.0)
        self.assertEqual(checker[0][4], 0.0)
        self.assertEqual(checker[4][0], 0.0)

    def test_mip_chain_halves_and_converges(self):
        checker = build_checker(64, tiles=16)
        chain = build_mip_chain(checker)
        sizes = [len(level) for level in chain]
        self.assertEqual(sizes[0], 64)
        self.assertEqual(sizes[-1], 1)
        self.assertTrue(all(sizes[i] == sizes[i + 1] * 2 for i in range(len(sizes) - 1)))
        self.assertAlmostEqual(chain[-1][0][0], 0.5, places=6)

    def test_clamp_to_edge(self):
        self.assertEqual(clamp_coord(-10, 64), 0)
        self.assertEqual(clamp_coord(99, 64), 63)
        self.assertEqual(clamp_coord(7, 64), 7)

    def test_oblique_view_uses_clamp_and_passes_sparkle_check(self):
        chain = build_mip_chain(build_checker(512, tiles=64))
        render = oblique_render(chain, out_size=128)
        report = verify_clamp_no_sparkle(render)
        self.assertTrue(report["index_clamp_ok"])
        self.assertGreater(report["clamped_pixels"], 0)
        self.assertTrue(report["passed"], report)

    def test_lod_sweep_covers_multiple_mip_levels(self):
        chain = build_mip_chain(build_checker(256, tiles=32))
        render = oblique_render(chain, out_size=64)
        lods = [value for row in render["lod"] for value in row]
        self.assertAlmostEqual(min(lods), 0.0, places=6)
        self.assertGreater(max(lods), 2.5)


if __name__ == "__main__":
    unittest.main()
