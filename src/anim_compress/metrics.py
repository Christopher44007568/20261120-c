from __future__ import annotations

from bisect import bisect_right
from math import ceil, sqrt

from .animation import Joint, JointPose, ProceduralAnimation
from .compression import CompressionResult
from .math3d import (
    quat_angle_degrees,
    quat_mul,
    quat_rotate,
    quat_slerp,
    vec_add,
    vec_length,
    vec_lerp,
    vec_sub,
)

END_EFFECTORS = ("head", "hand_l", "hand_r", "shin_l", "shin_r")


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def _summarize(values: list[float], sum_squares: float, count: int) -> dict[str, float]:
    if count == 0:
        return {"max": 0.0, "rmse": 0.0, "p95": 0.0}
    return {
        "max": max(values),
        "rmse": sqrt(sum_squares / count),
        "p95": _percentile(values, 0.95),
    }


def _world_from_local(joints: list[Joint], local: list[JointPose]) -> list[JointPose]:
    index_by_name = {joint.name: index for index, joint in enumerate(joints)}
    world: list[JointPose] = []
    for index, joint in enumerate(joints):
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


def _float_key_pose(
    joints: list[Joint],
    key_times: tuple[float, ...],
    key_samples: list[list[JointPose]],
    time_seconds: float,
) -> list[JointPose]:
    if time_seconds <= key_times[0]:
        return key_samples[0]
    if time_seconds >= key_times[-1]:
        return key_samples[-1]
    lower = bisect_right(key_times, time_seconds) - 1
    upper = lower + 1
    alpha = (time_seconds - key_times[lower]) / (key_times[upper] - key_times[lower])
    result = []
    for joint_index in range(len(joints)):
        start = key_samples[lower][joint_index]
        end = key_samples[upper][joint_index]
        result.append(
            JointPose(
                position=vec_lerp(start.position, end.position, alpha),
                rotation=quat_slerp(start.rotation, end.rotation, alpha),
            )
        )
    return result


