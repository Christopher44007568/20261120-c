"""Run the full Loop-subdivision lab and print a report."""
from looplab.subdivision import subdivide_levels
from looplab.curvature import curvature_stats
from looplab.testmeshes import grid_mesh, bump_mesh, fold_mesh
from looplab.sampling import compare_sampling
from looplab.verify import run_all

LEVELS = 3


def section(title):
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def report_levels_and_counts():
    section("1. Subdivision levels vs vertex/face counts (Loop, bump mesh)")
    meshes = subdivide_levels(bump_mesh(4), "loop", LEVELS)
    print(f"{'level':>5} {'vertices':>10} {'faces':>10} {'boundary_v':>11}")
    for lvl, m in enumerate(meshes):
        print(f"{lvl:>5} {len(m.vertices):>10} {len(m.faces):>10} "
              f"{len(m.boundary_vertices):>11}")
    return meshes


def report_curvature(meshes):
    section("2. Curvature after refinement: Loop vs Butterfly (interior)")
    bf = subdivide_levels(bump_mesh(4), "butterfly", LEVELS)
    header = f"{'level':>5} {'scheme':>10} {'max|K|':>10} {'mean|K|':>10} " \
             f"{'max|H|':>10} {'mean|H|':>10}"
    print(header)
    for lvl in range(LEVELS + 1):
        for scheme, set_ in (("loop", meshes), ("butterfly", bf)):
            s = curvature_stats(set_[lvl])
            print(f"{lvl:>5} {scheme:>10} {s['max|K|']:>10.4f} "
                  f"{s['mean|K|']:>10.4f} {s['max|H|']:>10.4f} "
                  f"{s['mean|H|']:>10.4f}")


def report_rule_checks():
    section("3. Subdivision rule verification (boundary vs interior)")
    for name, ok, detail in run_all():
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def report_sharp_edge():
    section("4. Sharp-edge behaviour of Loop subdivision")
    mesh, crease = fold_mesh(4, 90.0)
    tagged = subdivide_levels(mesh, "loop", LEVELS)
    from looplab.verify import _refined_dihedral
    for lvl, m in enumerate(tagged):
        d = _refined_dihedral(m, len(mesh.vertices))
        print(f"  crease-tagged   level {lvl}: sharpest dihedral = {d:.2f} deg")
    smooth = subdivide_levels(
        type(mesh)(mesh.vertices, mesh.faces), "loop", LEVELS)
    for lvl, m in enumerate(smooth):
        d = _refined_dihedral(m, len(mesh.vertices))
        print(f"  untagged(smooth) level {lvl}: sharpest dihedral = {d:.2f} deg")


def report_sampling():
    section("5. Importance sampling near the highlight (GGX, alpha=0.2)")
    r = compare_sampling()
    for key, label in (("uniform", "uniform hemisphere"),
                       ("ggx", "GGX importance")):
        s = r[key]
        print(f"  {label:<20} n={s['samples']} "
              f"near-highlight={s['near_highlight_pct']:5.1f}% "
              f"dark-waste={s['dark_waste_pct']:5.1f}% "
              f"mean NDF weight={s['mean_ndf_weight']:.3f}")
        print(f"    theta histogram (0-90 deg, 10 bins): {s['theta_hist_deg']}")


if __name__ == "__main__":
    meshes = report_levels_and_counts()
    report_curvature(meshes)
    report_rule_checks()
    report_sharp_edge()
    report_sampling()
