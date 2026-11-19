import unittest

from anim_compress.animation import make_demo_animation
from anim_compress.compression import compress_animation
from anim_compress.metrics import evaluate_reconstruction


class CompressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.animation = make_demo_animation(duration_seconds=60.0, fps=60)

    def test_quantization_error_decreases_with_more_bits(self):
        errors = []
        ratios = []
        for bits in (8, 12, 16):
            result = compress_animation(self.animation, bits=bits, keyframe_hz=10.0)
            metrics = evaluate_reconstruction(
                self.animation, result, frame_stride=3
            )["metrics"]
            errors.append(metrics["quantization_rotation_max_deg"])
            ratios.append(metrics["compression_ratio"])
        self.assertGreater(errors[0], errors[1])
        self.assertGreater(errors[1], errors[2])
        self.assertGreater(ratios[0], ratios[1])
        self.assertGreater(ratios[1], ratios[2])

    def test_long_reconstruction_is_stable_and_accurate(self):
        result = compress_animation(self.animation, bits=16, keyframe_hz=10.0)
        metrics = evaluate_reconstruction(
            self.animation, result, frame_stride=2
        )["metrics"]
        self.assertLess(metrics["rotation_max_deg"], 0.1)
        self.assertLess(metrics["position_max"], 0.001)
        self.assertLess(metrics["end_effector_max"], 0.005)
        self.assertEqual(len(metrics["window_rotation_peaks_deg"]), 6)
        self.assertLess(
            metrics["last_window_rotation_peak_deg"],
            metrics["first_window_rotation_peak_deg"] * 1.5 + 1.0e-6,
        )

    def test_key_times_round_trip_to_quantized_keys(self):
        result = compress_animation(self.animation, bits=12, keyframe_hz=8.0)
        compressed = result.animation
        for time_seconds in compressed.key_times[::4]:
            direct = compressed.local_poses_at(time_seconds)
            interpolated = compressed.local_poses_at(time_seconds + 1.0e-10)
            for first, second in zip(direct, interpolated):
                self.assertAlmostEqual(first.position[0], second.position[0], places=9)
                self.assertAlmostEqual(first.rotation[3], second.rotation[3], places=9)

    def test_non_integer_duration_keeps_final_key_time(self):
        animation = make_demo_animation(duration_seconds=10.07, fps=60)
        result = compress_animation(animation, bits=12, keyframe_hz=10.0)
        self.assertAlmostEqual(result.animation.key_times[-1], 10.07, places=12)


if __name__ == "__main__":
    unittest.main()
