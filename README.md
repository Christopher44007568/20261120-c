# 20261120-c

Two self-contained C++20 benchmarks, no dependencies beyond `pthreads`.

## Build

```
make            # builds frustum_cull and offset_shell
```

## 1. Parallel multi-core frustum culling (`frustum_cull`)

- One million deterministic AABB instances spread over a 4000-unit cube.
- Six-plane perspective frustum; per-box p-vertex/n-vertex plane test.
- A persistent worker pool (barrier synchronized, CPU-pinned, reusable
  per-thread buffers) splits the index range into one contiguous chunk per
  thread, each thread writes a private visible-id vector, and the vectors are
  concatenated (merged) with no lock on the hot loop.
- Correctness: the fast conservative test is checked against an exact
  8-corner reference. False culls must be zero; the few extra "visible" boxes
  are the standard conservative corner cases (reported as an over-estimate %).
- Timing uses 60 rounds per thread count and reports avg/min/median ms plus
  average- and best-case speedup and parallel efficiency.

```
make bench                       # or: ./frustum_cull 1000000 60
```

Output: console table plus `artifacts/frustum_cull_benchmark.csv`.

## 2. Offset shell volume, completeness and self-intersection repair (`offset_shell`)

- Analytic signed-distance fields for a sphere (R=1) and a torus (R=1, r=0.4)
  sampled on a uniform voxel grid (default 150^3).
- Offset at distance `d` uses the SDF iso-surfaces: outer solid `phi <= +d`,
  cavity `phi <= -d`; shell material is outer minus cavity. The level set
  regularizes self-intersections automatically (a naive normal offset folds
  through itself once `d` exceeds the local half-thickness; the SDF instead
  pinches a cavity shut into one clean closed body).
- For each offset distance it reports measured shell volume (voxel count) vs
  the analytic shell volume and relative error, 6-connected component count,
  and a cubical-complex manifold/watertightness test (interior lattice-edge
  fan parity) that catches cracks and non-manifold/self-intersecting geometry.
- A naive normal-offset section flags where self-intersection begins and
  confirms the inner surface scan-lines vanish while the SDF shell stays a
  single closed body (inner and outer surfaces stay continuous at the pinch).

```
make shell                       # numeric + topology report (no meshes)
./offset_shell 150 obj           # additionally writes OBJ boundary meshes
```

Output: `artifacts/offset_shell_report.txt`,
`artifacts/sphere_offset_volumes.csv`, `artifacts/torus_offset_volumes.csv`,
and optional `artifacts/*.obj`.
