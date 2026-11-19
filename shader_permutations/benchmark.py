"""Permutation pruning benchmark and first-frame latency accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median
from time import perf_counter_ns

from .cache import LruCache
from .compiler import CompiledProgram, ShaderCompiler
from .dependency import DependencyGraph
from .model import (
    SCENE_MATERIALS,
    Variant,
    generate_baseline_variants,
    generate_material_variants,
    validate_variant,
)


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    cache_capacity: int = 96
    draws_per_variant: int = 4
    runs: int = 3


@dataclass(frozen=True, slots=True)
class CompileStats:
    elapsed_ms: float
    compile_count: int
    unique_cache_keys: int
    instruction_count: int

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FirstFrameStats:
    elapsed_ms: float
    prewarm_ms: float
    request_miss_compile_ms: float
    requests: int
    hits: int
    misses: int
    hit_rate: float
    cache_entries: int

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    config: BenchmarkConfig
    baseline_count: int
    pruned_count: int
    semantically_valid_raw: int
    invalid_removed: int
    unused_valid_removed: int
    duplicate_variants_merged: int
    baseline_compile: CompileStats
    pruned_compile: CompileStats
    baseline_first_frame: FirstFrameStats
    pruned_first_frame: FirstFrameStats
    dependency_graph_acyclic: bool
    invalid_overlap_with_pruned: int
    scene_variants_covered: bool
    invalid_reason_counts: dict[str, int]
    invalid_samples: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        baseline_ms = self.baseline_compile.elapsed_ms
        pruned_ms = self.pruned_compile.elapsed_ms
        baseline_frame_ms = self.baseline_first_frame.elapsed_ms
        pruned_frame_ms = self.pruned_first_frame.elapsed_ms
        valid_unique = (
            self.semantically_valid_raw - self.duplicate_variants_merged
        )
        return {
            "config": asdict(self.config),
            "permutations": {
                "before": self.baseline_count,
                "after": self.pruned_count,
                "semantically_valid_raw": self.semantically_valid_raw,
                "invalid_removed": self.invalid_removed,
                "unused_valid_removed": self.unused_valid_removed,
                "duplicate_variants_merged": self.duplicate_variants_merged,
                "reduction_percent": _reduction(
                    self.baseline_count, self.pruned_count
                ),
            },
            "compile": {
                "before": self.baseline_compile.to_dict(),
                "after": self.pruned_compile.to_dict(),
                "latency_reduction_percent": _reduction(baseline_ms, pruned_ms),
                "speedup": baseline_ms / pruned_ms,
            },
            "first_frame": {
                "before": self.baseline_first_frame.to_dict(),
                "after": self.pruned_first_frame.to_dict(),
                "latency_reduction_percent": _reduction(
                    baseline_frame_ms, pruned_frame_ms
                ),
                "speedup": baseline_frame_ms / pruned_frame_ms,
            },
            "validation": {
                "invalid_removed": self.invalid_removed > 0
                and self.invalid_overlap_with_pruned == 0,
                "invalid_overlap_with_pruned": self.invalid_overlap_with_pruned,
                "permutation_accounting_balanced": (
                    self.invalid_removed + self.semantically_valid_raw
                    == self.baseline_count
                    and self.duplicate_variants_merged
                    + self.unused_valid_removed
                    + self.pruned_count
                    == self.semantically_valid_raw
                    and self.pruned_count <= valid_unique
                ),
                "scene_variants_covered": self.scene_variants_covered,
                "first_frame_improved": pruned_frame_ms < baseline_frame_ms,
                "dependency_graph_acyclic": self.dependency_graph_acyclic,
                "cache_hit_rate_improved": (
                    self.pruned_first_frame.hit_rate
                    > self.baseline_first_frame.hit_rate
                ),
            },
            "invalid_removal": {
                "reason_counts": self.invalid_reason_counts,
                "samples": list(self.invalid_samples),
            },
        }


def _reduction(before: float, after: float) -> float:
    if before <= 0:
        return 0.0
    return (1.0 - after / before) * 100.0


def _scene_variants() -> tuple[Variant, ...]:
    return generate_material_variants(SCENE_MATERIALS)


def _scene_coverage(
    scene: tuple[Variant, ...], requests: tuple[Variant, ...]
) -> bool:
    material_paths_covered = all(
        any(
            variant.path == path
            and material.required <= variant.resolved_keywords
            for variant in scene
        )
        for material in SCENE_MATERIALS
        for path in material.paths
    )
    request_coverage = {variant.cache_key for variant in scene} == {
        variant.cache_key for variant in requests
    }
    no_invalid = all(
        not validate_variant(variant.resolved_keywords, variant.path)
        for variant in scene
    )
    return material_paths_covered and request_coverage and no_invalid


def _measure_compile(
    variants: tuple[Variant, ...], compiler: ShaderCompiler, runs: int
) -> CompileStats:
    if runs < 1:
        raise ValueError("runs must be at least 1")
    samples: list[float] = []
    instruction_count = 0
    for run in range(runs):
        instruction_count = 0
        started = perf_counter_ns()
        for variant in variants:
            program: CompiledProgram = compiler.compile(variant)
            instruction_count += program.instruction_count
        samples.append((perf_counter_ns() - started) / 1_000_000.0)
    return CompileStats(
        elapsed_ms=median(samples),
        compile_count=len(variants),
        unique_cache_keys=len({_cache_key(variant, False) for variant in variants}),
        instruction_count=instruction_count // runs,
    )


def _cache_key(
    variant: Variant, canonical: bool
) -> tuple[str, tuple[str, ...]]:
    return variant.cache_key if canonical else variant.resolved_cache_key


def _run_first_frame(
    prewarm: tuple[Variant, ...],
    requests: tuple[Variant, ...],
    compiler: ShaderCompiler,
    capacity: int,
    canonical_keys: bool,
) -> FirstFrameStats:
    cache: LruCache[tuple[str, tuple[str, ...]], CompiledProgram] = LruCache(capacity)

    started = perf_counter_ns()
    for variant in prewarm:
        cache.put(_cache_key(variant, canonical_keys), compiler.compile(variant))
    prewarm_ns = perf_counter_ns() - started

    miss_compile_ns = 0
    for variant in requests:
        key = _cache_key(variant, canonical_keys)
        if cache.get(key) is not None:
            continue
        miss_started = perf_counter_ns()
        program = compiler.compile(variant)
        miss_compile_ns += perf_counter_ns() - miss_started
        cache.put(key, program)

    elapsed_ns = prewarm_ns + miss_compile_ns
    return FirstFrameStats(
        elapsed_ms=elapsed_ns / 1_000_000.0,
        prewarm_ms=prewarm_ns / 1_000_000.0,
        request_miss_compile_ms=miss_compile_ns / 1_000_000.0,
        requests=cache.hits + cache.misses,
        hits=cache.hits,
        misses=cache.misses,
        hit_rate=cache.hit_rate,
        cache_entries=len(cache),
    )


def _request_sequence(scene: tuple[Variant, ...], draws: int) -> tuple[Variant, ...]:
    if draws < 1:
        raise ValueError("draws_per_variant must be at least 1")
    return tuple(variant for _ in range(draws) for variant in scene)


def _invalid_audit(
    baseline: tuple[Variant, ...],
) -> tuple[dict[str, int], tuple[dict[str, object], ...]]:
    reasons: dict[str, int] = {}
    samples: list[dict[str, object]] = []
    for variant in baseline:
        violations = validate_variant(variant.resolved_keywords, variant.path)
        if not violations:
            continue
        for violation in violations:
            reasons[violation] = reasons.get(violation, 0) + 1
        if len(samples) < 40:
            samples.append(
                {
                    "path": variant.path,
                    "keywords": sorted(variant.keywords),
                    "resolved_keywords": sorted(variant.resolved_keywords),
                    "reasons": list(violations),
                }
            )
    return dict(sorted(reasons.items())), tuple(samples)


def run_benchmark(config: BenchmarkConfig | None = None) -> BenchmarkResult:
    config = config or BenchmarkConfig()
    compiler = ShaderCompiler()
    baseline = generate_baseline_variants()
    scene = _scene_variants()
    requests = _request_sequence(scene, config.draws_per_variant)

    invalid_reasons, invalid_samples = _invalid_audit(baseline)
    invalid_count = sum(
        bool(validate_variant(variant.resolved_keywords, variant.path))
        for variant in baseline
    )
    semantically_valid_raw = len(baseline) - invalid_count
    valid_baseline = tuple(
        variant
        for variant in baseline
        if not validate_variant(variant.resolved_keywords, variant.path)
    )
    unique_valid_keys = {variant.cache_key for variant in valid_baseline}
    duplicate_variants_merged = len(valid_baseline) - len(unique_valid_keys)
    invalid_overlap = sum(
        bool(validate_variant(variant.resolved_keywords, variant.path))
        for variant in scene
    )

    graph = DependencyGraph.keyword_graph()
    cycle = graph.cycle()
    if not cycle:
        graph.topological_order()

    baseline_compile = _measure_compile(baseline, compiler, config.runs)
    pruned_compile = _measure_compile(scene, compiler, config.runs)

    baseline_frames = [
        _run_first_frame(
            baseline,
            requests,
            compiler,
            config.cache_capacity,
            canonical_keys=False,
        )
        for _ in range(config.runs)
    ]
    pruned_frames = [
        _run_first_frame(
            scene,
            requests,
            compiler,
            config.cache_capacity,
            canonical_keys=True,
        )
        for _ in range(config.runs)
    ]
    baseline_frame = _median_frame(baseline_frames)
    pruned_frame = _median_frame(pruned_frames)

    return BenchmarkResult(
        config=config,
        baseline_count=len(baseline),
        pruned_count=len(scene),
        semantically_valid_raw=semantically_valid_raw,
        invalid_removed=invalid_count,
        unused_valid_removed=len(unique_valid_keys) - len(scene),
        duplicate_variants_merged=duplicate_variants_merged,
        baseline_compile=baseline_compile,
        pruned_compile=pruned_compile,
        baseline_first_frame=baseline_frame,
        pruned_first_frame=pruned_frame,
        dependency_graph_acyclic=not cycle,
        invalid_overlap_with_pruned=invalid_overlap,
        scene_variants_covered=_scene_coverage(scene, requests),
        invalid_reason_counts=invalid_reasons,
        invalid_samples=invalid_samples,
    )


def _median_frame(samples: list[FirstFrameStats]) -> FirstFrameStats:
    representative = samples[len(samples) // 2]
    return FirstFrameStats(
        elapsed_ms=median(sample.elapsed_ms for sample in samples),
        prewarm_ms=median(sample.prewarm_ms for sample in samples),
        request_miss_compile_ms=median(
            sample.request_miss_compile_ms for sample in samples
        ),
        requests=representative.requests,
        hits=representative.hits,
        misses=representative.misses,
        hit_rate=representative.hit_rate,
        cache_entries=representative.cache_entries,
    )
