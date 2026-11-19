#!/usr/bin/env python3
"""Independent watertightness check for an exported voxel-boundary OBJ.

Quantizes triangle vertices back to lattice coordinates, rebuilds the set of
occupied voxel cells, and applies the cubical-complex fan test: around every
interior lattice edge the four surrounding cells must show an even number of
empty<->occupied transitions (0, 2, or 4). Odd counts are cracks; anything
else is non-manifold/self-intersecting geometry. This mirrors the C++ check
but is implemented independently from the OBJ mesh.
"""
import collections
import sys


def check(path):
    verts = {}
    faces = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                verts[len(verts) + 1] = tuple(round(float(x), 6)
                                              for x in line.split()[1:4])
            elif line.startswith("f "):
                faces.append(tuple(int(tok) for tok in line.split()[1:]))

    # Recover voxel size as the smallest non-zero coordinate gap.
    coords = sorted({c for v in verts.values() for c in v})
    gaps = [b - a for a, b in zip(coords, coords[1:]) if b - a > 1e-9]
    h = min(gaps)
    origin = coords[0]

    def cell_key(p):
        return tuple(int(round((q - origin) / h)) for q in p)

    occupied = set()
    for tri in faces:
        cs = [cell_key(verts[i]) for i in tri]
        # Each triangle corner is a lattice vertex; the owning voxel is the
        # cell in the negative direction along the face normal axis. Taking
        # the minimum coordinate corner recovers one voxel of that face.
        mn = tuple(min(c[d] for c in cs) for d in range(3))
        occupied.add(mn)

    def occ(x, y, z):
        return (x, y, z) in occupied

    lattice = [c for cell in occupied for c in
               [(cell[0] + dx, cell[1] + dy, cell[2] + dz)
                for dx in (0, 1) for dy in (0, 1) for dz in (0, 1)]]
    xs = sorted({p[0] for p in lattice})
    ys = sorted({p[1] for p in lattice})
    zs = sorted({p[2] for p in lattice})
    lo = (min(xs), min(ys), min(zs))
    hi = (max(xs), max(ys), max(zs))

    open_edges = 0
    non_manifold = 0

    def transitions(ring):
        t = sum(1 for i in range(4) if ring[i] != ring[(i + 1) % 4])
        return t

    for ex in range(lo[0] + 1, hi[0]):
        for ey in range(lo[1] + 1, hi[1]):
            for ez in range(lo[2] + 1, hi[2]):
                rings = (
                    [occ(ex, ey - 1, ez - 1), occ(ex, ey, ez - 1),
                     occ(ex, ey, ez), occ(ex, ey - 1, ez)],          # x edge
                    [occ(ex - 1, ey, ez - 1), occ(ex, ey, ez - 1),
                     occ(ex, ey, ez), occ(ex - 1, ey, ez)],          # y edge
                    [occ(ex - 1, ey - 1, ez), occ(ex, ey - 1, ez),
                     occ(ex, ey, ez), occ(ex - 1, ey, ez)],          # z edge
                )
                for t in rings:
                    tr = transitions(t)
                    if tr % 2 == 1:
                        open_edges += 1
                    if tr not in (0, 2, 4):
                        non_manifold += 1

    watertight = open_edges == 0 and non_manifold == 0
    print(f"{path}: voxels={len(occupied)} open_lattice_edges={open_edges} "
          f"non_manifold={non_manifold} watertight={'YES' if watertight else 'NO'}")
    return watertight


if __name__ == "__main__":
    ok = all(check(p) for p in sys.argv[1:])
    sys.exit(0 if ok else 1)
