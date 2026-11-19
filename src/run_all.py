"""End-to-end driver: builds every result artifact for the report.

Outputs JSON files under ../artifacts:
  pn_control_points.json   - all 10 geometry + 6 normal control points/triangle
  pn_triangle_counts.json  - triangle counts at each tessellation level
  continuity.json          - edge control point, G1 normal and watertight checks
  silhouette.json          - contour smoothness metrics (low-poly vs PN vs CC)
  curvature_errors.json    - stratified position/normal error vs analytic torus
  volume_render.json       - ray-march/path-tracing transmittance experiment
"""
import json
import os

from mesh import make_icosahedron, make_torus
from pn_triangles import build_pn_patches, tessellate
from catmull_clark import subdivide_tris, compact, subdivide
from continuity import (check_edge_control_points, check_shared_edge_samples,
                        check_tessellation_watertight)
from silhouette2 import contour_report
from error_analysis import compare_methods, matched_budget_compare
from volume_render import run_experiment

OUT = os.path.join(os.path.dirname(__file__), "..", "artifacts")


def dump(name, payload):
    path = os.path.join(OUT, name)
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2)
    print("wrote", path)


def control_point_dump(mesh):
    patches, vnormals = build_pn_patches(mesh)
    tris = []
    for fi, (patch, face) in enumerate(zip(patches, mesh.faces)):
        tris.append({
            "face": list(face),
            "geometry_control_points": [
                {"ijk": list(k), "position": [round(c, 6) for c in p]}
                for k, p in sorted(patch.b.items())],
            "normal_control_points": [
                {"ijk": list(k), "normal": [round(c, 6) for c in p]}
                for k, p in sorted(patch.nn.items())],
        })
    return {
        "mesh": mesh.name,
        "n_faces": len(mesh.faces),
        "geometry_points_per_triangle": 10,
        "normal_points_per_triangle": 6,
        "vertex_normals": [[round(c, 6) for c in n] for n in vnormals],
        "triangles": tris,
    }


def main():
    ico = make_icosahedron()
    torus = make_torus(nu=10, nv=6)

    # 1. Control points for the first icosahedron face + full torus dump.
    dump("pn_control_points.json", control_point_dump(ico))

    # 2. Triangle counts at every tessellation level, both methods.
    counts = {"icosahedron": {"base_triangles": len(ico.faces)},
              "torus": {"base_triangles": len(torus.faces)}}
    for msh, key in ((ico, "icosahedron"), (torus, "torus")):
        pn_levels, cc_levels = [], []
        for level in (1, 2, 4, 8):
            v, f, n = tessellate(msh, level)
            pn_levels.append({"level": level, "triangles": len(f),
                              "vertices": len(v)})
        for level in (1, 2, 3):
            v, q = compact(*subdivide(msh.vertices, msh.faces, level))
            cc_levels.append({"level": level, "quads": len(q),
                              "triangles_after_split": 2 * len(q),
                              "vertices": len(v)})
        counts[key]["pn_triangles"] = pn_levels
        counts[key]["catmull_clark"] = cc_levels
    dump("pn_triangle_counts.json", counts)

    # 3. Continuity / no-crack verification.
    continuity = {}
    for msh in (ico, torus):
        v, f, n = tessellate(msh, 4)
        continuity[msh.name] = {
            "edge_control_points": check_edge_control_points(msh),
            "shared_edge_samples": check_shared_edge_samples(msh),
            "tessellation_watertight_L4":
                check_tessellation_watertight(v, f),
        }
    dump("continuity.json", continuity)

    # 4. Silhouette smoothness on the low-poly icosahedron.
    sil = []
    base = contour_report(ico.vertices, ico.faces,
                          ico.vertex_normals(), ref_radius=1.0)
    base["method_name"] = "low-poly icosahedron"
    sil.append(base)
    for level in (2, 4, 8, 16):
        v, f, n = tessellate(ico, level)
        rep = contour_report(v, f, n, ref_radius=1.0)
        rep["method_name"] = f"PN-triangles L={level}"
        rep["triangles"] = len(f)
        sil.append(rep)
    for level in (1, 2, 3):
        v, f = subdivide_tris(ico.vertices, ico.faces, level)
        from mesh import Mesh
        rep = contour_report(v, f, Mesh(v, f).vertex_normals(),
                             ref_radius=1.0)
        rep["method_name"] = f"Catmull-Clark L={level}"
        rep["triangles"] = len(f)
        sil.append(rep)
    dump("silhouette.json", sil)

    # 5. Curvature-stratified error on the analytic torus.
    errors = compare_methods(torus, R=1.0, r=0.4, level=3)
    matched = matched_budget_compare(torus, R=1.0, r=0.4)
    dump("curvature_errors.json", {
        "pn_tris": errors["pn"]["tris"],
        "cc_tris": errors["cc"]["tris"],
        "pn": errors["pn"]["report"],
        "catmull_clark": errors["cc"]["report"],
        "matched_budget_16x": matched,
    })

    # 6. Participating-medium transport experiment.
    dump("volume_render.json", run_experiment(n_rays=1000000))


if __name__ == "__main__":
    main()
