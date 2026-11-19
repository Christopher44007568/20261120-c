"""Remesh an organic triangle mesh into a uniform quad mesh and verify."""

from __future__ import annotations

import os

from .common import DATA_DIR, MESH_DIR, PLOT_DIR, save_csv
from parallax.mesh_quality import uniformity_report, write_obj
from parallax.remesh import organic_quad_mesh, organic_tri_mesh


def run():
    tri_points, tri_faces = organic_tri_mesh(subdivisions=3)
    quad_points, quad_faces = organic_quad_mesh(resolution=16)

    tri_report = uniformity_report(tri_points, tri_faces)
    quad_report = uniformity_report(quad_points, quad_faces)

    tri_obj = os.path.join(MESH_DIR, "organic_input_triangles.obj")
    quad_obj = os.path.join(MESH_DIR, "organic_remeshed_quads.obj")
    write_obj(tri_obj, tri_points, tri_faces)
    write_obj(quad_obj, quad_points, quad_faces)

    rows = []
    all_keys = sorted(set(tri_report) | set(quad_report))
    for key in all_keys:
        rows.append([key, tri_report.get(key, "-"), quad_report.get(key, "-")])
    csv_path = os.path.join(DATA_DIR, "exp4_remesh_quality.csv")
    save_csv(csv_path, ["metric", "input_triangle_mesh", "remeshed_quad_mesh"], rows)

    _plot(tri_points, tri_faces, quad_points, quad_faces)
    return csv_path, tri_report, quad_report, (tri_obj, quad_obj)


def _plot(tri_points, tri_faces, quad_points, quad_faces):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    from parallax.mesh_quality import edge_lengths

    fig = plt.figure(figsize=(12, 8))
    ax1 = fig.add_subplot(2, 2, 1, projection="3d")
    ax2 = fig.add_subplot(2, 2, 2, projection="3d")
    ax3 = fig.add_subplot(2, 2, 3)
    ax4 = fig.add_subplot(2, 2, 4)

    def draw(ax, points, faces, title, color, limit):
        polys = [[points[i] for i in face[:3]] for face in faces[:limit]]
        coll = Poly3DCollection(polys, alpha=0.7, facecolor=color,
                                edgecolors="k", linewidths=0.2)
        ax.add_collection3d(coll)
        ax.set_title(title)
        ax.set_xlim(-1.4, 1.4)
        ax.set_ylim(-1.4, 1.4)
        ax.set_zlim(-1.4, 1.4)
        ax.set_box_aspect((1, 1, 1))
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_zticks([])

    draw(ax1, tri_points, tri_faces, "Input: organic triangle mesh",
         "#8fb8de", 900)
    draw(ax2, quad_points, quad_faces, "Remeshed: uniform quads",
         "#7fc97f", 900)

    tri_l = edge_lengths(tri_points, tri_faces)
    quad_l = edge_lengths(quad_points, quad_faces)
    bins = 24
    ax3.hist(tri_l, bins=bins, density=True, alpha=0.6, label="triangles",
             color="#8fb8de")
    ax3.hist(quad_l, bins=bins, density=True, alpha=0.6, label="quads",
             color="#7fc97f")
    ax3.set_xlabel("edge length")
    ax3.set_ylabel("density")
    ax3.set_title("Edge-length distribution")
    ax3.legend()

    from parallax.mesh_quality import face_angles
    tri_angles = [a for f in tri_faces for a in face_angles(tri_points, f)]
    quad_angles = [a for f in quad_faces for a in face_angles(quad_points, f)]
    ax4.hist(tri_angles, bins=bins, density=True, alpha=0.6, label="triangles",
             color="#8fb8de")
    ax4.hist(quad_angles, bins=bins, density=True, alpha=0.6, label="quads",
             color="#7fc97f")
    ax4.axvline(90, color="k", ls="--", lw=1)
    ax4.set_xlabel("face angle (deg)")
    ax4.set_ylabel("density")
    ax4.set_title("Face-angle distribution")
    ax4.legend()

    fig.tight_layout()
    out = os.path.join(PLOT_DIR, "exp4_remesh.png")
    fig.savefig(out, dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    path, tri, quad, objs = run()
    print("wrote", path)
    print(f"triangle edge CV: {tri['edge_cv']:.4f} watertight={tri['watertight']}")
    print(f"quad     edge CV: {quad['edge_cv']:.4f} watertight={quad['watertight']}")
    print("meshes:", objs)
