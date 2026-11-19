# 20261120-c

Pure-stdlib Python validation harness for two rendering techniques. No
third-party dependencies; charts are hand-written SVG.

## Particle LOD and aggregation — `particle_lod.py`

120k particles in a spherical cloud. Particles whose projected screen disk
is smaller than 12 px² are merged into 16px screen-grid aggregate
primitives; each primitive carries the merged particle count, so projected
screen-space density (mass per area) is preserved exactly on the aggregate
grid. A ±25% hysteresis band suppresses LOD flicker.

Run: `python3 particle_lod.py`

Outputs in `artifacts/`:
- `particle_lod_report.md` / `.json` — per-distance LOD0/LOD1 counts,
  aggregate primitives, batch counts vs the no-LOD baseline, coarse (16px)
  and fine (4px) density errors, mass ratio, LOD-switch TV distance, and a
  hysteresis on/off round-trip popping control.
- `lod_counts.svg`, `draw_calls.svg`, `density_error.svg`,
  `frame_continuity.svg`, `hysteresis_control.svg`, and reference/LOD
  density heat maps for near and far cameras.

## Area-light soft shadows — `area_shadows.py`

Equal-area (4.0) capsule, disk and rectangle lights shadowed by a sphere.
In the far field the occluder becomes a projected disk on the light plane,
so the shadow factor is the analytic planar overlap between the light
shape and the silhouette disk: two-circle formula for disks, an exact
quadrant integral for rectangles, and adaptive Simpson quadrature with
analytic per-slice integrands for capsules.

Run: `python3 area_shadows.py`

Outputs in `artifacts/`:
- `area_shadow_report.md` / `.json` — umbra / 50% / penumbra edge radii
  per light shape, analytic-vs-dense-grid overlap validation, and an
  independent 3D Monte Carlo ray-test comparison.
- `shadow_edges.svg`, `analytic_validation.svg`.
