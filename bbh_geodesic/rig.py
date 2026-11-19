"""Procedural running humanoid rig with rigidly skinned capsule samples."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator

from .geometry import (
    AABB,
    Transform,
    Vec3,
    add,
    cross,
    length,
    normalize,
    rotation_xyz,
    scale,
    sub,
)


@dataclass(frozen=True)
class Bone:
    name: str
    parent: str | None
    head: Vec3
    tail: Vec3
    radius: float

    @property
    def band(self) -> str:
        if ".L" in self.name:
            return "L"
        if ".R" in self.name:
            return "R"
        return "C"


BONES = (
    Bone("pelvis", None, (0.00, 1.00, 0.00), (0.00, 1.12, 0.00), 0.120),
    Bone("spine", "pelvis", (0.00, 1.12, 0.00), (0.00, 1.32, 0.00), 0.110),
    Bone("chest", "spine", (0.00, 1.32, 0.00), (0.00, 1.52, 0.00), 0.130),
    Bone("neck", "chest", (0.00, 1.52, 0.00), (0.00, 1.65, 0.00), 0.055),
    Bone("head", "neck", (0.00, 1.65, 0.00), (0.00, 1.86, 0.00), 0.095),
    Bone("clavicle.L", "chest", (0.02, 1.47, 0.00), (0.19, 1.49, 0.00), 0.060),
    Bone("upper_arm.L", "clavicle.L", (0.19, 1.49, 0.00), (0.45, 1.35, 0.00), 0.055),
    Bone("forearm.L", "upper_arm.L", (0.45, 1.35, 0.00), (0.68, 1.20, 0.00), 0.045),
    Bone("hand.L", "forearm.L", (0.68, 1.20, 0.00), (0.78, 1.13, 0.01), 0.040),
    Bone("clavicle.R", "chest", (-0.02, 1.47, 0.00), (-0.19, 1.49, 0.00), 0.060),
    Bone("upper_arm.R", "clavicle.R", (-0.19, 1.49, 0.00), (-0.45, 1.35, 0.00), 0.055),
    Bone("forearm.R", "upper_arm.R", (-0.45, 1.35, 0.00), (-0.68, 1.20, 0.00), 0.045),
    Bone("hand.R", "forearm.R", (-0.68, 1.20, 0.00), (-0.78, 1.13, 0.01), 0.040),
    Bone("thigh.L", "pelvis", (0.12, 1.00, 0.00), (0.15, 0.55, 0.00), 0.085),
    Bone("shin.L", "thigh.L", (0.15, 0.55, 0.00), (0.15, 0.14, 0.01), 0.065),
    Bone("foot.L", "shin.L", (0.15, 0.14, 0.01), (0.15, 0.06, 0.22), 0.055),
    Bone("thigh.R", "pelvis", (-0.12, 1.00, 0.00), (-0.15, 0.55, 0.00), 0.085),
    Bone("shin.R", "thigh.R", (-0.15, 0.55, 0.00), (-0.15, 0.14, 0.01), 0.065),
    Bone("foot.R", "shin.R", (-0.15, 0.14, 0.01), (-0.15, 0.06, 0.22), 0.055),
)

BONE_BY_NAME = {bone.name: bone for bone in BONES}


def _capsule_points(bone: Bone) -> tuple[Vec3, ...]:
    axis = sub(bone.tail, bone.head)
    axis_len = length(axis)
    direction = normalize(axis)
    reference = (0.0, 1.0, 0.0) if abs(direction[1]) < 0.92 else (0.0, 0.0, 1.0)
    u = normalize(cross(direction, reference))
    v = normalize(cross(direction, u))
    rings = (
        (0.00, 0.15),
        (0.05, 0.62),
        (0.20, 0.96),
        (0.40, 1.00),
        (0.60, 1.00),
        (0.80, 0.96),
        (0.95, 0.62),
        (1.00, 0.15),
    )
    points: list[Vec3] = []
    for t, radial in rings:
        center = add(bone.head, scale(axis, t))
        for k in range(12):
            theta = 2.0 * math.pi * k / 12.0
            offset = add(
                scale(u, math.cos(theta) * bone.radius * radial),
                scale(v, math.sin(theta) * bone.radius * radial),
            )
            points.append(add(center, offset))
    return tuple(points)


CAPSULE_POINTS = {bone.name: _capsule_points(bone) for bone in BONES}


def _depth(name: str) -> int:
    depth = 0
    bone = BONE_BY_NAME[name]
    while bone.parent is not None:
        depth += 1
        bone = BONE_BY_NAME[bone.parent]
    return depth


BONE_DEPTH = {bone.name: _depth(bone.name) for bone in BONES}


def children_map() -> dict[str | None, list[str]]:
    result: dict[str | None, list[str]] = {None: []}
    for bone in BONES:
        result.setdefault(bone.parent, []).append(bone.name)
        result.setdefault(bone.name, [])
    return result


@dataclass(frozen=True)
class PoseSample:
    phase: float
    transforms: dict[str, Transform]
    points: dict[str, tuple[Vec3, ...]]
    bounds: AABB


class RunRig:
    """A 19-bone humanoid with a 48-frame in-place run cycle."""

    def __init__(self, frame_count: int = 48) -> None:
        if frame_count < 8:
            raise ValueError("frame_count must be at least 8")
        self.frame_count = frame_count
        self.children = children_map()
        self.root_name = BONES[0].name

    def _local_angles(self, phase: float) -> dict[str, tuple[float, float, float]]:
        s = math.sin(2.0 * math.pi * phase)
        c = math.cos(2.0 * math.pi * phase)
        knee_l = 0.16 + 0.92 * max(0.0, math.sin(2.0 * math.pi * phase + 2.5))
        knee_r = 0.16 + 0.92 * max(0.0, math.sin(2.0 * math.pi * phase + 2.5 + math.pi))
        return {
            "pelvis": (0.035 + 0.025 * c, 0.06 * s, 0.025 * s),
            "spine": (0.075, -0.09 * s, -0.025 * s),
            "chest": (0.035, -0.11 * s, 0.018 * c),
            "neck": (-0.04, 0.08 * s, 0.0),
            "head": (-0.03, 0.10 * s, 0.0),
            "clavicle.L": (0.0, 0.0, -0.025 * c),
            "upper_arm.L": (0.66 * s, 0.0, 0.05),
            "forearm.L": (-0.72 - 0.16 * max(0.0, s), 0.0, 0.0),
            "hand.L": (0.1, 0.0, 0.0),
            "clavicle.R": (0.0, 0.0, 0.025 * c),
            "upper_arm.R": (-0.66 * s, 0.0, -0.05),
            "forearm.R": (-0.72 - 0.16 * max(0.0, -s), 0.0, 0.0),
            "hand.R": (0.1, 0.0, 0.0),
            "thigh.L": (-0.76 * s, 0.0, 0.02),
            "shin.L": (knee_l, 0.0, 0.0),
            "foot.L": (-0.32 + 0.22 * s, 0.0, 0.0),
            "thigh.R": (0.76 * s, 0.0, -0.02),
            "shin.R": (knee_r, 0.0, 0.0),
            "foot.R": (-0.32 - 0.22 * s, 0.0, 0.0),
        }

    def pose(self, phase: float) -> PoseSample:
        phase = phase % 1.0
        angles = self._local_angles(phase)
        transforms: dict[str, Transform] = {}
        points: dict[str, tuple[Vec3, ...]] = {}
        for bone in BONES:
            local = Transform(rotation_xyz(*angles[bone.name]))
            if bone.parent is None:
                bob = 0.045 * (0.5 - 0.5 * math.cos(4.0 * math.pi * phase))
                transforms[bone.name] = Transform(
                    local.rotation, (bone.head[0], bone.head[1] + bob, bone.head[2])
                )
            else:
                parent = BONE_BY_NAME[bone.parent]
                offset = sub(bone.head, parent.head)
                parent_world = transforms[bone.parent]
                world = parent_world.compose(Transform(local.rotation, offset))
                transforms[bone.name] = world
            origin = bone.head
            points[bone.name] = tuple(
                transforms[bone.name].apply(sub(point, origin))
                for point in CAPSULE_POINTS[bone.name]
            )
        all_points = [p for bone_points in points.values() for p in bone_points]
        return PoseSample(phase, transforms, points, AABB.from_points(all_points))

    def frames(self) -> Iterator[PoseSample]:
        for frame in range(self.frame_count):
            yield self.pose(frame / self.frame_count)

    def bone_length(self, name: str) -> float:
        bone = BONE_BY_NAME[name]
        return length(sub(bone.tail, bone.head))
