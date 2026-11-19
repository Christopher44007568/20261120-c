"""Skeletal animation compression and sharp-aware mesh subdivision."""

from .animation import Joint, ProceduralAnimation
from .compression import (
    CompressionResult,
    CompressedAnimation,
    compress_animation,
)
from .metrics import evaluate_reconstruction
from .subdivision import Mesh, SubdivisionResult, build_tent_mesh, subdivide_mesh

__all__ = [
    "Joint",
    "ProceduralAnimation",
    "CompressionResult",
    "CompressedAnimation",
    "compress_animation",
    "evaluate_reconstruction",
    "SubdivisionResult",
    "Mesh",
    "build_tent_mesh",
    "subdivide_mesh",
]
