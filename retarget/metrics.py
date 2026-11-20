"""Retargeting quality metrics: orientation error and foot sliding."""
import math
from .math3d import q_mul, q_conj, q_angle, v_sub, v_len
from .retarget import detect_contacts


def orientation_errors(rt, src_frames, tgt_frames):
    """Per-joint world-orientation error (deg) after delta transplant."""
    src_rest = rt.src_rest
    tgt_rest = rt.tgt_rest
    sums, counts, worst = {}, {}, {}
    for (s_pose, s_root), (t_pose, t_root) in zip(src_frames, tgt_frames):
        s_fk = rt.src.fk(s_pose, s_root)
        t_fk = rt.tgt.fk(t_pose, t_root)
        for s_name, t_name in rt.map.items():
            s_delta = q_mul(s_fk[s_name][1], q_conj(src_rest[s_name][1]))
            t_delta = q_mul(t_fk[t_name][1], q_conj(tgt_rest[t_name][1]))
            err = math.degrees(q_angle(q_mul(s_delta, q_conj(t_delta))))
            sums[t_name] = sums.get(t_name, 0.0) + err
            counts[t_name] = counts.get(t_name, 0) + 1
            worst[t_name] = max(worst.get(t_name, 0.0), err)
    mean = {k: sums[k] / counts[k] for k in sums}
    return {"mean_deg": mean, "max_deg": worst}


def foot_sliding(rt, tgt_frames, contacts, fps=30):
    """Per-frame horizontal slip of planted feet during contact phases."""
    feet = ("foot_l", "foot_r")
    fk_frames = [(None, None, rt.tgt.fk(p, r)) for (p, r) in tgt_frames]
    report = {}
    for f in feet:
        cset = set(contacts[f])
        planted, drifts = None, []
        for i, (_, _, fk) in enumerate(fk_frames):
            p = fk[f][0]
            if i in cset:
                if planted is None:
                    planted = p
                dx = p[0] - planted[0]
                dz = p[2] - planted[2]
                drifts.append(math.sqrt(dx * dx + dz * dz))
                planted = p
            else:
                planted = None
        report[f] = {
            "contact_frames": len(contacts[f]),
            "max_step_slip_m": max(drifts) if drifts else 0.0,
            "mean_step_slip_m": (sum(drifts) / len(drifts)) if drifts else 0.0,
        }
    return report


def cumulative_foot_drift(rt, tgt_frames, contacts):
    """Max distance from the initial plant position per contact phase."""
    feet = ("foot_l", "foot_r")
    fk_frames = [(None, None, rt.tgt.fk(p, r)) for (p, r) in tgt_frames]
    report = {}
    for f in feet:
        cset = set(contacts[f])
        planted, worst = None, 0.0
        for i, (_, _, fk) in enumerate(fk_frames):
            p = fk[f][0]
            if i in cset:
                if planted is None:
                    planted = p
                worst = max(worst, v_len(v_sub(p, planted)))
            else:
                planted = None
        report[f] = worst
    return report
