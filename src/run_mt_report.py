"""Marching tetrahedra vs marching cubes: topology consistency and thin-wall tests."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fields
from meshers import marching_tetrahedra, marching_cubes
from topology import analyze, fmt_report


def run_case(name, field, n, iso=1e-6):
    data, h = fields.sample(field, n)
    (mt_v, mt_t), tet_count = marching_tetrahedra(data, n, iso)
    mc_v, mc_t = marching_cubes(data, n, iso)
    mt_stats = analyze(mt_v, mt_t)
    mc_stats = analyze(mc_v, mc_t)
    print(f"=== {name} (grid {n}^3, h={h:.4f}) ===")
    print(f"  tetrahedra processed: {tet_count} (6 per cube x {(n-1)**3} cubes)")
    print(f"  MT triangles: {len(mt_t)}   MC triangles: {len(mc_t)}")
    print(fmt_report("marching-tetrahedra", mt_stats))
    print(fmt_report("marching-cubes", mc_stats))
    consistent = (mt_stats["chi"] == mc_stats["chi"]
                  and mt_stats["components"] == mc_stats["components"])
    print(f"  topology consistent (chi & components match): {consistent}")
    print()
    return mt_stats, mc_stats


def main():
    n = 33
    h = 2.0 / (n - 1)
    results = {}

    # 1) baseline shapes: MT vs MC topology consistency
    results["sphere"] = run_case("sphere r=0.75", fields.sphere(0.75), n)
    results["two_spheres"] = run_case("two spheres", fields.two_spheres(), n)

    # 2) thin-wall fields: wall thickness close to grid spacing
    for t_factor in (2.0, 1.5, 1.0):
        t = t_factor * h
        key = f"thin_slab_t={t_factor}h"
        results[key] = run_case(f"thin slab wall, thickness={t:.4f} ({t_factor}h)",
                                fields.thin_slab(t), n)
    for t_factor in (1.5, 2.0):
        t = t_factor * h
        results[f"thin_shell_t={t_factor}h"] = run_case(
            f"thin spherical shell, thickness={t:.4f} ({t_factor}h)",
            fields.thin_shell(0.7, t), n)
    # finer grid: same 1.5h-relative wall now sampled at 3h of the coarse grid
    n2 = 65
    h2 = 2.0 / (n2 - 1)
    results["thin_shell_fine"] = run_case(
        f"thin spherical shell on fine grid, thickness={3*h2:.4f}",
        fields.thin_shell(0.7, 3 * h2), n2)

    # 3) ambiguity stress test: 3D checkerboard (classic MC face ambiguity)
    results["checkerboard"] = run_case("checkerboard (ambiguity stress)",
                                       fields.checkerboard(h), n)

    # summary
    print("=== SUMMARY ===")
    ok = True
    for key, (mt, mc) in results.items():
        mt_ok = mt["watertight"] and mt["misoriented_edges"] == 0
        mc_ok = mc["watertight"]
        print(f"  {key:24s} MT watertight={mt['watertight']} "
              f"MC watertight={mc['watertight']} "
              f"chi(MT)={mt['chi']} chi(MC)={mc['chi']}")
        if key.startswith("thin") and not mt_ok:
            ok = False
    print(f"  thin-wall no-hole check (MT): {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
