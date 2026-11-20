"""Skeleton definition and forward kinematics."""
from .math3d import (q_identity, q_mul, q_rotate, v_add, v_sub, v_len)


class Joint:
    def __init__(self, name, parent, rest_offset, rest_rot=None):
        self.name = name
        self.parent = parent            # parent Joint or None
        self.rest_offset = rest_offset  # offset from parent in parent space
        self.rest_rot = rest_rot or q_identity()  # rest local rotation
        self.children = []
        if parent is not None:
            parent.children.append(self)

    def chain(self):
        out, j = [], self
        while j is not None:
            out.append(j)
            j = j.parent
        return list(reversed(out))


class Skeleton:
    """Hierarchical skeleton; pose = {joint_name: local_rotation}."""

    def __init__(self, name, root):
        self.name = name
        self.root = root
        self.joints = {}
        self._index(root)

    def _index(self, j):
        self.joints[j.name] = j
        for c in j.children:
            self._index(c)

    def rest_pose(self):
        return {n: j.rest_rot for n, j in self.joints.items()}

    def bone_length(self, joint_name):
        j = self.joints[joint_name]
        return v_len(j.rest_offset)

    def fk(self, pose, root_pos=(0.0, 0.0, 0.0)):
        """Return {joint_name: (world_pos, world_rot)}."""
        out = {}

        def walk(j, parent_pos, parent_rot):
            local_rot = pose.get(j.name, j.rest_rot)
            world_rot = q_mul(parent_rot, local_rot)
            offset = q_rotate(parent_rot, j.rest_offset)
            world_pos = v_add(parent_pos, offset)
            out[j.name] = (world_pos, world_rot)
            for c in j.children:
                walk(c, world_pos, world_rot)

        root_rot = pose.get(self.root.name, self.root.rest_rot)
        out[self.root.name] = (root_pos, root_rot)
        for c in self.root.children:
            walk(c, root_pos, root_rot)
        return out

    def total_height(self):
        fk = self.fk(self.rest_pose())
        ys = [p[0][1] for p in fk.values()]
        return max(ys) - min(ys)


def build_humanoid(name, hip_h, thigh, shin, arm, shoulder_w, torso):
    """Build a simple humanoid. Units in meters."""
    hips = Joint("hips", None, (0.0, 0.0, 0.0))
    spine = Joint("spine", hips, (0.0, torso * 0.5, 0.0))
    chest = Joint("chest", spine, (0.0, torso * 0.5, 0.0))
    neck = Joint("neck", chest, (0.0, 0.10, 0.0))
    Joint("head", neck, (0.0, 0.12, 0.0))
    for side, s in (("l", 1.0), ("r", -1.0)):
        up = Joint(f"upleg_{side}", hips, (s * shoulder_w * 0.5, 0.0, 0.0))
        lo = Joint(f"loleg_{side}", up, (0.0, -thigh, 0.0))
        Joint(f"foot_{side}", lo, (0.0, -shin, 0.0))
        sh = Joint(f"shoulder_{side}", chest, (s * shoulder_w, 0.05, 0.0))
        el = Joint(f"forearm_{side}", sh, (s * arm, 0.0, 0.0))
        Joint(f"hand_{side}", el, (s * arm * 0.8, 0.0, 0.0))
    skel = Skeleton(name, hips)
    skel.hip_height = hip_h
    return skel