def evaluate_reconstruction(
    source: ProceduralAnimation,
    result: CompressionResult,
    frame_stride: int = 1,
) -> dict[str, object]:
    compressed = result.animation
    frame_numbers = list(range(0, source.frame_count, max(1, frame_stride)))
    if frame_numbers[-1] != source.frame_count - 1:
        frame_numbers.append(source.frame_count - 1)
    key_samples = [source.local_poses_at(time) for time in compressed.key_times]
    joint_names = [joint.name for joint in source.joints]
    end_effectors = [name for name in END_EFFECTORS if name in joint_names]

    interpolation_rotation_values: list[float] = []
    interpolation_position_values: list[float] = []
    reconstruction_rotation_values: list[float] = []
    reconstruction_position_values: list[float] = []
    world_position_values: list[float] = []
    end_effector_values: list[float] = []
    interpolation_rotation_squares = 0.0
    interpolation_position_squares = 0.0
    reconstruction_rotation_squares = 0.0
    reconstruction_position_squares = 0.0
    world_position_squares = 0.0
    end_effector_squares = 0.0
    sample_count = 0

    series = {"time": [], "rotation_max_deg": [], "position_max": [], "world_position_max": []}
    series_stride = max(1, source.fps)
    window_rotation_peaks: list[float] = []
    window_index = 0
    window_span = max(1, ceil(len(frame_numbers) / 6))

    for frame_position, frame in enumerate(frame_numbers):
        time_seconds = min(source.duration_seconds, frame / source.fps)
        source_local = source.local_poses_at(time_seconds)
        decoded_local = compressed.local_poses_at(time_seconds)
        float_local = _float_key_pose(source.joints, compressed.key_times, key_samples, time_seconds)

        frame_rotation = 0.0
        frame_position_error = 0.0
        for index in range(len(source.joints)):
            interp_rotation = quat_angle_degrees(
                source_local[index].rotation, float_local[index].rotation
            )
            rotation = quat_angle_degrees(
                source_local[index].rotation, decoded_local[index].rotation
            )
            position = vec_length(
                vec_sub(source_local[index].position, decoded_local[index].position)
            )
            interpolation_position = vec_length(
                vec_sub(source_local[index].position, float_local[index].position)
            )
            interpolation_rotation_values.append(interp_rotation)
            interpolation_rotation_squares += interp_rotation * interp_rotation
            interpolation_position_values.append(interpolation_position)
            interpolation_position_squares += interpolation_position * interpolation_position
            reconstruction_rotation_values.append(rotation)
            reconstruction_rotation_squares += rotation * rotation
            reconstruction_position_values.append(position)
            reconstruction_position_squares += position * position
            frame_rotation = max(frame_rotation, rotation)
            frame_position_error = max(frame_position_error, position)
            sample_count += 1

        source_world = _world_from_local(source.joints, source_local)
        decoded_world = _world_from_local(source.joints, decoded_local)
        frame_world = 0.0
        for index in range(len(source.joints)):
            world_error = vec_length(
                vec_sub(source_world[index].position, decoded_world[index].position)
            )
            world_position_values.append(world_error)
            world_position_squares += world_error * world_error
            frame_world = max(frame_world, world_error)
            if joint_names[index] in end_effectors:
                end_effector_values.append(world_error)
                end_effector_squares += world_error * world_error

        if frame % series_stride == 0 or frame == frame_numbers[-1]:
            series["time"].append(round(time_seconds, 6))
            series["rotation_max_deg"].append(round(frame_rotation, 8))
            series["position_max"].append(round(frame_position_error, 10))
            series["world_position_max"].append(round(frame_world, 10))

        if window_index >= len(window_rotation_peaks):
            window_rotation_peaks.append(0.0)
        window_rotation_peaks[window_index] = max(window_rotation_peaks[window_index], frame_rotation)
        if (frame_position + 1) % window_span == 0:
            window_index += 1

    quant_rotation_values: list[float] = []
    quant_position_values: list[float] = []
    quant_rotation_squares = 0.0
    quant_position_squares = 0.0
    for key_time, original_samples in zip(compressed.key_times, key_samples):
        decoded_samples = compressed.local_poses_at(key_time)
        for original, decoded in zip(original_samples, decoded_samples):
            rotation_error = quat_angle_degrees(original.rotation, decoded.rotation)
            position_error = vec_length(vec_sub(original.position, decoded.position))
            quant_rotation_values.append(rotation_error)
            quant_position_values.append(position_error)
            quant_rotation_squares += rotation_error * rotation_error
            quant_position_squares += position_error * position_error

    interpolation_rotation = _summarize(
        interpolation_rotation_values,
        interpolation_rotation_squares,
        sample_count,
    )
    interpolation_position = _summarize(
        interpolation_position_values,
        interpolation_position_squares,
        sample_count,
    )
    reconstruction_rotation = _summarize(
        reconstruction_rotation_values,
        reconstruction_rotation_squares,
        sample_count,
    )
    reconstruction_position = _summarize(
        reconstruction_position_values,
        reconstruction_position_squares,
        sample_count,
    )
    world_position = _summarize(
        world_position_values,
        world_position_squares,
        len(world_position_values),
    )
    end_effector = _summarize(
        end_effector_values,
        end_effector_squares,
        len(end_effector_values),
    )
    quant_rotation = _summarize(
        quant_rotation_values,
        quant_rotation_squares,
        len(quant_rotation_values),
    )
    quant_position = _summarize(
        quant_position_values,
        quant_position_squares,
        len(quant_position_values),
    )

    metrics: dict[str, object] = dict(result.stats)
    metrics.update(
        {
            "interpolation_rotation_max_deg": interpolation_rotation["max"],
            "interpolation_rotation_rmse_deg": interpolation_rotation["rmse"],
            "interpolation_rotation_p95_deg": interpolation_rotation["p95"],
            "interpolation_position_max": interpolation_position["max"],
            "interpolation_position_rmse": interpolation_position["rmse"],
            "interpolation_position_p95": interpolation_position["p95"],
            "rotation_max_deg": reconstruction_rotation["max"],
            "rotation_rmse_deg": reconstruction_rotation["rmse"],
            "rotation_p95_deg": reconstruction_rotation["p95"],
            "position_max": reconstruction_position["max"],
            "position_rmse": reconstruction_position["rmse"],
            "position_p95": reconstruction_position["p95"],
            "world_position_max": world_position["max"],
            "world_position_rmse": world_position["rmse"],
            "end_effector_max": end_effector["max"],
            "end_effector_rmse": end_effector["rmse"],
            "quantization_rotation_max_deg": quant_rotation["max"],
            "quantization_rotation_rmse_deg": quant_rotation["rmse"],
            "quantization_rotation_p95_deg": quant_rotation["p95"],
            "quantization_position_max": quant_position["max"],
            "quantization_position_rmse": quant_position["rmse"],
            "quantization_position_p95": quant_position["p95"],
            "window_rotation_peaks_deg": [round(value, 8) for value in window_rotation_peaks],
            "first_window_rotation_peak_deg": window_rotation_peaks[0],
            "last_window_rotation_peak_deg": window_rotation_peaks[-1],
            "evaluated_frame_count": len(frame_numbers),
        }
    )

    return {
        "metrics": metrics,
        "series": series,
        "pose_comparison": _pose_comparison(source, compressed, end_effectors),
    }


def _pose_comparison(
    source: ProceduralAnimation,
    compressed: object,
    end_effectors: list[str],
) -> list[dict[str, object]]:
    times = [
        0.0,
        source.duration_seconds * 0.25,
        source.duration_seconds * 0.50,
        source.duration_seconds * 0.75,
        source.duration_seconds,
    ]
    joint_names = [joint.name for joint in source.joints]
    selected = [joint_names.index(name) for name in end_effectors]
    records = []
    for time_seconds in times:
        source_world = source.world_poses_at(time_seconds)
        decoded_world = compressed.world_poses_at(time_seconds)  # type: ignore[attr-defined]
        joints = []
        for index in selected:
            source_pose = source_world[index]
            decoded_pose = decoded_world[index]
            joints.append(
                {
                    "name": joint_names[index],
                    "source_position": [round(value, 7) for value in source_pose.position],
                    "decoded_position": [round(value, 7) for value in decoded_pose.position],
                    "position_error": round(
                        vec_length(vec_sub(source_pose.position, decoded_pose.position)), 8
                    ),
                    "rotation_error_deg": round(
                        quat_angle_degrees(source_pose.rotation, decoded_pose.rotation), 8
                    ),
                }
            )
        records.append({"time": round(time_seconds, 6), "joints": joints})
    return records
