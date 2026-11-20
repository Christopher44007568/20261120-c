"""Procedural walk with truly planted stance feet (analytic 2-bone IK)."""
import math
from .math3d import q_axis_angle


def _smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


class Gait:
    """Alternating gait along +Z with duty factor and stride length."""

    def __init__(self, freq=1.0, stride=0.6, duty=0.6, lift=0.08):
        self.freq = freq
        self.stride = stride
        self.duty = duty
        self.lift = lift
        self.speed = stride * freq

    def foot_target(self, side, t, root_z):
        """World (z, y) target of a foot at time t."""
        off = 0.0 if side == "l" else 0.5 * self.stride
        d = self.duty
        half = 0.5 * d * self.stride
        z = root_z
        n = math.floor((z + half - off) / self.stride)
        for cand in (n, n + 1):
            plant_z = off + cand * self.stride
            if plant_z - half <= z <= plant_z + half:
                return plant_z, 0.0, True
        n = math.floor((z - half - off) / self.stride)
        z0 = off + n * self.stride
        z1 = off + (n + 1) * self.stride
        r0 = z0 + half
        r1 = z1 - half
        u = (z - r0) / max(r1 - r0, 1e-9)
        y = self.lift * 4.0 * u * (1.0 - u)
        return z0 + (z1 - z0) * _smoothstep(u), y, False


def _leg_ik(thigh, shin, dz, dy):
    """2-bone IK in the sagittal plane; returns (hip_pitch, knee_bend)."""
    dist = math.hypot(dz, dy)
    dist = min(dist, thigh + shin - 1e-6)
    dist = max(dist, abs(thigh - shin) + 1e-6)
    cos_k = (thigh * thigh + shin * shin - dist * dist) / (2 * thigh * shin)
    knee = math.pi - math.acos(max(-1.0, min(1.0, cos_k)))
    beta = math.atan2(dz, -dy)
    cos_a = (thigh * thigh + dist * dist - shin * shin) / (2 * thigh * dist)
    alpha = math.acos(max(-1.0, min(1.0, cos_a)))
    hip_pitch = -(beta + alpha)
    return hip_pitch, knee


def walk_pose(skel, t, gait, ankle_h=0.05):
    """Walk pose with planted stance feet. Returns (pose, root_pos)."""
    pose = skel.rest_pose()
    hip_h = skel.hip_height
    thigh = skel.bone_length("loleg_l")
    shin = skel.bone_length("foot_l")
    phase = 2.0 * math.pi * gait.freq * t
    root_z = gait.speed * t
    root_pos = (0.0, hip_h + 0.015 * math.sin(2.0 * phase), root_z)

    for side, lat in (("l", 0.10), ("r", -0.10)):
        fz, fy, stance = gait.foot_target(side, t, root_z)
        hip_z = root_z
        hip_y = root_pos[1]
        dz = fz - hip_z
        dy = (fy + ankle_h) - hip_y
        hip_pitch, knee = _leg_ik(thigh, shin, dz, dy)
        x = (1.0, 0.0, 0.0)
        pose[f"upleg_{side}"] = q_axis_angle(x, hip_pitch)
        pose[f"loleg_{side}"] = q_axis_angle(x, knee)
        pose[f"foot_{side}"] = q_axis_angle(x, -(hip_pitch + knee))
        pose[f"shoulder_{side}"] = q_axis_angle(x, 0.5 * hip_pitch)
    pose["spine"] = q_axis_angle((0.0, 1.0, 0.0),
                                 math.radians(3.0) * math.sin(phase))
    return pose, root_pos


def sample_animation(skel, gait, duration=3.0, fps=30):
    """Return list of (t, pose, root_pos)."""
    n = int(duration * fps) + 1
    frames = []
    for i in range(n):
        t = i / fps
        pose, root = walk_pose(skel, t, gait)
        frames.append((t, pose, root))
    return frames
