import json
import tempfile
import unittest
from pathlib import Path

from shader_permutations.benchmark import BenchmarkConfig, run_benchmark
from shader_permutations.compiler import ShaderCompiler
from shader_permutations.model import generate_material_variants
from shader_permutations.report import all_validation_passed, write_artifacts


class CompilerAndBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_benchmark(
            BenchmarkConfig(cache_capacity=96, draws_per_variant=4, runs=1)
        )

    def test_all_pruned_variants_compile(self) -> None:
        compiler = ShaderCompiler()
        programs = [compiler.compile(variant) for variant in generate_material_variants()]
        self.assertEqual(len(programs), 68)
        self.assertTrue(all(program.instruction_count > 0 for program in programs))

    def test_first_frame_compilation_is_lower_after_pruning(self) -> None:
        before = self.result.baseline_first_frame
        after = self.result.pruned_first_frame
        self.assertLess(after.elapsed_ms, before.elapsed_ms)
        self.assertLess(after.prewarm_ms, before.prewarm_ms)
        self.assertGreater(after.hit_rate, before.hit_rate)
        self.assertEqual(after.misses, 0)
        self.assertEqual(after.hit_rate, 1.0)

    def test_required_validation_checks_pass(self) -> None:
        self.assertEqual(self.result.pruned_count, 68)
        self.assertEqual(self.result.invalid_overlap_with_pruned, 0)
        self.assertTrue(self.result.dependency_graph_acyclic)
        self.assertTrue(self.result.scene_variants_covered)
        self.assertTrue(all_validation_passed(self.result))

    def test_artifacts_are_written_and_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            paths = write_artifacts(self.result, output)
            for path in paths.values():
                self.assertTrue(path.is_file())
            report = json.loads(paths["report"].read_text(encoding="utf-8"))
            self.assertEqual(report["permutations"]["before"], 4096)
            self.assertEqual(report["permutations"]["after"], 68)
            self.assertTrue(report["validation"]["all_checks_pass"])
            self.assertTrue(report["dependency_graph"]["acyclic"])


if __name__ == "__main__":
    unittest.main()
