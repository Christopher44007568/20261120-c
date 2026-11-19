"""Deterministic visibility-buffer vs deferred-rendering budget model."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class FrameConfig:
    width: int = 1920
    height: int = 1080
    samples: int = 1
    coverage: float = 0.65
    gbuffer_bytes: int = 20
    visibility_bytes: int = 8
    depth_bytes: int = 4
    hdr_bytes: int = 8
    material_cache_penalty: int = 0

    @property
    def pixels(self) -> int:
        return self.width * self.height


def estimate_frame(config: FrameConfig) -> dict[str, float | int]:
    """Estimate framebuffer footprint and per-frame external-memory traffic.

    Common depth-test traffic, vertex fetch, textures, and render-target
    compression are deliberately excluded from both paths. The visibility
    resolve loads the packed material payload from scene buffers; the deferred
    path loads the equivalent G-buffer channels after an implicit MSAA resolve.
    """
    pixels = config.pixels
    samples = config.samples
    coverage = config.coverage
    gbuffer = config.gbuffer_bytes
    visibility = config.visibility_bytes
    depth = config.depth_bytes
    hdr = config.hdr_bytes

    deferred_memory = pixels * samples * (gbuffer + depth) + pixels * hdr
    visibility_memory = pixels * samples * (visibility + depth) + pixels * hdr

    deferred_traffic = (
        pixels * samples * coverage * (gbuffer + depth)
        + pixels * coverage * (gbuffer + depth)
        + pixels * coverage * hdr
    )
    visibility_traffic = (
        pixels * samples * coverage * (visibility + depth)
        + pixels * coverage * (visibility + depth)
        + pixels * coverage * (gbuffer + config.material_cache_penalty)
        + pixels * coverage * hdr
    )

    return {
        "width": config.width,
        "height": config.height,
        "pixels": pixels,
        "samples": samples,
        "coverage": coverage,
        "deferred_memory_bytes": deferred_memory,
        "visibility_memory_bytes": visibility_memory,
        "memory_saving_bytes": deferred_memory - visibility_memory,
        "memory_saving_percent": 100.0 * (deferred_memory - visibility_memory) / deferred_memory,
        "deferred_traffic_bytes": deferred_traffic,
        "visibility_traffic_bytes": visibility_traffic,
        "traffic_saving_bytes": deferred_traffic - visibility_traffic,
        "traffic_saving_percent": 100.0 * (deferred_traffic - visibility_traffic) / deferred_traffic,
        "deferred_bytes_per_pixel": (gbuffer + depth) * samples + hdr,
        "visibility_bytes_per_pixel": (visibility + depth) * samples + hdr,
        "deferred_traffic_per_covered_pixel": (
            samples * (gbuffer + depth) + (gbuffer + depth) + hdr
        ),
        "visibility_traffic_per_covered_pixel": (
            samples * (visibility + depth)
            + (visibility + depth)
            + gbuffer
            + config.material_cache_penalty
            + hdr
        ),
    }


def build_suite() -> dict[str, object]:
    resolutions = [(1920, 1080), (2560, 1440), (3840, 2160)]
    results: list[dict[str, float | int]] = []
    for width, height in resolutions:
        for samples in (1, 2, 4):
            config = FrameConfig(width=width, height=height, samples=samples)
            row = estimate_frame(config)
            row["msaa"] = samples
            results.append(row)

    sensitivity: list[dict[str, float | int]] = []
    for samples in (1, 2, 4):
        for gbuffer in (16, 20, 24):
            for penalty in (0, 4, 8, 16):
                config = FrameConfig(
                    samples=samples,
                    gbuffer_bytes=gbuffer,
                    material_cache_penalty=penalty,
                )
                row = estimate_frame(config)
                sensitivity.append(
                    {
                        "msaa": samples,
                        "gbuffer_bytes": gbuffer,
                        "cache_penalty_bytes": penalty,
                        "memory_saving_percent": row["memory_saving_percent"],
                        "traffic_saving_percent": row["traffic_saving_percent"],
                    }
                )
    return {"frames": results, "sensitivity": sensitivity}


def repeatability_check(runs: int = 5) -> dict[str, object]:
    payload = build_suite()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    hashes = []
    for _ in range(runs):
        current = json.dumps(build_suite(), sort_keys=True, separators=(",", ":"))
        hashes.append(hashlib.sha256(current.encode("utf-8")).hexdigest())
    return {
        "runs": runs,
        "unique_hashes": len(set(hashes)),
        "results_hash": digest,
        "bit_identical": len(set(hashes)) == 1,
    }


def conditional_conclusion(suite: dict[str, object]) -> dict[str, object]:
    frames = suite["frames"]
    sensitivity = suite["sensitivity"]
    full_hd = next(
        row for row in frames if row["width"] == 1920 and row["height"] == 1080 and row["msaa"] == 1
    )
    full_hd_4x = next(
        row for row in frames if row["width"] == 1920 and row["height"] == 1080 and row["msaa"] == 4
    )
    losing = [
        row
        for row in sensitivity
        if row["msaa"] == 1 and row["traffic_saving_percent"] < 0.0
    ]
    return {
        "memory_always_lower": all(row["memory_saving_bytes"] > 0 for row in frames),
        "msaa1_traffic_saving_percent": full_hd["traffic_saving_percent"],
        "msaa4_traffic_saving_percent": full_hd_4x["traffic_saving_percent"],
        "msaa1_deferred_traffic_per_pixel": full_hd["deferred_traffic_per_covered_pixel"],
        "msaa1_visibility_traffic_per_pixel": full_hd["visibility_traffic_per_covered_pixel"],
        "vis_bandwidth_loses_without_msaa_when": losing,
    }
