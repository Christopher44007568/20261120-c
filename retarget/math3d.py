"""Pure-python 3D math: vectors and quaternions (w, x, y, z)."""
import math


def v_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def v_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def v_len(a):
    return math.sqrt(v_dot(a, a))


def v_norm(a):
    n = v_len(a)
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def v_lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


def q_identity():
    return (1.0, 0.0, 0.0, 0.0)


def q_mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def q_conj(q):
    return (q[0], -q[1], -q[2], -q[3])


def q_norm(q):
    n = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
    if n < 1e-12:
        return q_identity()
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def q_axis_angle(axis, angle):
    ax = v_norm(axis)
    h = 0.5 * angle
    s = math.sin(h)
    return (math.cos(h), ax[0] * s, ax[1] * s, ax[2] * s)


def q_rotate(q, v):
    qv = (0.0, v[0], v[1], v[2])
    r = q_mul(q_mul(q, qv), q_conj(q))
    return (r[1], r[2], r[3])


def q_between(a, b):
    """Quaternion rotating unit vector a to unit vector b."""
    d = v_dot(a, b)
    if d > 1.0 - 1e-9:
        return q_identity()
    if d < -1.0 + 1e-9:
        axis = v_cross((1.0, 0.0, 0.0), a)
        if v_len(axis) < 1e-9:
            axis = v_cross((0.0, 1.0, 0.0), a)
        return q_axis_angle(axis, math.pi)
    axis = v_cross(a, b)
    q = (1.0 + d, axis[0], axis[1], axis[2])
    return q_norm(q)


def q_angle(q):
    """Absolute rotation angle of a quaternion in radians."""
    w = max(-1.0, min(1.0, abs(q[0])))
    return 2.0 * math.acos(w)


def q_slerp(a, b, t):
    d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
    if d < 0.0:
        b = (-b[0], -b[1], -b[2], -b[3])
        d = -d
    if d > 0.9995:
        return q_norm(tuple(a[i] + (b[i] - a[i]) * t for i in range(4)))
    th = math.acos(max(-1.0, min(1.0, d)))
    sa, sb = math.sin((1 - t) * th), math.sin(t * th)
    s = math.sin(th)
    return tuple((sa * a[i] + sb * b[i]) / s for i in range(4))
