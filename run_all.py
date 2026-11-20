"""Motion retargeting pipeline demo + thin-wall scalar field check.

Outputs artifacts/report.json with joint mapping, retargeting errors,
IK solver stats, foot-sliding validation, skeleton comparison, and
thin-wall isosurface watertightness (no-hole) verification.
"""
import json
import math
import os

from retarget.skeleton import build_humanoid
from retarget.animate import Gait, sample_animation
from retarget.retarget import Retargeter, JOINT_MAP, detect_contacts
from retarget.metrics import (orientation_errors, foot_sliding,
                              cumulative_foot_drift)
from thinwall.marching import (extract_isosurface, check_watertight,
                               euler_characteristic)
from thinwall.fields import sphere_shell, plate_shell

FPS = 30
DURATION = 3.0
ANKLE_H = 0.05


def make_skeletons():
    # (thigh, shin, torso, arm, shoulder_w, stance_bend)
    specs = {
        "target_same": (0.45, 0.45, 0.55, 0.28, 0.20, 0.07),
        "target_longlegs": (0.56, 0.50, 0.45, 0.26, 0.19, 0.04),
        "target_shortlegs": (0.34, 0.38, 0.62, 0.30, 0.21, 0.10),
    }
    src = build_humanoid("source", 0.88, 0.45, 0.45, 0.28, 0.20, 0.55)
    targets = {}
    for name, (th, sh, torso, arm, sw, bend) in specs.items():
        targets[name] = build_humanoid(name, th + sh - bend + ANKLE_H,
                                       th, sh, arm, sw, torso)
    return src, targets


def bone_table(src, tgt):
    rows = []
    for j in ("loleg_l", "foot_l", "forearm_l", "spine", "chest"):
        rows.append({
            "bone": j,
            "source_m": round(src.bone_length(j), 4),
            "target_m": round(tgt.bone_length(j), 4),
            "ratio": round(tgt.bone_length(j) / src.bone_length(j), 4),
        })
    return rows


def retarget_one(src, tgt, src_frames, src_fk_frames, contacts):
    rt = Retargeter(src, tgt)
    tgt_frames = []
    for (_, pose, root) in src_frames:
        p, r = rt.retarget_frame(pose, root)
        tgt_frames.append([p, r])

    slide_before = cumulative_foot_drift(rt, tgt_frames, contacts)
    err_before = orientation_errors(
        rt, [(p, r) for (_, p, r) in src_frames], tgt_frames)

    rt.foot_lock(src_fk_frames, tgt_frames)

    slide_after = cumulative_foot_drift(rt, tgt_frames, contacts)
    slip_after = foot_sliding(rt, tgt_frames, contacts)
    err_after = orientation_errors(
        rt, [(p, r) for (_, p, r) in src_frames], tgt_frames)

    def rnd(d):
        return {k: round(v, 6) for k, v in d.items()}

    return rt, tgt_frames, {
        "stance_drift_before_lock_m": rnd(slide_before),
        "stance_drift_after_lock_m": rnd(slide_after),
        "per_frame_slip_after_lock": slip_after,
        "orientation_error_before_lock_deg": {
            "mean": {k: round(v, 4) for k, v in
                     err_before["mean_deg"].items()},
            "max": {k: round(v, 4) for k, v in
                    err_before["max_deg"].items()},
        },
        "orientation_error_after_lock_deg": {
            "mean": {k: round(v, 4) for k, v in
                     err_after["mean_deg"].items()},
            "max": {k: round(v, 4) for k, v in
                    err_after["max_deg"].items()},
        },
        "ik_solver": {
            "solves": rt.ik_solves,
            "total_iterations": rt.ik_iterations,
            "avg_iterations_per_solve": round(
                rt.ik_iterations / max(rt.ik_solves, 1), 3),
            "tolerance_m": 1e-4,
            "max_iterations": 20,
        },
    }


def skeleton_comparison(src, tgt, src_frames, tgt_frames, sample_ids):
    """World joint positions before/after retargeting at sample frames."""
    out = []
    for i in sample_ids:
        (_, s_pose, s_root) = src_frames[i]
        s_fk = src.fk(s_pose, s_root)
        t_fk = tgt.fk(tgt_frames[i][0], tgt_frames[i][1])
        row = {"frame": i, "joints": {}}
        for s_name, t_name in JOINT_MAP.items():
            sp = s_fk[s_name][0]
            tp = t_fk[t_name][0]
            row["joints"][t_name] = {
                "source_xyz": [round(c, 4) for c in sp],
                "target_xyz": [round(c, 4) for c in tp],
            }
        out.append(row)
    return out


