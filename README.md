# 20261120-c

## Motion retargeting + thin-wall scalar field demo

Pure-stdlib Python 3 pipeline (no external deps):

- `retarget/` — skeleton/FK (`skeleton.py`), procedural walk with planted
  stance feet (`animate.py`), rotation-transplant retargeting with CCD-IK
  foot-lock constraint solver (`retarget.py`), error/sliding metrics
  (`metrics.py`), vector/quaternion math (`math3d.py`).
- `thinwall/` — marching-tetrahedra isosurface extraction with
  watertightness (no-hole) check (`marching.py`) and thin-walled scalar
  fields (`fields.py`).
- `run_all.py` — runs the whole pipeline and writes
  `artifacts/report.json`.

Run:

```sh
python3 run_all.py
```

The report contains the joint mapping, per-joint retargeting error
(before/after foot lock), IK constraint solver iteration counts, foot
sliding validation for targets with different leg lengths, skeleton
before/after comparison samples, and thin-wall isosurface topology
verification (boundary edges = 0, Euler characteristic matches).
