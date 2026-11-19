from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from math import ceil, floor

from .animation import Joint, JointPose, ProceduralAnimation
from .math3d import (
    dequantize_signed,
    quat_angle_degrees,
    quat_dot,
    quat_mul,
    quat_normalize,
    quat_rotate,
    quat_slerp,
    quantize_signed,
    vec_add,
    vec_length,
    vec_lerp,
    vec_sub,
)


@dataclass(frozen=True)
class QuantizedKey:
    rotation_codes: tuple[int, int, int, int]
    position_codes: tuple[int, int, int]


@dataclass(frozen=True)
class CompressedJoint:
    name: str
    parent: str | None
    position_bounds: tuple[tuple[float, float], ...]
    keys: tuple[QuantizedKey, ...]


@dataclass(frozen=True)
class CompressionResult:
    animation: "CompressedAnimation"
    stats: dict[str, float | int]


@dataclass(frozen=True)
class CompressedAnimation:
    duration_seconds: float
    fps: int
    bits: int
    key_times: tuple[float, ...]
    joints: tuple[CompressedJoint, ...]

    def _decode_joint(self, joint: CompressedJoint, key_index: int) -> JointPose:
        key = joint.keys[key_index]
        rotation = tuple(
            dequantize_signed(code, -1.0, 1.0, self.bits)
            for code in key.rotation_codes
        )
        position = tuple(
            dequantize_signed(code, low, high, self.bits)
            for code, (low, high) in zip(key.position_codes, joint.position_bounds)
        )
        return JointPose(position=position, rotation=quat_normalize(rotation))  # type: ignore[arg-type]

    def local_poses_at(self, time_seconds: float) -> list[JointPose]:
        if time_seconds <= self.key_times[0]:
            return [self._decode_joint(joint, 0) for joint in self.joints]
        if time_seconds >= self.key_times[-1]:
            return [self._decode_joint(joint, len(joint.keys) - 1) for joint in self.joints]

        lower_index = bisect_right(self.key_times, time_seconds) - 1
        upper_index = lower_index + 1
        time0 = self.key_times[lower_index]
        time1 = self.key_times[upper_index]
        alpha = (time_seconds - time0) / (time1 - time0)
        poses = []
        for joint in self.joints:
            start = self._decode_joint(joint, lower_index)
            end = self._decode_joint(joint, upper_index)
            poses.append(
                JointPose(
                    position=vec_lerp(start.position, end.position, alpha),
                    rotation=quat_slerp(start.rotation, end.rotation, alpha),
                )
            )
        return poses

    def world_poses_at(self, time_seconds: float) -> list[JointPose]:
        local = self.local_poses_at(time_seconds)
        index_by_name = {joint.name: index for index, joint in enumerate(self.joints)}
        world: list[JointPose] = []
        for index, joint in enumerate(self.joints):
            pose = local[index]
            if joint.parent is None:
                world.append(pose)
                continue
            parent = world[index_by_name[joint.parent]]
            world.append(
                JointPose(
                    position=vec_add(
                        parent.position,
                        quat_rotate(parent.rotation, pose.position),
                    ),
                    rotation=quat_mul(parent.rotation, pose.rotation),
                )
            )
        return world


def compress_animation(
    animation: ProceduralAnimation,
    bits: int = 16,
    keyframe_hz: float = 10.0,
) -> CompressionResult:
    if not 4 <= bits <= 24:
        raise ValueError("bits must be in [4, 24]")
    if keyframe_hz <= 0.0:
        raise ValueError("keyframe_hz must be positive")

    key_count = int(floor(animation.duration_seconds * keyframe_hz)) + 1
    key_time_list = [index / keyframe_hz for index in range(key_count)]
    if key_time_list[-1] < animation.duration_seconds - 1.0e-12:
        key_time_list.append(animation.duration_seconds)
    key_times = tuple(key_time_list)
    key_samples = [animation.local_poses_at(time) for time in key_times]
    compressed_joints = []

    for joint_index, joint in enumerate(animation.joints):
        positions = [samples[joint_index].position for samples in key_samples]
        bounds = tuple(
            (
                min(position[axis] for position in positions),
                max(position[axis] for position in positions),
            )
            for axis in range(3)
        )
        keys = []
        for samples in key_samples:
            pose = samples[joint_index]
            rotation = pose.rotation
            if quat_dot(rotation, (0.0, 0.0, 0.0, 1.0)) < 0.0:
                rotation = tuple(-component for component in rotation)  # type: ignore[assignment]
            rotation_codes = tuple(
                quantize_signed(component, -1.0, 1.0, bits)
                for component in rotation
            )
            position_codes = tuple(
                quantize_signed(pose.position[axis], bounds[axis][0], bounds[axis][1], bits)
                for axis in range(3)
            )
            keys.append(
                QuantizedKey(
                    rotation_codes=rotation_codes,  # type: ignore[arg-type]
                    position_codes=position_codes,  # type: ignore[arg-type]
                )
            )
        compressed_joints.append(
            CompressedJoint(
                name=joint.name,
                parent=joint.parent,
                position_bounds=bounds,
                keys=tuple(keys),
            )
        )

    compressed = CompressedAnimation(
        duration_seconds=animation.duration_seconds,
        fps=animation.fps,
        bits=bits,
        key_times=key_times,
        joints=tuple(compressed_joints),
    )
    stats = _compression_stats(animation, compressed, keyframe_hz)
    return CompressionResult(animation=compressed, stats=stats)


def _compression_stats(
    source: ProceduralAnimation,
    compressed: CompressedAnimation,
    keyframe_hz: float,
) -> dict[str, float | int]:
    joint_count = len(source.joints)
    source_frames = source.frame_count
    key_count = len(compressed.key_times)
    baseline_bytes = source_frames * joint_count * 7 * 4
    keyframe_float_bytes = key_count * joint_count * 7 * 4
    payload_bits = key_count * joint_count * 7 * compressed.bits
    payload_bytes = ceil(payload_bits / 8)
    key_time_bytes = key_count * 4
    joint_metadata_bytes = joint_count * (6 * 4 + 16)
    compressed_bytes = payload_bytes + key_time_bytes + joint_metadata_bytes
    return {
        "source_frames": source_frames,
        "joint_count": joint_count,
        "duration_seconds": source.duration_seconds,
        "source_fps": source.fps,
        "keyframe_hz": keyframe_hz,
        "key_count": key_count,
        "bits": compressed.bits,
        "baseline_bytes": baseline_bytes,
        "keyframe_float_bytes": keyframe_float_bytes,
        "payload_bytes": payload_bytes,
        "metadata_bytes": key_time_bytes + joint_metadata_bytes,
        "compressed_bytes": compressed_bytes,
        "compression_ratio": baseline_bytes / compressed_bytes,
        "keyframe_reduction_ratio": source_frames / key_count,
        "quantization_ratio": keyframe_float_bytes / payload_bytes,
    }
