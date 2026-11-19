"""Error and directional-summary metrics used by the experiment."""

from __future__ import annotations

import numpy as np

from .model import normalize


def angular_error_deg(first: np.ndarray, second: np.ndarray) -> float:
    cosine = np.clip(float(normalize(first) @ normalize(second)), -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def weighted_centroid(directions: np.ndarray, values: np.ndarray) -> np.ndarray:
    weights = np.maximum(np.asarray(values, dtype=np.float64), 0.0)
    total = float(weights.sum())
    if total <= 1e-15:
        return directions[0].copy()
    return normalize((directions * weights[:, None]).sum(axis=0))


def scalar_metrics(prediction: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    difference = prediction - reference
    denominator = float(np.sqrt(np.mean(reference**2)))
    relative_l1 = float(np.sum(np.abs(difference)) / max(np.sum(reference), 1e-15))
    return {
        "relative_l1": relative_l1,
        "nrmse": float(np.sqrt(np.mean(difference**2)) / max(denominator, 1e-15)),
        "relative_bias": float(
            np.sum(difference) / max(np.sum(reference), 1e-15)
        ),
        "max_relative_error": float(
            np.max(np.abs(difference) / np.maximum(reference, 1e-12))
        ),
        "overshoot_25_fraction": float(
            np.mean(difference > 0.25 * np.maximum(reference, 1e-12))
        ),
    }


def environment_metrics(
    prediction: np.ndarray,
    reference: np.ndarray,
    directions: np.ndarray,
) -> dict[str, float]:
    metrics = scalar_metrics(prediction, reference)
    peak_prediction = directions[int(np.argmax(prediction))]
    peak_reference = directions[int(np.argmax(reference))]
    centroid_prediction = weighted_centroid(directions, prediction)
    centroid_reference = weighted_centroid(directions, reference)
    metrics.update(
        {
            "peak_ratio": float(np.max(prediction) / max(np.max(reference), 1e-15)),
            "peak_direction_error_deg": angular_error_deg(
                peak_prediction, peak_reference
            ),
            "centroid_direction_error_deg": angular_error_deg(
                centroid_prediction, centroid_reference
            ),
            "flux_ratio": float(np.mean(prediction) / max(np.mean(reference), 1e-15)),
            "negative_fraction": float(np.mean(prediction < -1e-12)),
            "minimum_value": float(np.min(prediction)),
        }
    )
    return metrics


def brightness_metrics(
    prediction: np.ndarray,
    reference: np.ndarray,
    standard_error: np.ndarray,
    normals: np.ndarray,
) -> dict[str, float]:
    metrics = scalar_metrics(prediction, reference)
    metrics.update(
        {
            "peak_direction_error_deg": angular_error_deg(
                normals[int(np.argmax(prediction))],
                normals[int(np.argmax(reference))],
            ),
            "centroid_direction_error_deg": angular_error_deg(
                weighted_centroid(normals, prediction),
                weighted_centroid(normals, reference),
            ),
            "median_mc_relative_se": float(
                np.median(standard_error / np.maximum(reference, 1e-15))
            ),
        }
    )
    return metrics
