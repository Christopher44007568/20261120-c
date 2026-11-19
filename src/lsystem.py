"""L-system tree: rule expansion and 3D turtle interpretation."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LSystemConfig:
    axiom: str
    rules: dict[str, str]
    depth: int
    angle_deg: float
    step: float = 1.0
    width: float = 1.0
    seed: int = 1


def expand(cfg: LSystemConfig) -> str:
    sentence = cfg.axiom
    for _ in range(cfg.depth):
        sentence = "".join(cfg.rules.get(ch, ch) for ch in sentence)
    return sentence


def _rotate(v: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    c, s = np.cos(angle), np.sin(angle)
    return v * c + np.cross(axis, v) * s + axis * np.dot(axis, v) * (1 - c)


def interpret(cfg: LSystemConfig, sentence: str) -> dict:
    """Return branch segments (start, end, width) and leaf points."""
    rng = np.random.default_rng(cfg.seed)
    angle = np.radians(cfg.angle_deg)
    pos = np.zeros(3)
    heading = np.array([0.0, 0.0, 1.0])
    left = np.array([1.0, 0.0, 0.0])
    up = np.array([0.0, 1.0, 0.0])
    stack: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]] = []
    segments: list[tuple[np.ndarray, np.ndarray, float]] = []
    leaves: list[np.ndarray] = []
    width = cfg.width

    for ch in sentence:
        if ch in "FAB":
            jitter = 1.0 + rng.normal(0, 0.06)
            end = pos + heading * cfg.step * jitter
            segments.append((pos.copy(), end.copy(), max(width, 0.05)))
            pos = end
        elif ch == "+":
            heading = _rotate(heading, up, angle * (1 + rng.normal(0, 0.08)))
        elif ch == "-":
            heading = _rotate(heading, up, -angle * (1 + rng.normal(0, 0.08)))
        elif ch == "&":
            heading = _rotate(heading, left, angle * (1 + rng.normal(0, 0.08)))
        elif ch == "^":
            heading = _rotate(heading, left, -angle * (1 + rng.normal(0, 0.08)))
        elif ch == "[":
            stack.append((pos.copy(), heading.copy(), left.copy(), up.copy(), width))
            width *= 0.72
        elif ch == "]":
            leaves.append(pos.copy())
            pos, heading, left, up, width = stack.pop()
    return {
        "segments": segments,
        "leaves": np.array(leaves) if leaves else np.zeros((0, 3)),
        "sentence_len": len(sentence),
    }


def build_tree(cfg: LSystemConfig) -> dict:
    sentence = expand(cfg)
    result = interpret(cfg, sentence)
    result["depth"] = cfg.depth
    result["config"] = cfg
    return result
