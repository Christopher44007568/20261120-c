"""Run every experiment and print a consolidated numeric summary."""

from __future__ import annotations

import numpy as np

from experiments import exp1_offsets, exp2_seams, exp3_wall, exp4_remesh


def main():
    print("=" * 70)
    print("EXP 1: reflection offsets (uncorrected / plane / box BPR)")
    print("=" * 70)
    path, summary = exp1_offsets.run()
    for key, vals in summary.items():
        print(f"  {key:12s} angular err  mean={np.mean(vals):7.3f}  "
              f"max={np.max(vals):7.3f} deg")
    print("  data:", path)

    print("=" * 70)
    print("EXP 2: boundary seams")
    print("=" * 70)
    path, hard_max, soft_max, volume_rows, convergence = exp2_seams.run()
    print(f"  hard switch max jump : {hard_max:7.3f} deg")
    print(f"  blended    max jump  : {soft_max:7.4f} deg")
    for row in volume_rows:
        print(f"  half={row[0]:4.1f} m  volume={row[1]:9.1f} m3  "
              f"hard={row[3]:6.3f} deg  blended={row[4]:.4f} deg")
    print("  refinement (eps, hard_L2, hard/eps, blend_L2, blend/eps):")
    for row in convergence:
        print(f"    eps={row[0]}  hard_L2={row[1]:.4f} (/{float(row[0]):.0e}"
              f"={row[2]:.1f})  blend_L2={row[3]:.2e} (ratio={row[4]:.3f})")
    print("  data:", path)

    print("=" * 70)
    print("EXP 3: near-wall probe, no-through-wall check")
    print("=" * 70)
    path, worst, leaks, bad_path = exp3_wall.run()
    print(f"  BPR max penetration: {worst:.3e} m over all rays; leaking rays: {leaks}")
    print("  control case data :", bad_path)
    print("  data:", path)

    print("=" * 70)
    print("EXP 4: organic remeshing")
    print("=" * 70)
    path, tri, quad, objs = exp4_remesh.run()
    print(f"  triangles: V={tri['vertex_count']} F={tri['face_count']} "
          f"edge_cv={tri['edge_cv']:.4f} watertight={tri['watertight']}")
    print(f"  quads    : V={quad['vertex_count']} F={quad['face_count']} "
          f"edge_cv={quad['edge_cv']:.4f} aspect_max={quad['aspect_max']:.3f} "
          f"watertight={quad['watertight']}")
    print("  meshes:", objs)
    print("  data:", path)


if __name__ == "__main__":
    main()
