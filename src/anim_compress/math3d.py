from __future__ import annotations

from math import acos, cos, pi, sin, sqrt

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]

IDENTITY_QUAT: Quat = (0.0, 0.0, 0.0, 1.0)


def vec_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec_scale(a: Vec3, scale: float) -> Vec3:
    return (a[0] * scale, a[1] * scale, a[2] * scale)


def vec_dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec_cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vec_length(a: Vec3) -> float:
    return sqrt(vec_dot(a, a))


def vec_normalize(a: Vec3) -> Vec3:
    length = vec_length(a)
    if length <= 1.0e-15:
        return (0.0, 0.0, 0.0)
    return vec_scale(a, 1.0 / length)


def vec_lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def quat_mul(a: Quat, b: Quat) -> Quat:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quat_normalize(q: Quat) -> Quat:
    length = sqrt(sum(component * component for component in q))
    if length <= 1.0e-15:
        return IDENTITY_QUAT
    return tuple(component / length for component in q)  # type: ignore[return-value]


def quat_conjugate(q: Quat) -> Quat:
    return (-q[0], -q[1], -q[2], q[3])


def quat_dot(a: Quat, b: Quat) -> float:
    return sum(x * y for x, y in zip(a, b))


def quat_from_axis_angle(axis: Vec3, angle: float) -> Quat:
    axis = vec_normalize(axis)
    half = angle * 0.5
    sine = sin(half)
    return (axis[0] * sine, axis[1] * sine, axis[2] * sine, cos(half))


def quat_from_euler_xyz(x: float, y: float, z: float) -> Quat:
    qx = quat_from_axis_angle((1.0, 0.0, 0.0), x)
    qy = quat_from_axis_angle((0.0, 1.0, 0.0), y)
    qz = quat_from_axis_angle((0.0, 0.0, 1.0), z)
    return quat_normalize(quat_mul(qz, quat_mul(qy, qx)))


def quat_rotate(q: Quat, point: Vec3) -> Vec3:
    q = quat_normalize(q)
    rotated = quat_mul(quat_mul(q, (point[0], point[1], point[2], 0.0)), quat_conjugate(q))
    return (rotated[0], rotated[1], rotated[2])


def quat_slerp(a: Quat, b: Quat, t: float) -> Quat:
    if t <= 0.0:
        return quat_normalize(a)
    if t >= 1.0:
        return quat_normalize(b)
    a = quat_normalize(a)
    b = quat_normalize(b)
    dot = quat_dot(a, b)
    if dot < 0.0:
        b = tuple(-component for component in b)  # type: ignore[assignment]
        dot = -dot
    if dot > 0.9995:
        blend = tuple(a[i] + (b[i] - a[i]) * t for i in range(4))
        return quat_normalize(blend)  # type: ignore[arg-type]
    theta = acos(max(-1.0, min(1.0, dot)))
    sine = sin(theta)
    wa = sin((1.0 - t) * theta) / sine
    wb = sin(t * theta) / sine
    return quat_normalize(tuple(wa * a[i] + wb * b[i] for i in range(4)))  # type: ignore[arg-type]


def quat_angle_degrees(a: Quat, b: Quat) -> float:
    dot = min(1.0, abs(quat_dot(quat_normalize(a), quat_normalize(b))))
    return 2.0 * acos(dot) * 180.0 / pi


def quantize_signed(value: float, minimum: float, maximum: float, bits: int) -> int:
    levels = (1 << bits) - 1
    if maximum <= minimum:
        return 0
    normalized = (value - minimum) / (maximum - minimum)
    return max(0, min(levels, int(round(normalized * levels))))


def dequantize_signed(code: int, minimum: float, maximum: float, bits: int) -> float:
    levels = (1 << bits) - 1
    return minimum + (maximum - minimum) * code / levels


def quantization_step(minimum: float, maximum: float, bits: int) -> float:
    return (maximum - minimum) / ((1 << bits) - 1)