def thinwall_check():
    """Extract thin-walled isosurfaces; verify watertight (no holes)."""
    results = {}
    cases = {
        "sphere_shell_t6cm": (
            sphere_shell((0, 0, 0), 1.0, 0.06),
            ((-1.3, -1.3, -1.3), (1.3, 1.3, 1.3)), 4),
        "plate_shell_t5cm": (
            plate_shell((0, 0, 0), (0.8, 0.5, 0.02), 0.05),
            ((-1.0, -0.7, -0.3), (1.0, 0.7, 0.3)), 2),
    }
    for name, (field, bounds, expected_euler) in cases.items():
        # Resolution: grid step <= wall_thickness / 2.5 keeps the wall
        # resolved so the extractor cannot bridge or puncture it.
        thickness = 0.06 if "sphere" in name else 0.05
        step = thickness / 2.5
        res = tuple(max(8, int(math.ceil((bounds[1][a] - bounds[0][a])
                                         / step)) + 1) for a in range(3))
        verts, tris = extract_isosurface(field, bounds, res)
        wt = check_watertight(tris)
        chi = euler_characteristic(verts, tris)
        results[name] = {
            "grid_resolution": res,
            "wall_thickness_m": thickness,
            "cells_across_wall": round(thickness / step, 2),
            "num_vertices": len(verts),
            "num_triangles": wt["num_triangles"],
            "boundary_edges": wt["boundary_edges"],
            "nonmanifold_edges": wt["nonmanifold_edges"],
            "watertight_no_holes": wt["watertight"],
            "euler_characteristic": chi,
            "expected_euler": expected_euler,
            "topology_ok": chi == expected_euler,
        }
    return results


def source_self_check(src, src_fk_frames, contacts):
    """Source animation must itself be slide-free (planted by design)."""
    out = {}
    for f in ("foot_l", "foot_r"):
        cset = set(contacts[f])
        planted, worst = None, 0.0
        for i, (_, _, fk) in enumerate(src_fk_frames):
            p = fk[f][0]
            if i in cset:
                if planted is None:
                    planted = p
                d = math.sqrt(sum((p[k] - planted[k]) ** 2 for k in range(3)))
                worst = max(worst, d)
            else:
                planted = None
        out[f] = round(worst, 8)
    return out


def main():
    src, targets = make_skeletons()
    gait = Gait(freq=1.0, stride=0.6, duty=0.6, lift=0.08)
    src_frames = sample_animation(src, gait, DURATION, FPS)
    src_fk_frames = [(None, None, src.fk(p, r)) for (_, p, r) in src_frames]
    contacts = detect_contacts(src_fk_frames, ("foot_l", "foot_r"))

    report = {
        "config": {"fps": FPS, "duration_s": DURATION,
                   "frames": len(src_frames),
                   "gait": {"freq_hz": gait.freq,
                            "stride_m": gait.stride,
                            "duty_factor": gait.duty}},
        "joint_mapping": JOINT_MAP,
        "source_skeleton": {
            "hip_height_m": round(src.hip_height, 4),
            "total_height_m": round(src.total_height(), 4),
            "thigh_m": src.bone_length("loleg_l"),
            "shin_m": src.bone_length("foot_l"),
        },
        "source_contact_frames": {k: len(v) for k, v in contacts.items()},
        "source_stance_drift_m": source_self_check(src, src_fk_frames,
                                                   contacts),
        "targets": {},
        "thin_wall_scalar_field": thinwall_check(),
    }

    sample_ids = [0, 15, 30, 45, 60, 75, 90]
    for name, tgt in targets.items():
        rt, tgt_frames, metrics = retarget_one(
            src, tgt, src_frames, src_fk_frames, contacts)
        report["targets"][name] = {
            "hip_height_m": round(tgt.hip_height, 4),
            "leg_length_ratio_vs_source": round(
                (tgt.bone_length("loleg_l") + tgt.bone_length("foot_l"))
                / (src.bone_length("loleg_l") + src.bone_length("foot_l")),
                4),
            "bone_length_table": bone_table(src, tgt),
            "metrics": metrics,
            "skeleton_comparison_samples": skeleton_comparison(
                src, tgt, src_frames, tgt_frames, sample_ids),
        }

    os.makedirs("artifacts", exist_ok=True)
    path = os.path.join("artifacts", "report.json")
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2)
    print_summary(report)
    return report


def print_summary(report):
    print("=== Retargeting summary ===")
    print(f"frames={report['config']['frames']} "
          f"contacts={report['source_contact_frames']}")
    for name, t in report["targets"].items():
        m = t["metrics"]
        print(f"\n[{name}] leg_ratio={t['leg_length_ratio_vs_source']}")
        print(f"  drift before lock: {m['stance_drift_before_lock_m']}")
        print(f"  drift after  lock: {m['stance_drift_after_lock_m']}")
        ik = m["ik_solver"]
        print(f"  IK solves={ik['solves']} iters={ik['total_iterations']} "
              f"avg={ik['avg_iterations_per_solve']}")
        em = m["orientation_error_after_lock_deg"]["mean"]
        worst = max(em.values())
        print(f"  orient err mean(max joint)={worst:.3f} deg")
    print("\n=== Thin-wall scalar field ===")
    for name, r in report["thin_wall_scalar_field"].items():
        print(f"[{name}] watertight={r['watertight_no_holes']} "
              f"boundary_edges={r['boundary_edges']} "
              f"euler={r['euler_characteristic']}"
              f"(expect {r['expected_euler']})")


if __name__ == "__main__":
    main()
