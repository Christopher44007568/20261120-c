"""Heatmaps for the parameter sweep (artifacts/param_sweep.csv)."""
from __future__ import annotations

import csv
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "artifacts")


def load():
    with open(os.path.join(ART, "param_sweep.csv")) as f:
        return list(csv.DictReader(f))


def grid(rows, key, col_key, row_key, col_val=None):
    cols = sorted({float(r[col_key]) for r in rows})
    idx = sorted({int(r[row_key]) for r in rows})
    g = np.full((len(idx), len(cols)), np.nan)
    for r in rows:
        i = idx.index(int(r[row_key]))
        j = cols.index(float(r[col_key]))
        g[i, j] = float(r[key])
    return idx, cols, g


def main():
    rows = load()
    bend_rows = [r for r in rows if float(r["k_stretch"]) == 1.0]
    stretch_rows = [r for r in rows if abs(float(r["k_bend"]) - 0.1) < 1e-9]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    panels = [
        (bend_rows, "k_bend", "max_stretch_err", "max stretch err (k_stretch=1)"),
        (bend_rows, "k_bend", "hem_wrinkles", "hem wrinkle count"),
        (bend_rows, "k_bend", "skirt_radius_max", "skirt radius [m]"),
        (stretch_rows, "k_stretch", "max_stretch_err", "max stretch err (k_bend=0.1)"),
        (stretch_rows, "k_stretch", "hem_wrinkles", "hem wrinkle count"),
        (stretch_rows, "k_stretch", "skirt_radius_max", "skirt radius [m]"),
    ]
    for ax, (sub, ck, key, title) in zip(axes.flat, panels):
        idx, cols, g = grid(sub, key, ck, "iterations")
        im = ax.imshow(g, aspect="auto", origin="lower", cmap="viridis")
        ax.set_xticks(range(len(cols)), [f"{c:g}" for c in cols])
        ax.set_yticks(range(len(idx)), idx)
        ax.set_xlabel(ck)
        ax.set_ylabel("iterations")
        ax.set_title(title)
        for i in range(g.shape[0]):
            for j in range(g.shape[1]):
                ax.text(j, i, f"{g[i, j]:.2f}", ha="center", va="center",
                        color="w", fontsize=8)
        fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(os.path.join(ART, "param_sweep.png"), dpi=140)
    print("saved param_sweep.png")


if __name__ == "__main__":
    main()
