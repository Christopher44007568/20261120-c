# Quad Remeshing + Visibility/Deferred Frame-Budget Study

This repository contains a dependency-free, deterministic experiment that:

- converts triangulated organic meshes into pure quad meshes while retaining authored feature edges;
- compares triangle and quad edge-length variance, interior-angle distributions, and quad quality;
- validates two organic models at coarse, nominal, and fine tessellations;
- reports exact, length-weighted, and geometric feature-edge retention;
- estimates framebuffer memory and per-frame traffic for visibility-buffer and deferred rendering;
- cross-checks the rendering accounting with a deterministic CPU rasterizer.

No Python packages outside the standard library are required.

## Run

```bash
python3 run_experiment.py
python3 -m unittest discover -s tests -v
```

The first command rewrites every result, mesh, CSV, and SVG under `artifacts/`.
The full run takes about two seconds on the reference machine.

## Results

| Model | Triangles | Quads | Edge-length CV | Mean quad quality | Feature retention | Subdivision ready |
|---|---:|---:|---:|---:|---:|---|
| `organic_ring` (closed) | 3,456 | 1,728 | 0.187 -> 0.115 | 0.943 | 100% | yes |
| `organic_leaf` (open) | 2,688 | 1,344 | 0.207 -> 0.133 | 0.987 | 100% | yes |

All coarse/nominal/fine variants pass the same checks. The visibility buffer uses
37.5%-46.2% less framebuffer memory for 1x-4x MSAA. Its total traffic advantage is
conditional: 7.1% at 1080p/1x MSAA with a perfectly coherent material fetch, and
31.2% at 4x MSAA. Large per-pixel material-cache penalties can make deferred
rendering win when MSAA is not used.

See `REPORT.md` for the detailed tables, interpretation, assumptions, and limitations.

## Important Artifacts

- `artifacts/results.json`: complete machine-readable results.
- `artifacts/data/organic_summary.csv`: primary mesh-quality comparison.
- `artifacts/data/organic_variants.csv`: coarse/nominal/fine stability checks.
- `artifacts/data/histograms.csv`: quality, angle, and edge-length histograms.
- `artifacts/data/rendering_frames.csv`: memory and traffic at 1080p/1440p/4K.
- `artifacts/data/rendering_sensitivity.csv`: G-buffer size and cache-penalty sweep.
- `artifacts/data/raster_cross_check.csv`: actual projected coverage and traffic counts.
- `artifacts/meshes/`: source triangle meshes and remeshed quads in OBJ/JSON.
- `artifacts/charts/`: quality histograms, angle/edge distributions, wireframes, and rendering charts.

## Method

Each synthetic organic reference is generated as a quad grid, split by its shorter
diagonal, and passed to the remesher as a pure triangle mesh. The remesher sees
only vertices, triangles, and feature-edge tags. It builds candidate quads from
triangle pairs, rejects pairs crossing feature edges, finds a maximum-cardinality
matching on the triangle dual graph (including blossom contractions), and improves
pair weights by local swaps. The authored reference quads are used only for an
independent recovery check.

The renderer comparison is an architecture/model experiment, not a hardware GPU
profile. The common depth-test, vertex-fetch, texture, and rasterization costs are
excluded from both paths. See `REPORT.md` for the exact byte layout and equations.
