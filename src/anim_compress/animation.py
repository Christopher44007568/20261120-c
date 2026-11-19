from __future__ import annotations

from dataclasses import dataclass
from math import floor, pi, sin

from .math3d import (
    IDENTITY_QUAT,
    Quat,
    Vec3,
    quat_from_euler_xyz,
    quat_mul,
    quat_rotate,
    vec_add,
    vec_scale,
)


@dataclass(frozen=True)
class JointPose:
    position: Vec3
    rotation: Quat


@dataclass(frozen=True)
class Joint:
    name: str
    parent: str | None
    rest_position: Vec3
    rotation_amplitude: Vec3 = (0.0, 0.0, 0.0)
    rotation_frequency: Vec3 = (0.0, 0.0, 0.0)
    rotation_phase: Vec3 = (0.0, 0.0, 0.0)
    translation_amplitude: Vec3 = (0.0, 0.0, 0.0)
    translation_frequency: Vec3 = (0.0, 0.0, 0.0)
    translation_phase: Vec3 = (0.0, 0.0, 0.0)

    def local_pose(self, time_seconds: float) -> JointPose:
        angles = []
        for axis in range(3):
            phase = _wave(time_seconds, self.rotation_frequency[axis], self.rotation_phase[axis])
            accent_phase = _wave(
                time_seconds,
                self.rotation_frequency[axis] * 2.35 + 0.07,
                self.rotation_phase[axis] * 1.7,
            )
            angles.append(self.rotation_amplitude[axis] * (phase + 0.12 * accent_phase))
        offset = []
        for axis in range(3):
            wave = _wave(
                time_seconds,
                self.translation_frequency[axis],
                self.translation_phase[axis],
            )
            offset.append(self.translation_amplitude[axis] * wave)
        position = vec_add(self.rest_position, (offset[0], offset[1], offset[2]))
        rotation = quat_from_euler_xyz(angles[0], angles[1], angles[2])
        return JointPose(position=position, rotation=rotation)


def _wave(time_seconds: float, frequency: float, phase: float) -> float:
    if frequency == 0.0:
        return sin(phase)
    return sin(2.0 * pi * frequency * time_seconds + phase)


class ProceduralAnimation:
    def __init__(self, joints: list[Joint], duration_seconds: float, fps: int) -> None:
        self.joints = list(joints)
        self.duration_seconds = float(duration_seconds)
        self.fps = int(fps)
        self._joint_index = {joint.name: index for index, joint in enumerate(self.joints)}
        if len(self._joint_index) != len(self.joints):
            raise ValueError("joint names must be unique")
        for joint in self.joints:
            if joint.parent is not None and joint.parent not in self._joint_index:
                raise ValueError(f"unknown parent {joint.parent!r} for joint {joint.name!r}")

    @property
    def frame_count(self) -> int:
        return int(floor(self.duration_seconds * self.fps)) + 1

    def time_at_frame(self, frame: int) -> float:
        return frame / self.fps

    def local_poses_at(self, time_seconds: float) -> list[JointPose]:
        return [joint.local_pose(time_seconds) for joint in self.joints]

    def world_poses_at(self, time_seconds: float) -> list[JointPose]:
        local = self.local_poses_at(time_seconds)
        world: list[JointPose] = []
        for index, joint in enumerate(self.joints):
            pose = local[index]
            if joint.parent is None:
                world.append(pose)
                continue
            parent = world[self._joint_index[joint.parent]]
            rotation = quat_mul(parent.rotation, pose.rotation)
            rotated_offset = quat_rotate(parent.rotation, pose.position)
            world.append(
                JointPose(
                    position=vec_add(parent.position, rotated_offset),
                    rotation=rotation,
                )
            )
        return world

    def rest_world_positions(self) -> dict[str, Vec3]:
        poses = self.world_poses_at(0.0)
        return {
            joint.name: pose.position
            for joint, pose in zip(self.joints, poses)
        }


