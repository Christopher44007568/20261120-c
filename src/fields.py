"""Scalar fields on regular grids, including thin-wall cases."""
import math


def make_grid(n, lo=-1.0, hi=1.0):
    """Return (xs, h): n sample coordinates per axis and spacing."""
    h = (hi - lo) / (n - 1)
    return [lo + i * h for i in range(n)], h


def sample(field, n, lo=-1.0, hi=1.0):
    """Sample field(x, y, z) into a flat list, index = x + n*(y + n*z)."""
    xs, h = make_grid(n, lo, hi)
    data = [0.0] * (n * n * n)
    for k, z in enumerate(xs):
        for j, y in enumerate(xs):
            base = n * (j + n * k)
            for i, x in enumerate(xs):
                data[i + base] = field(x, y, z)
    return data, h


def sphere(r=0.75):
    return lambda x, y, z: r - math.sqrt(x * x + y * y + z * z)


def two_spheres():
    def f(x, y, z):
        d1 = math.sqrt((x + 0.45) ** 2 + y * y + z * z) - 0.4
        d2 = math.sqrt((x - 0.45) ** 2 + y * y + z * z) - 0.4
        return -min(d1, d2)
    return f


def thin_slab(thickness, half=0.7):
    """Axis-aligned thin wall: slab |z|<=t/2 clipped to a square plate."""
    def f(x, y, z):
        d_slab = abs(z) - thickness / 2.0
        d_clip = max(abs(x), abs(y)) - half
        return -max(d_slab, d_clip)
    return f


def thin_shell(r=0.7, thickness=0.1):
    """Thin spherical shell wall."""
    def f(x, y, z):
        d = abs(math.sqrt(x * x + y * y + z * z) - r) - thickness / 2.0
        return -d
    return f


def checkerboard(h):
    """Alternating +/- field at grid nodes: worst case for MC face ambiguity."""
    def f(x, y, z):
        if max(abs(x), abs(y), abs(z)) > 0.875:
            return -1.0  # padding keeps the surface off the domain boundary
        i = round((x + 1.0) / h)
        j = round((y + 1.0) / h)
        k = round((z + 1.0) / h)
        return 1.0 if (i + j + k) % 2 == 0 else -1.0
    return f
