"""Connected-component and percolation analysis of cave air masks."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

_STRUCT6 = ndimage.generate_binary_structure(3, 1)  # 6-connectivity


@dataclass
class Connectivity:
    n_components: int
    largest_size: int
    largest_ratio: float      # largest component / all air voxels
    percolates_z: bool        # one component touches both z=0 and z=max


def label_components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    labels, n = ndimage.label(mask, structure=_STRUCT6)
    return labels, int(n)


def analyze(mask: np.ndarray) -> Connectivity:
    labels, n = label_components(mask)
    if n == 0:
        return Connectivity(0, 0, 0.0, False)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    largest = int(sizes.max())
    top = np.unique(labels[:, :, 0])
    bottom = np.unique(labels[:, :, -1])
    shared = set(top[top > 0]) & set(bottom[bottom > 0])
    return Connectivity(
        n_components=n,
        largest_size=largest,
        largest_ratio=largest / int(mask.sum()),
        percolates_z=bool(shared),
    )


def layer_channel_report(mask: np.ndarray, n_layers: int) -> dict:
    """Check channel connectivity across stacked horizontal layers."""
    nz = mask.shape[2]
    bounds = np.linspace(0, nz, n_layers + 1).astype(int)
    labels, _ = label_components(mask)
    layers = []
    for i in range(n_layers):
        slab = mask[:, :, bounds[i]:bounds[i + 1]]
        _, n = label_components(slab)
        layers.append({"layer": i, "air_voxels": int(slab.sum()),
                       "components": int(n)})
    crossings = []
    for i in range(n_layers - 1):
        boundary = bounds[i + 1] - 1
        above = set(np.unique(labels[:, :, boundary])) - {0}
        below = set(np.unique(labels[:, :, boundary + 1])) - {0}
        crossings.append({
            "interface": f"L{i}-L{i+1}",
            "connected": bool(above & below),
            "shared_components": len(above & below),
        })
    main = analyze(mask)
    return {"layers": layers, "crossings": crossings,
            "top_to_bottom": main.percolates_z,
            "largest_ratio": main.largest_ratio}
