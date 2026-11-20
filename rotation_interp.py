"""Quaternion slerp / nlerp / Euler-angle keyframe interpolation comparison.

- Interpolates keyframe rotations with three methods.
- Verifies shortest-path behaviour for segments with >180 deg rotation.
- Outputs rotation trajectories, angular velocities and per-method
  angular error against the geodesic ground truth (slerp).
"""
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ---------- quaternion helpers (w, x, y, z) ----------
def q_normalize(q):
    return q / np.linalg.norm(q)


def q_mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ])


def q_conj(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])


def q_from_axis_angle(axis, angle):
    axis = np.asarray(axis, float)
    axis /= np.linalg.norm(axis)
    return np.array([np.cos(angle / 2), *(np.sin(angle / 2) * axis)])


def q_to_rotmat(q):
    w, x, y, z = q_normalize(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def q_angle_between(a, b):
    """Geodesic angle (rad) on SO(3), hemisphere-aware."""
    d = abs(float(np.dot(q_normalize(a), q_normalize(b))))
    return 2 * np.arccos(min(1.0, d))


def q_hemisphere(q0, q1):
    """Flip q1 sign so both lie on the same hemisphere (shortest path)."""
    return q1 if np.dot(q0, q1) >= 0 else -q1


def slerp(q0, q1, t):
    q1 = q_hemisphere(q0, q1)
    d = min(1.0, float(np.dot(q0, q1)))
    theta = np.arccos(d)
    if theta < 1e-8:
        return q_normalize(q0 + t * (q1 - q0))
    s = np.sin(theta)
    return q_normalize((np.sin((1 - t) * theta) * q0 + np.sin(t * theta) * q1) / s)


def nlerp(q0, q1, t):
    q1 = q_hemisphere(q0, q1)
    return q_normalize((1 - t) * q0 + t * q1)


# ---------- Euler (ZYX) helpers ----------
def quat_to_euler(q):
    w, x, y, z = q_normalize(q)
    sinr = 2 * (w * x + y * z)
    cosr = 1 - 2 * (x * x + y * y)
    roll = np.arctan2(sinr, cosr)
    sinp = 2 * (w * y - z * x)
    pitch = np.copysign(np.pi / 2, sinp) if abs(sinp) >= 1 else np.arcsin(sinp)
    siny = 2 * (w * z + x * y)
    cosy = 1 - 2 * (y * y + z * z)
    yaw = np.arctan2(siny, cosy)
    return np.array([roll, pitch, yaw])


def euler_to_quat(e):
    roll, pitch, yaw = e
    cr, sr = np.cos(roll / 2), np.sin(roll / 2)
    cp, sp = np.cos(pitch / 2), np.sin(pitch / 2)
    cy, sy = np.cos(yaw / 2), np.sin(yaw / 2)
    return q_normalize(np.array([
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ]))


def euler_lerp(e0, e1, t):
    """Naive lerp of the *authored* Euler angles (no unwrapping)."""
    return euler_to_quat((1 - t) * e0 + t * e1)


# ---------- keyframes ----------
# Each keyframe stores the authored Euler angles (deg, ZYX) and the
# equivalent quaternion.  Quaternion interpolation uses the quaternion,
# Euler interpolation lerps the authored angles directly (as a naive
# animation system would), which is what exposes the long-way problem.
def build_keyframes():
    d = np.deg2rad
    authored_euler = [
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 30.0),
        (0.0, 0.0, 300.0),    # 270 deg away as authored -> tests shortest path
        (0.0, 150.0, 120.0),  # large-angle keyframe
        (350.0, 40.0, 260.0), # large-angle keyframe
    ]
    times = [float(i) for i in range(len(authored_euler))]
    keys = []
    for e in authored_euler:
        e_rad = d(np.array(e))
        keys.append({"euler": e_rad, "q": euler_to_quat(e_rad)})
    return times, keys


def raw_relative_angle(q0, q1):
    """Rotation angle (deg) WITHOUT hemisphere fix; in [0, 360]."""
    d = float(np.dot(q_normalize(q0), q_normalize(q1)))
    return np.rad2deg(2 * np.arccos(np.clip(d, -1.0, 1.0)))


def interp(method, k0, k1, u):
    if method == "euler":
        return euler_lerp(k0["euler"], k1["euler"], u)
    fn = slerp if method == "slerp" else nlerp
    return fn(k0["q"], k1["q"], u)


METHODS = ("slerp", "nlerp", "euler")


def segment_relative_angles(times, keys):
    print("== Keyframe segments (relative rotation) ==")
    for i in range(len(times) - 1):
        raw = raw_relative_angle(keys[i]["q"], keys[i + 1]["q"])
        short = min(raw, 360.0 - raw)
        tag = "  <-- >180 deg, shortest path flips hemisphere" if raw > 180 else ""
        print(f"  seg {i}: t=[{times[i]:.0f},{times[i+1]:.0f}]  "
              f"raw = {raw:7.2f} deg, shortest = {short:7.2f} deg{tag}")


def sample_trajectory(times, keys, method, n_per_seg=200):
    ts, qs = [], []
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        seg_t = np.linspace(t0, t1, n_per_seg, endpoint=(i == len(times) - 2))
        for t in seg_t:
            u = (t - t0) / (t1 - t0)
            ts.append(t)
            qs.append(interp(method, keys[i], keys[i + 1], u))
    return np.array(ts), np.array(qs)


