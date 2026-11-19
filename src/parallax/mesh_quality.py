"""Element-uniformity metrics and OBJ export for triangle/quad meshes."""

from __future__ import annotations

from collections import Counter

import numpy as np


def face_edges(face):
    return [(face[i], face[(i + 1) % len(face)]) for i in range(len(face))]


def edge_lengths(points: np.ndarray, faces) -> np.ndarray:
    lengths = []
    for face in faces:
        for a, b in face_edges(face):
            lengths.append(np.linalg.norm(points[a] - points[b]))
    return np.asarray(lengths)


def face_angles(points: np.ndarray, face) -> list[float]:
    angles = []
    for i in range(len(face)):
        prev_p = points[face[i - 1]]
        cur = points[face[i]]
        nxt = points[face[(i + 1) % len(face)]]
        v1 = prev_p - cur
        v2 = nxt - cur
        cos_a = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-12)
        angles.append(np.degrees(np.arccos(np.clip(cos_a, -1.0, 1.0))))
    return angles


def quad_aspect_ratios(points: np.ndarray, quads) -> np.ndarray:
    ratios = []
    for face in quads:
        edges = [np.linalg.norm(points[b] - points[a]) for a, b in face_edges(face)]
        ratios.append(max(edges) / (min(edges) + 1e-12))
    return np.asarray(ratios)


def is_watertight(faces) -> bool:
    counter = Counter()
    for face in faces:
        for a, b in face_edges(face):
            counter[tuple(sorted((a, b)))] += 1
    return all(count == 2 for count in counter.values())


def uniformity_report(points: np.ndarray, faces) -> dict:
    lengths = edge_lengths(points, faces)
    angles = np.concatenate([face_angles(points, f) for f in faces])
    report = {
        "vertex_count": len(points),
        "face_count": len(faces),
        "vertices_per_face": len(faces[0]),
        "watertight": is_watertight(faces),
        "edge_mean": float(np.mean(lengths)),
        "edge_std": float(np.std(lengths)),
        "edge_cv": float(np.std(lengths) / np.mean(lengths)),
        "edge_min": float(np.min(lengths)),
        "edge_max": float(np.max(lengths)),
        "angle_mean": float(np.mean(angles)),
        "angle_std": float(np.std(angles)),
        "angle_max_deviation": float(np.max(np.abs(angles - np.mean(angles)))),
    }
    if len(faces[0]) == 4:
        ratios = quad_aspect_ratios(points, faces)
        report["aspect_mean"] = float(np.mean(ratios))
        report["aspect_max"] = float(np.max(ratios))
    return report


def write_obj(path: str, points: np.ndarray, faces) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for p in points:
            fh.write(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
        for face in faces:
            indices = " ".join(str(i + 1) for i in face)
            fh.write(f"f {indices}\n")
