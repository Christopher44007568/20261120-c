# 20261120-c

## Skin SSS diffusion-profile analysis

`sss_analysis.py` builds a per-RGB diffusion profile for skin subsurface
scattering (Jensen dipole), applies it as a screen-space blur to a synthetic
face irradiance, validates backlit translucency for a thin ear (2 mm) vs a
thick cheek (12 mm), and compares the diffusion profile against a
variance-matched Gaussian approximation using a Monte Carlo photon
random-walk reference.

Run:

```
python3 sss_analysis.py   # needs numpy, scipy, matplotlib
```

Outputs in `artifacts/`:

- `sss_profiles.png` — diffusion profile vs Gaussian vs MC reference, per channel
- `sss_blur_comparison.png` — screen-space blur luminance and error maps
- `sss_translucency.png` — backlit thin-ear vs thick-cheek luminance
- `sss_report.json` — scatter radii, translucency, luminance error metrics
