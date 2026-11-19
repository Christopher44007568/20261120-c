import math
import unittest

from layout.fft import fft
from layout.geometry import Board, Obstacle, Pin
from layout.noise import (HIGH_FREQ_SLOPES, generate_noises,
                          high_frequency_artifacts, spectral_slope,
                          welch_psd)
from layout.router import Router
from layout.scenario import build_demo_board


class GeometryTests(unittest.TestCase):
    def test_pin_inside_obstacle_rejected(self):
        board = Board(6, 6, 1, [Obstacle(0, 1, 1, 3, 3)])
        with self.assertRaises(ValueError):
            board.check_pins([Pin("a", 0, 2, 2), Pin("a", 0, 5, 5)])

    def test_neighbors_are_orthogonal(self):
        board = Board(5, 5, 1, [Obstacle(0, 2, 0, 3, 5)])
        neigh = list(board.neighbors(0, (1, 2)))
        self.assertEqual(sorted(c for _, c in neigh),
                         [(0, 2), (1, 1), (1, 3)])


class RoutingTests(unittest.TestCase):
    def test_demo_board_routes_without_crossings(self):
        board, pins = build_demo_board()
        result = Router(board, pins, rip_up_passes=3).route()
        self.assertTrue(result.routed)
        self.assertEqual(result.crossings, 0)
        self.assertEqual(result.via_errors, [])

    def test_paths_are_orthogonal_and_endpoint_connected(self):
        board, pins = build_demo_board()
        result = Router(board, pins).route()
        endpoints = {(p.net, (p.layer, p.cell)) for p in pins}
        for net, path in result.nets.items():
            self.assertIn((net, path[0]), endpoints)
            self.assertIn((net, path[-1]), endpoints)
            for (la, ca), (lb, cb) in zip(path, path[1:]):
                same_layer_move = la == lb and (
                    abs(ca[0] - cb[0]) + abs(ca[1] - cb[1]) == 1)
                via_move = ca == cb and abs(la - lb) == 1
                self.assertTrue(same_layer_move or via_move)
                self.assertFalse(board.blocked(la, ca))
                self.assertFalse(board.blocked(lb, cb))

    def test_via_bookkeeping_matches_path_transitions(self):
        board, pins = build_demo_board()
        result = Router(board, pins).route()
        transitions = 0
        for path in result.nets.values():
            transitions += sum(1 for a, b in zip(path, path[1:])
                               if a[0] != b[0])
        self.assertEqual(transitions, result.via_count)
        for _, cell, lo, hi in result.vias:
            self.assertEqual(hi - lo, 1)
            for layer in (lo, hi):
                self.assertFalse(board.blocked(layer, cell))


class NoiseTests(unittest.TestCase):
    def test_fft_matches_direct_dft(self):
        signal = [0.9, 0.2, -0.4, 0.7]
        n = len(signal)
        direct = [
            sum(v * math.e ** (-2j * math.pi * k * j / n)
                for j, v in enumerate(signal))
            for k in range(n)]
        self.assertTrue(all(abs(a - b) < 1e-12
                            for a, b in zip(direct, fft(signal))))

    def test_spectral_slopes_match_theory_in_low_band(self):
        noises = generate_noises(n=4096)
        for name, samples in noises.items():
            freqs, psd = welch_psd(samples)
            slope = spectral_slope(freqs, psd, 0.02, 0.12)
            self.assertAlmostEqual(slope, HIGH_FREQ_SLOPES[name], delta=0.12)

    def test_no_high_frequency_artifacts_for_three_noises(self):
        for samples in generate_noises(n=4096).values():
            freqs, psd = welch_psd(samples)
            self.assertFalse(
                high_frequency_artifacts(freqs, psd)["artifact_detected"])

    def test_artifact_detector_flags_injected_nyquist_energy(self):
        noises = generate_noises(n=4096)
        samples = noises["pink"]
        contaminated = [
            v + 1.5 * math.sin(2 * math.pi * 0.42 * n)
            for n, v in enumerate(samples)]
        freqs, psd = welch_psd(contaminated)
        self.assertTrue(
            high_frequency_artifacts(freqs, psd)["artifact_detected"])


if __name__ == "__main__":
    unittest.main()
