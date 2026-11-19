"""Experiment matrix and acceptance-ready boundary case parameters."""

from __future__ import annotations

from dataclasses import dataclass

from .scenarios import Scene, make_scene


@dataclass(frozen=True)
class ExperimentSpec:
    case_id: str
    description: str
    seed: int
    width: int
    height: int
    count: int
    overlap: str
    transparent_fraction: float
    alpha_test_fraction: float = 0.0

    def build(self) -> Scene:
        return make_scene(
            self.case_id,
            seed=self.seed,
            width=self.width,
            height=self.height,
            count=self.count,
            overlap=self.overlap,
            transparent_fraction=self.transparent_fraction,
            alpha_test_fraction=self.alpha_test_fraction,
        )


# Each row is a fully specified, seed-reproducible input. The last three rows
# probe the early-Z transparency boundary: blending fragments cannot write
# depth, so overdraw between transparent objects cannot be eliminated.
EXPERIMENTS: tuple[ExperimentSpec, ...] = (
    ExperimentSpec("E1_heavy_opaque",
                   "大量重叠、全不透明：先深度后着色的主战场",
                   101, 256, 256, 24, "heavy", 0.0),
    ExperimentSpec("E2_sparse_opaque",
                   "稀疏重叠、全不透明：低 overdraw 对照组",
                   202, 256, 256, 24, "sparse", 0.0),
    ExperimentSpec("E3_heavy_25pct_transparent",
                   "大量重叠、25% 透明：部分边界，仍有净收益",
                   303, 256, 256, 24, "heavy", 0.25),
    ExperimentSpec("E4_heavy_50pct_transparent",
                   "大量重叠、50% 透明：收益与预通道成本接近打平",
                   404, 256, 256, 24, "heavy", 0.5),
    ExperimentSpec("E5_heavy_75pct_transparent",
                   "大量重叠、75% 透明：收益被透明 overdraw 侵蚀",
                   505, 256, 256, 24, "heavy", 0.75),
    ExperimentSpec("E6_heavy_100pct_transparent",
                   "全透明：早 Z 完全失效，Z-Prepass 退化为纯开销",
                   606, 256, 256, 24, "heavy", 1.0),
    ExperimentSpec("E7_heavy_100pct_alpha_test",
                   "全 alpha-test（写深度的透明裁剪）：边界反例，收益恢复",
                   707, 256, 256, 24, "heavy", 0.0, 1.0),
)


def boundary_parameter_rows() -> list[dict[str, float | int | str]]:
    """Flat input parameter table for acceptance reproducibility."""

    rows: list[dict[str, float | int | str]] = []
    for spec in EXPERIMENTS:
        rows.append({
            "case_id": spec.case_id,
            "seed": spec.seed,
            "width": spec.width,
            "height": spec.height,
            "quad_count": spec.count,
            "overlap": spec.overlap,
            "transparent_fraction": spec.transparent_fraction,
            "alpha_test_fraction": spec.alpha_test_fraction,
            "description": spec.description,
        })
    return rows
