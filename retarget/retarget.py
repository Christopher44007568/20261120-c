"""Motion retargeting with foot-lock IK constraint solver."""
import math
from .math3d import (q_mul, q_conj, q_norm, q_rotate, q_between, q_angle,
                     v_sub, v_add, v_scale, v_len, v_norm, v_cross, v_dot)

# Joint mapping: source joint name -> target joint name.
JOINT_MAP = {
    "hips": "hips",
    "spine": "spine",
    "chest": "chest",
    "neck": "neck",
    "head": "head",
    "upleg_l": "upleg_l", "loleg_l": "loleg_l", "foot_l": "foot_l",
    "upleg_r": "upleg_r", "loleg_r": "loleg_r", "foot_r": "foot_r",
    "shoulder_l": "shoulder_l", "forearm_l": "forearm_l", "hand_l": "hand_l",
    "shoulder_r": "shoulder_r", "forearm_r": "forearm_r", "hand_r": "hand_r",
}


def detect_contacts(fk_frames, foot_names, height_thresh=0.09,
                    vel_thresh=0.35, fps=30):
    """Mark frames where each foot is in contact (low and slow)."""
    contacts = {f: [] for f in foot_names}
    prev = {f: None for f in foot_names}
    for i, (_, _, fk) in enumerate(fk_frames):
        for f in foot_names:
            p = fk[f][0]
            v = 0.0
            if prev[f] is not None:
                v = v_len(v_sub(p, prev[f])) * fps
            if p[1] < height_thresh and v < vel_thresh:
                contacts[f].append(i)
            prev[f] = p
    return contacts


class Retargeter:
    def __init__(self, src, tgt, joint_map=JOINT_MAP):
        self.src = src
        self.tgt = tgt
        self.map = joint_map
        self.h_ratio = tgt.hip_height / src.hip_height
        # Rest world rotations for delta computation.
        self.src_rest = src.fk(src.rest_pose(), (0.0, src.hip_height, 0.0))
        self.tgt_rest = tgt.fk(tgt.rest_pose(), (0.0, tgt.hip_height, 0.0))
        self.ik_iterations = 0
        self.ik_solves = 0

    def retarget_frame(self, src_pose, src_root):
        """Map local rotations via world-space delta transplant."""
        src_fk = self.src.fk(src_pose, src_root)
        tgt_pose = self.tgt.rest_pose()
        for s_name, t_name in self.map.items():
            if s_name not in src_fk or t_name not in self.tgt.joints:
                continue
            s_world = src_fk[s_name][1]
            s_rest = self.src_rest[s_name][1]
            t_rest = self.tgt_rest[t_name][1]
            # World delta from source rest, applied to target rest world.
            delta = q_mul(s_world, q_conj(s_rest))
            t_world = q_norm(q_mul(delta, t_rest))
            # Convert world rotation back to target local rotation.
            parent = self.tgt.joints[t_name].parent
            if parent is None:
                tgt_pose[t_name] = t_world
            else:
                # Parent world rot under current (already retargeted) pose;
                # approximate with FK of partial pose.
                fk = self.tgt.fk(tgt_pose,
                                 (0.0, self.tgt.hip_height, 0.0))
                p_world = fk[parent.name][1]
                tgt_pose[t_name] = q_norm(q_mul(q_conj(p_world), t_world))
        # Scale root translation by hip-height ratio.
        tgt_root = v_scale(src_root, self.h_ratio)
        return tgt_pose, tgt_root

    # ---- CCD IK foot lock ---------------------------------------------
    def ik_solve(self, pose, root_pos, chain_names, target_pos,
                 max_iter=20, tol=1e-4):
        """CCD IK on a joint chain; returns (pose, iterations_used)."""
        it = 0
        for it in range(1, max_iter + 1):
            fk = self.tgt.fk(pose, root_pos)
            eff = fk[chain_names[-1]][0]
            err = v_sub(target_pos, eff)
            if v_len(err) < tol:
                break
            for jn in reversed(chain_names[:-1]):
                fk = self.tgt.fk(pose, root_pos)
                jpos, jwrot = fk[jn]
                eff = fk[chain_names[-1]][0]
                to_eff = v_norm(v_sub(eff, jpos))
                to_tgt = v_norm(v_sub(target_pos, jpos))
                dq = q_between(to_eff, to_tgt)
                # World-space delta -> local space of the joint.
                parent = self.tgt.joints[jn].parent
                pw = fk[parent.name][1] if parent else (1.0, 0.0, 0.0, 0.0)
                local_delta = q_mul(q_mul(q_conj(pw), dq), pw)
                pose[jn] = q_norm(q_mul(local_delta, pose[jn]))
        self.ik_iterations += it
        self.ik_solves += 1
        return pose, it

    def foot_lock(self, frames_src_fk, frames_tgt):
        """Pin planted feet; frames_tgt = list of [pose, root_pos]."""
        feet = ("foot_l", "foot_r")
        contacts = detect_contacts(frames_src_fk, feet)
        planted = {f: None for f in feet}
        chains = {f: [j.name for j in
                      self.tgt.joints[f].chain()[1:]] for f in feet}
        n_frames = len(frames_tgt)
        for f in feet:
            cset = set(contacts[f])
            for i in range(n_frames):
                pose, root = frames_tgt[i]
                if i in cset:
                    if planted[f] is None:
                        fk = self.tgt.fk(pose, root)
                        planted[f] = fk[f][0]
                    frames_tgt[i][0], _ = self.ik_solve(
                        pose, root, chains[f], planted[f])
                else:
                    planted[f] = None
        return frames_tgt