def angular_velocity(ts, qs):
    """|omega| (rad/s) from finite differences of the quaternion path."""
    omega = []
    for k in range(len(ts) - 1):
        dq = q_mul(q_conj(qs[k]), qs[k + 1])
        dq = q_hemisphere(np.array([1.0, 0, 0, 0]), dq)
        ang = 2 * np.arccos(min(1.0, abs(dq[0])))
        omega.append(ang / (ts[k + 1] - ts[k]))
    return np.array(omega)


def verify_shortest_path(times, keys):
    print("\n== Shortest-path verification (segments with raw rotation >180 deg) ==")
    ok_all = True
    found = False
    for i in range(len(times) - 1):
        k0, k1 = keys[i], keys[i + 1]
        raw = raw_relative_angle(k0["q"], k1["q"])
        if raw <= 180.0:
            continue
        found = True
        short_arc = 360.0 - raw
        us = np.linspace(0, 1, 1001)
        for name in METHODS:
            path = [interp(name, k0, k1, u) for u in us]
            dev = [np.rad2deg(q_angle_between(k0["q"], q)) for q in path]
            swept = sum(np.rad2deg(q_angle_between(path[k], path[k + 1]))
                        for k in range(len(path) - 1))
            if name == "euler":
                tag = ("LONG WAY (no hemisphere fix)"
                       if swept > short_arc + 1e-3 else "short")
                print(f"  seg {i} (raw {raw:5.1f} deg) {name:6s}: "
                      f"swept = {swept:6.2f} deg -> {tag}")
                continue
            ok = max(dev) <= short_arc + 1e-6 and swept <= short_arc + 1e-3
            ok_all &= ok
            print(f"  seg {i} (raw {raw:5.1f} deg) {name:6s}: max deviation "
                  f"from start = {max(dev):6.2f} deg, swept = {swept:6.2f} deg "
                  f"(short arc = {short_arc:5.1f} deg) -> "
                  f"{'SHORTEST OK, no detour' if ok else 'FAIL'}")
    if not found:
        print("  (no >180 deg segment found)")
        ok_all = False
    print(f"  shortest-path check: {'PASS' if ok_all else 'FAIL'}")
    return ok_all


def angular_errors(times, keys):
    """Angular error of each method vs geodesic ground truth (slerp)."""
    print("\n== Angular error vs geodesic ground truth (slerp) ==")
    print(f"  {'segment':<8}{'method':<8}{'max err (deg)':>14}{'mean err (deg)':>15}")
    summary = {}
    for i in range(len(times) - 1):
        k0, k1 = keys[i], keys[i + 1]
        us = np.linspace(0, 1, 201)[1:-1]
        truth = [slerp(k0["q"], k1["q"], u) for u in us]
        for name in METHODS:
            errs = [np.rad2deg(q_angle_between(interp(name, k0, k1, u), g))
                    for u, g in zip(us, truth)]
            summary.setdefault(name, []).extend(errs)
            print(f"  seg {i:<4d}{name:<8}{max(errs):>14.4f}{np.mean(errs):>15.4f}")
    print("\n  Overall (all segments, comparable metric: geodesic angle to slerp):")
    for name, errs in summary.items():
        print(f"  {name:<8} max = {max(errs):8.4f} deg   "
              f"mean = {np.mean(errs):8.4f} deg")
    return summary


def make_plots(times, keys):
    fig = plt.figure(figsize=(15, 4.5))
    ax3d = fig.add_subplot(131, projection="3d")
    v0 = np.array([1.0, 0.0, 0.0])
    colors = {"slerp": "tab:blue", "nlerp": "tab:orange", "euler": "tab:green"}
    sampled = {}
    for name in METHODS:
        ts, qs = sample_trajectory(times, keys, name)
        sampled[name] = (ts, qs)
        pts = np.array([q_to_rotmat(q) @ v0 for q in qs])
        ax3d.plot(*pts.T, color=colors[name], label=name, lw=1.2)
    ax3d.scatter(*v0, color="k", s=20)
    ax3d.set_title("Rotated x-axis trajectory on sphere")
    ax3d.legend(loc="upper left", fontsize=8)
    ax3d.set_box_aspect((1, 1, 1))

    axw = fig.add_subplot(132)
    for name, (ts, qs) in sampled.items():
        om = angular_velocity(ts, qs)
        axw.plot(0.5 * (ts[:-1] + ts[1:]), np.rad2deg(om),
                 color=colors[name], label=name, lw=1.0)
    axw.set_xlabel("t (s)")
    axw.set_ylabel("|omega| (deg/s)")
    axw.set_title("Angular velocity")
    axw.legend(fontsize=8)

    axe = fig.add_subplot(133)
    qg = sampled["slerp"][1]
    for name, (ts, qs) in sampled.items():
        errs = [np.rad2deg(q_angle_between(a, b)) for a, b in zip(qs, qg)]
        axe.plot(ts, errs, color=colors[name], label=name, lw=1.0)
    axe.set_xlabel("t (s)")
    axe.set_ylabel("error (deg)")
    axe.set_title("Angular error vs slerp ground truth")
    axe.legend(fontsize=8)

    fig.tight_layout()
    fig.savefig("artifacts/rotation_trajectory.png", dpi=150)
    print("\nfigure saved: artifacts/rotation_trajectory.png")


def main():
    times, keys = build_keyframes()
    segment_relative_angles(times, keys)
    ok = verify_shortest_path(times, keys)
    angular_errors(times, keys)
    make_plots(times, keys)
    if not ok:
        raise SystemExit("shortest-path verification failed")


if __name__ == "__main__":
    main()
