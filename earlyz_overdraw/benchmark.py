"""Run pipelines across draw orders and measure model + wall-clock cost."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .raster import PIPELINES, Metrics, run_pipeline
from .scenarios import ORDERS, Scene, order_quads


@dataclass(frozen=True)
class RunResult:
    scene_name: str
    pipeline: str
    draw_order: str
    metrics: Metrics


def timed_run(scene: Scene, pipeline: str, draw_order: str, *,
              repeats: int = 5) -> Metrics:
    """Run one configuration and attach best-of-N wall-clock timing."""

    quads = order_quads(scene, draw_order)
    first = run_pipeline(pipeline, scene.width, scene.height,
                         quads, draw_order)
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        metrics = run_pipeline(pipeline, scene.width, scene.height,
                               quads, draw_order)
        best = min(best, (time.perf_counter() - start) * 1000.0)
    metrics.elapsed_ms = best
    # Keep the deterministic counters from the final (identical) run.
    assert metrics.model_cycles == first.model_cycles
    return metrics


def run_matrix(scene: Scene, *, pipelines: tuple[str, ...] = PIPELINES,
               orders: tuple[str, ...] = ORDERS,
               repeats: int = 5) -> list[RunResult]:
    results: list[RunResult] = []
    for pipeline in pipelines:
        for order in orders:
            metrics = timed_run(scene, pipeline, order, repeats=repeats)
            results.append(RunResult(scene.name, pipeline, order, metrics))
    return results


def benefit_table(results: list[RunResult],
                  baseline_pipeline: str = "forward_no_early_z"
                  ) -> list[dict[str, float | str]]:
    """Overdraw / time reduction per configuration vs. the no-early-Z baseline.

    The baseline is matched on draw order so the comparison isolates the
    pipeline change. Rows come back sorted from largest deterministic
    model-cycle saving to the smallest; wall-clock data is kept alongside
    because Python timing carries scheduling noise.
    """

    baseline = {
        result.draw_order: result.metrics
        for result in results
        if result.pipeline == baseline_pipeline
    }
    rows: list[dict[str, float | str]] = []
    for result in results:
        if result.pipeline == baseline_pipeline:
            continue
        base = baseline[result.draw_order]
        current = result.metrics
        rows.append({
            "pipeline": result.pipeline,
            "draw_order": result.draw_order,
            "overdraw_pixels_drop_pct": _pct_drop(
                base.redundant_shaded, current.redundant_shaded),
            "shader_invocations_drop_pct": _pct_drop(
                base.shader_invocations, current.shader_invocations),
            "model_cycles_drop_pct": _pct_drop(
                base.model_cycles, current.model_cycles),
            "elapsed_drop_pct": _pct_drop(
                base.elapsed_ms, current.elapsed_ms),
            "baseline_elapsed_ms": base.elapsed_ms,
            "elapsed_ms": current.elapsed_ms,
        })
    rows.sort(key=lambda row: float(row["model_cycles_drop_pct"]),
               reverse=True)
    return rows


def _pct_drop(baseline: float, current: float) -> float:
    if baseline <= 0:
        return 0.0
    return (baseline - current) / baseline * 100.0
