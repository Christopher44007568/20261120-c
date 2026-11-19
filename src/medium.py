"""Participating media: homogeneous boxes and trilinear heterogeneous density fields."""

import numpy as np


class Medium:
    """A box-shaped medium whose extinction coefficient is
    sigma_t(p) = sigma_t0 * density(p), with a constant single-scattering albedo."""

    def __init__(self, bounds, density, sigma_t0, albedo=1.0):
        self.bounds = np.asarray(bounds, dtype=float)
        self.density = np.asarray(density, dtype=float)
        self.sigma_t0 = float(sigma_t0)
        self.albedo = float(albedo)
        self.majorant = self.sigma_t0 * float(self.density.max())

    @property
    def shape(self):
        return self.density.shape

    def _grid_coords(self, points):
        lo = self.bounds[0]
        extent = self.bounds[1] - self.bounds[0]
        u = (points - lo) / extent
        nx, ny, nz = self.density.shape
        return u * np.array([nx - 1.0, ny - 1.0, nz - 1.0])

    def density_at(self, points):
        """Trilinear interpolation of the density grid at (N,3) world points."""
        g = self._grid_coords(points)
        i0 = np.floor(g).astype(int)
        nx, ny, nz = self.density.shape
        i0 = np.clip(i0, 0, np.array([nx - 2, ny - 2, nz - 2]))
        i1 = i0 + 1
        f = g - i0
        d = self.density
        c000 = d[i0[:, 0], i0[:, 1], i0[:, 2]]
        c100 = d[i1[:, 0], i0[:, 1], i0[:, 2]]
        c010 = d[i0[:, 0], i1[:, 1], i0[:, 2]]
        c110 = d[i1[:, 0], i1[:, 1], i0[:, 2]]
        c001 = d[i0[:, 0], i0[:, 1], i1[:, 2]]
        c101 = d[i1[:, 0], i0[:, 1], i1[:, 2]]
        c011 = d[i0[:, 0], i1[:, 1], i1[:, 2]]
        c111 = d[i1[:, 0], i1[:, 1], i1[:, 2]]
        fx, fy, fz = f[:, 0], f[:, 1], f[:, 2]
        c00 = c000 * (1 - fx) + c100 * fx
        c10 = c010 * (1 - fx) + c110 * fx
        c01 = c001 * (1 - fx) + c101 * fx
        c11 = c011 * (1 - fx) + c111 * fx
        c0 = c00 * (1 - fy) + c10 * fy
        c1 = c01 * (1 - fy) + c11 * fy
        return c0 * (1 - fz) + c1 * fz

    def sigma_at(self, points):
        return self.sigma_t0 * self.density_at(points)


class HomogeneousMedium:
    """Constant sigma_t inside a box; supports the analytic Beer-Lambert check."""

    def __init__(self, bounds, sigma_t, albedo=1.0):
        self.bounds = np.asarray(bounds, dtype=float)
        self.sigma_t = float(sigma_t)
        self.albedo = float(albedo)
        self.majorant = self.sigma_t
        self.density = np.ones((2, 2, 2))
        self.sigma_t0 = self.sigma_t

    def sigma_at(self, points):
        return np.full(points.shape[0], self.sigma_t)

    def analytic_transmittance(self, distance):
        return float(np.exp(-self.sigma_t * distance))
