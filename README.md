# 20261120-c

Rotation keyframe interpolation comparison and edge-aware scalar-field
reconstruction.

- `python3 rotation_interp.py` — compares slerp / nlerp / Euler-angle
  keyframe interpolation, verifies shortest-path behaviour for >180 deg
  segments, prints angular errors, writes
  `artifacts/rotation_trajectory.png` and `artifacts/rotation_report.txt`.
- `python3 scalar_field_edges.py` — reconstructs a scalar field with a
  sharp edge from coarse samples (bilinear vs edge-aware), prints
  reconstruction error and edge sharpness, writes
  `artifacts/scalar_field_edges.png` and `artifacts/scalar_field_report.txt`.
