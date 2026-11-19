"""Shader permutation pruning and first-frame compile benchmark."""

from .benchmark import BenchmarkConfig, run_benchmark
from .model import (
    LIGHT_PATHS,
    SCENE_MATERIALS,
    generate_baseline_variants,
    generate_material_variants,
)

__all__ = [
    "BenchmarkConfig",
    "LIGHT_PATHS",
    "SCENE_MATERIALS",
    "generate_baseline_variants",
    "generate_material_variants",
    "run_benchmark",
]
