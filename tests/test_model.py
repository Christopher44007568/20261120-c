import unittest

from shader_permutations.model import (
    KEYWORDS,
    LIGHT_PATHS,
    SCENE_MATERIALS,
    generate_baseline_variants,
    generate_material_variants,
    resolve_dependencies,
    validate_variant,
)


class PermutationModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = generate_baseline_variants()
        cls.pruned = generate_material_variants()

    def test_baseline_is_full_cartesian_product(self) -> None:
        self.assertEqual(len(self.baseline), 2 ** len(KEYWORDS) * len(LIGHT_PATHS))
        self.assertEqual(len(self.baseline), 4096)

    def test_pruned_count_and_uniqueness(self) -> None:
        self.assertEqual(len(self.pruned), 68)
        self.assertEqual(
            len({variant.cache_key for variant in self.pruned}),
            len(self.pruned),
        )

    def test_pruned_variants_are_semantically_valid(self) -> None:
        for variant in self.pruned:
            with self.subTest(variant=variant.label):
                self.assertEqual(
                    validate_variant(variant.resolved_keywords, variant.path),
                    (),
                )

    def test_pruned_keywords_are_minimal(self) -> None:
        for variant in self.pruned:
            for keyword in variant.keywords:
                for other in variant.keywords - {keyword}:
                    with self.subTest(variant=variant.label, keyword=keyword):
                        self.assertNotIn(keyword, resolve_dependencies({other}))

    def test_invalid_accounting(self) -> None:
        invalid = [
            variant
            for variant in self.baseline
            if validate_variant(variant.resolved_keywords, variant.path)
        ]
        self.assertEqual(len(invalid), 3040)
        unique_valid = {
            variant.cache_key
            for variant in self.baseline
            if variant not in invalid
        }
        self.assertEqual(len(unique_valid), 430)
        self.assertTrue(
            {variant.cache_key for variant in self.pruned} <= unique_valid
        )

    def test_every_material_path_is_covered(self) -> None:
        for material in SCENE_MATERIALS:
            for path in material.paths:
                with self.subTest(material=material.name, path=path):
                    self.assertTrue(
                        any(
                            variant.path == path
                            and material.required <= variant.resolved_keywords
                            for variant in self.pruned
                        )
                    )


if __name__ == "__main__":
    unittest.main()
