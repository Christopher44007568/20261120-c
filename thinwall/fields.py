"""Thin-walled scalar fields (signed-distance style)."""
import math


def sphere_shell(center, radius, thickness):
    """Thin spherical shell: iso-0 surface is the shell mid-surface
    bounded by wall thickness; field<0 inside the wall material."""
    cx, cy, cz = center
    half = 0.5 * thickness

    def f(p):
        d = math.sqrt((p[0] - cx) ** 2 + (p[1] - cy) ** 2 +
                      (p[2] - cz) ** 2)
        return abs(d - radius) - half
    return f


def plate_shell(center, size, thickness):
    """Thin rectangular plate (box shell) with given half-sizes."""
    cx, cy, cz = center
    hx, hy, hz = size
    half = 0.5 * thickness

    def f(p):
        dx = abs(p[0] - cx) - hx
        dy = abs(p[1] - cy) - hy
        dz = abs(p[2] - cz) - hz
        box = math.sqrt(max(dx, 0.0) ** 2 + max(dy, 0.0) ** 2 +
                        max(dz, 0.0) ** 2) + min(max(dx, dy, dz), 0.0)
        return abs(box) - half
    return f
