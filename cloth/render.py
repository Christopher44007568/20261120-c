"""Matplotlib helpers: shaded cloth renders with the table."""
from __future__ import annotations

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def table_patches(radius, h_top, n=48):
    """Cylinder side + top cap as vertex/face lists for rendering."""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    x, z = radius * np.cos(t), radius * np.sin(t)
    polys = []
    for i in range(n):
        j = (i + 1) % n
        polys.append([(x[i], z[i], 0.0), (x[j], z[j], 0.0),
                      (x[j], z[j], h_top), (x[i], z[i], h_top)])
    return polys


def _up(p):
    """Reorder (x, y=height, z) to matplotlib's (x, z, height)."""
    return p[..., [0, 2, 1]]


def shaded_surface(ax, positions, triangles, color="0.75", title="",
                   table=None, elev=20, azim=-60, lim=0.9, zmax=0.95,
                   ground=True):
    """Draw a cloth mesh with light-source shading (shows wrinkles).

    All polygons are merged into one Poly3DCollection so matplotlib's
    internal depth sort handles occlusion correctly.
    """
    polys, colors = [], []
    if ground:
        g = 1.15 * lim
        polys.append([(-g, -g, 0.0), (g, -g, 0.0),
                      (g, g, 0.0), (-g, g, 0.0)])
        colors.append(np.array([0.93, 0.93, 0.93, 1.0]))
    if table is not None:
        # Render the table slightly smaller so the cloth resting on it
        # (y == h_top) stays strictly above the rendered surface.
        for poly in table_patches(table.radius * 0.995, table.h_top - 0.008):
            polys.append(poly)
            colors.append(np.array([0.45, 0.45, 0.45, 1.0]))
    p0 = _up(positions[triangles[:, 0]])
    p1 = _up(positions[triangles[:, 1]])
    p2 = _up(positions[triangles[:, 2]])
    fn = np.cross(p1 - p0, p2 - p0)
    ln = np.linalg.norm(fn, axis=1, keepdims=True)
    ln[ln < 1e-30] = 1.0
    fn = fn / ln
    light = np.array([0.4, 0.8, 0.45])
    light = light / np.linalg.norm(light)
    diff = np.abs(fn @ light)
    shade = 0.25 + 0.75 * diff
    base = np.array(matplotlib.colors.to_rgb(color))
    rgb = np.clip(base[None, :] * shade[:, None], 0, 1)
    polys.extend(zip(p0, p1, p2))
    colors.extend(np.column_stack([rgb, np.ones(len(rgb))]))
    mesh = Poly3DCollection(polys, facecolors=colors, edgecolors="none")
    ax.add_collection3d(mesh)
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(0.0, zmax)
    ax.view_init(elev=elev, azim=azim)
    ax.set_box_aspect((2 * lim, 2 * lim, zmax))
    ax.set_title(title, fontsize=10)
    ax.set_axis_off()


def new_fig(ncols, nrows=1, size=4.2):
    fig = plt.figure(figsize=(size * ncols, size * nrows))
    axes = []
    for i in range(nrows * ncols):
        axes.append(fig.add_subplot(nrows, ncols, i + 1, projection="3d"))
    return fig, axes
