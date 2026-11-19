# 20261120-c

IES (photometric web / 光域网) lighting lab, pure Python 3 stdlib.

- `ies_toolkit.py` — LM-63 parser, candela sampling by incident angle
  (bilinear in theta/phi with symmetry unfolding), intensity scaling,
  total-flux integration, and an IES texture class with a box-filter
  mip chain and GPU-style LOD selection.
- `generate_ies.py` — writes `ies/spot.ies` (narrow symmetric spot) and
  `ies/wallwash.ies` (asymmetric wall-wash), both normalized to 1500 lm.
- `analyze.py` — candela tables, point-vs-IES highlight shapes on a
  floor grid, directionality checks, flux consistency, and a mip /
  moire test for distant minified sampling.

Run: `python3 generate_ies.py && python3 analyze.py`
