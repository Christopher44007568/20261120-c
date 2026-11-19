"""Sphere renderer for visual validation of the Ashikhmin velvet BRDF.
Renders cloth-shaded spheres with rotating fiber direction and grazing
light, comparing velvet vs anisotropic GGX. Pure stdlib.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brdf
from brdf import dot, norm, cross
import pngutil

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")

ALBEDO = (0.30, 0.04, 0.06)   # dark red cloth
LIGHT_COLOR = 6.0
AMBIENT = 0.03
SPEC_SCALE = 6.0              # boost specular lobe for visibility


def frame_at(n, phi):
    """Tangent frame on the sphere; fiber rotated by phi about n."""
    up = (0.0, 1.0, 0.0) if abs(n[1]) < 0.99 else (1.0, 0.0, 0.0)
    t0 = norm(cross(up, n))
    b0 = cross(n, t0)
    c, s = math.cos(phi), math.sin(phi)
    t = (c * t0[0] + s * b0[0], c * t0[1] + s * b0[1], c * t0[2] + s * b0[2])
    return t


def render(path, model, fiber_phi, light_dir, size=256, a=4.0,
           alpha_x=0.05, alpha_y=0.5):
    l = norm(light_dir)
    v = (0.0, 0.0, 1.0)
    pixels = []
    for py in range(size):
        row = []
        y = 1.0 - 2.0 * (py + 0.5) / size
        for px in range(size):
            x = 2.0 * (px + 0.5) / size - 1.0
            r2 = x * x + y * y
            if r2 > 1.0:
                row.append((16, 16, 20))
                continue
            n = (x, y, math.sqrt(1.0 - r2))
            t = frame_at(n, fiber_phi)
            nl = max(dot(n, l), 0.0)
            if model == "velvet":
                spec = brdf.velvet_aniso(l, v, n, t, 1.0, a)
            else:
                spec = brdf.ggx_aniso(l, v, n, t, alpha_x, alpha_y)
            rgb = []
            for c in range(3):
                diff = ALBEDO[c] * nl / math.pi
                val = AMBIENT * ALBEDO[c] + LIGHT_COLOR * nl * (
                    diff + SPEC_SCALE * spec)
                rgb.append(pngutil.tonemap(val, exposure=1.2))
            row.append(tuple(rgb))
        pixels.append(row)
    pngutil.write_png(path, size, size, pixels)
    print(f"  wrote {os.path.relpath(path)}")


def main():
    os.makedirs(OUT, exist_ok=True)
    print("== Rendering rotation set (velvet, light 45 deg) ==")
    light45 = (math.sin(math.radians(45)), 0.0, math.cos(math.radians(45)))
    for deg in (0, 45, 90, 135):
        render(os.path.join(OUT, f"rotate_velvet_{deg:03d}.png"),
               "velvet", math.radians(deg), light45)
    print("== Rendering grazing set (light 75 deg, fiber 0/90, velvet vs GGX) ==")
    light75 = (math.sin(math.radians(75)), 0.0, math.cos(math.radians(75)))
    for deg in (0, 90):
        render(os.path.join(OUT, f"grazing_velvet_{deg:03d}.png"),
               "velvet", math.radians(deg), light75)
        render(os.path.join(OUT, f"grazing_ggx_{deg:03d}.png"),
               "ggx", math.radians(deg), light75)


if __name__ == "__main__":
    main()
