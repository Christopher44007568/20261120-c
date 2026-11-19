"""Stdlib PNG rasterizer for the three-noise Welch spectra."""

import math

from layout.noise import generate_noises, welch_psd
from tools.rasterize_routing import Canvas


def main():
    width, height = 900, 560
    x0, y0, pw, ph = 80, 60, 700, 400
    canvas = Canvas(width, height)
    noises = generate_noises(n=4096)
    spectra = {name: welch_psd(x, nperseg=512)
               for name, x in noises.items()}
    f_min, f_max = 0.008, 0.5
    p_min = min(p for _, psd in spectra.values() for p in psd if p > 0) * 0.5
    p_max = max(p for _, psd in spectra.values() for p in psd) * 2.0

    def lx(f):
        return int(x0 + (math.log10(f) - math.log10(f_min))
                   / (math.log10(f_max) - math.log10(f_min)) * pw)

    def ly(p):
        return int(y0 + ph - (math.log10(p) - math.log10(p_min))
                   / (math.log10(p_max) - math.log10(p_min)) * ph)

    for i in range(5):
        gx, gy = x0 + i * pw // 4, y0 + i * ph // 4
        canvas.line(gx, y0, gx, y0 + ph, (220, 220, 220), 1)
        canvas.line(x0, gy, x0 + pw, gy, (220, 220, 220), 1)
    canvas.line(x0, y0, x0, y0 + ph, (0, 0, 0), 1)
    canvas.line(x0, y0 + ph, x0 + pw, y0 + ph, (0, 0, 0), 1)
    colors = {"white": (31, 119, 180), "pink": (214, 39, 40),
              "brown": (44, 160, 44)}
    for name, (freqs, psd) in spectra.items():
        pts = [(lx(f), ly(p)) for f, p in zip(freqs, psd)
               if f >= f_min and p > 0]
        for (a, b), (c, d) in zip(pts, pts[1:]):
            canvas.line(a, b, c, d, colors[name], 1)
    for i, (name, color) in enumerate(colors.items()):
        canvas.rect(x0 + pw + 20, y0 + 10 + i * 22,
                    x0 + pw + 44, y0 + 24 + i * 22, color)
    canvas.save("artifacts/spectra_preview.png")
    print("wrote artifacts/spectra_preview.png")


if __name__ == "__main__":
    main()