def make_demo_animation(duration_seconds: float = 600.0, fps: int = 60) -> ProceduralAnimation:
    joints = [
        Joint(
            "root",
            None,
            (0.0, 0.0, 0.0),
            rotation_amplitude=(0.20, 0.38, 0.16),
            rotation_frequency=(0.071, 0.043, 0.059),
            rotation_phase=(0.1, 1.7, 2.4),
            translation_amplitude=(0.25, 0.04, 0.18),
            translation_frequency=(0.031, 0.067, 0.023),
            translation_phase=(0.4, 1.1, 2.2),
        ),
        Joint(
            "pelvis",
            "root",
            (0.0, 0.95, 0.0),
            rotation_amplitude=(0.10, 0.22, 0.18),
            rotation_frequency=(0.083, 0.052, 0.067),
            rotation_phase=(0.8, 0.2, 1.3),
        ),
        Joint(
            "spine",
            "pelvis",
            (0.0, 0.48, 0.0),
            rotation_amplitude=(0.18, 0.31, 0.12),
            rotation_frequency=(0.067, 0.047, 0.073),
            rotation_phase=(1.2, 2.0, 0.4),
        ),
        Joint(
            "chest",
            "spine",
            (0.0, 0.42, 0.0),
            rotation_amplitude=(0.12, 0.26, 0.16),
            rotation_frequency=(0.059, 0.039, 0.077),
            rotation_phase=(2.1, 0.9, 1.6),
        ),
        Joint(
            "head",
            "chest",
            (0.0, 0.32, 0.02),
            rotation_amplitude=(0.16, 0.28, 0.14),
            rotation_frequency=(0.091, 0.057, 0.063),
            rotation_phase=(0.3, 1.5, 2.8),
        ),
        Joint(
            "upper_arm_l",
            "chest",
            (0.24, 0.20, 0.0),
            rotation_amplitude=(0.42, 0.25, 0.36),
            rotation_frequency=(0.047, 0.061, 0.033),
            rotation_phase=(1.8, 0.5, 2.3),
        ),
        Joint(
            "forearm_l",
            "upper_arm_l",
            (0.34, -0.24, 0.0),
            rotation_amplitude=(0.52, 0.18, 0.24),
            rotation_frequency=(0.071, 0.043, 0.051),
            rotation_phase=(0.7, 2.6, 1.2),
        ),
        Joint(
            "hand_l",
            "forearm_l",
            (0.31, -0.25, 0.0),
            rotation_amplitude=(0.22, 0.20, 0.28),
            rotation_frequency=(0.113, 0.089, 0.101),
            rotation_phase=(1.1, 2.2, 0.2),
        ),
        Joint(
            "upper_arm_r",
            "chest",
            (-0.24, 0.20, 0.0),
            rotation_amplitude=(0.39, 0.27, 0.33),
            rotation_frequency=(0.053, 0.067, 0.037),
            rotation_phase=(2.4, 1.0, 0.7),
        ),
        Joint(
            "forearm_r",
            "upper_arm_r",
            (-0.34, -0.24, 0.0),
            rotation_amplitude=(0.48, 0.16, 0.22),
            rotation_frequency=(0.077, 0.049, 0.057),
            rotation_phase=(1.5, 0.4, 2.1),
        ),
        Joint(
            "hand_r",
            "forearm_r",
            (-0.31, -0.25, 0.0),
            rotation_amplitude=(0.20, 0.18, 0.25),
            rotation_frequency=(0.107, 0.093, 0.097),
            rotation_phase=(2.0, 0.8, 1.4),
        ),
        Joint(
            "thigh_l",
            "pelvis",
            (0.14, -0.12, 0.0),
            rotation_amplitude=(0.28, 0.17, 0.12),
            rotation_frequency=(0.061, 0.041, 0.029),
            rotation_phase=(1.6, 2.4, 0.3),
        ),
        Joint(
            "shin_l",
            "thigh_l",
            (0.0, -0.48, 0.0),
            rotation_amplitude=(0.39, 0.11, 0.09),
            rotation_frequency=(0.067, 0.047, 0.033),
            rotation_phase=(0.5, 1.9, 2.7),
        ),
        Joint(
            "thigh_r",
            "pelvis",
            (-0.14, -0.12, 0.0),
            rotation_amplitude=(0.27, 0.16, 0.11),
            rotation_frequency=(0.059, 0.043, 0.031),
            rotation_phase=(2.2, 0.6, 1.3),
        ),
        Joint(
            "shin_r",
            "thigh_r",
            (0.0, -0.48, 0.0),
            rotation_amplitude=(0.37, 0.10, 0.08),
            rotation_frequency=(0.071, 0.051, 0.037),
            rotation_phase=(1.3, 2.8, 0.9),
        ),
    ]
    return ProceduralAnimation(joints, duration_seconds=duration_seconds, fps=fps)
