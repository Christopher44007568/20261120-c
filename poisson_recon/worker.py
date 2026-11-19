"""One-shot Poisson reconstruction worker.

Open3D's Poisson implementation can accumulate native state across repeated
calls in a long-lived process. The benchmark therefore runs each reconstruction
in a short-lived child process.
"""

from __future__ import annotations

import json
import sys

import numpy as np

from .reconstruct import poisson_reconstruct


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        print("usage: python -m poisson_recon.worker INPUT.npz OUTPUT.npz")
        return 2
    source, destination = argv
    data = np.load(source)
    result = poisson_reconstruct(
        np.asarray(data["points"], dtype=float),
        np.asarray(data["normals"], dtype=float),
        depth=int(data["depth"]),
        scale=float(data["scale"]),
    )
    np.savez(
        destination,
        vertices=result.vertices,
        faces=result.faces,
        backend=np.array(result.backend),
        runtime_s=np.array(result.runtime_s),
        metadata=np.array(json.dumps(result.metadata)),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
