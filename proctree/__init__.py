"""Pure-stdlib procedural tree (L-system) and mipmap verification toolkit."""

from .plant import LSystemParams, Tree, generate, rewrite
from .texture import (
    build_checker,
    build_mip_chain,
    clamp_coord,
    oblique_render,
    verify_clamp_no_sparkle,
)

__all__ = [
    "LSystemParams",
    "Tree",
    "generate",
    "rewrite",
    "build_checker",
    "build_mip_chain",
    "clamp_coord",
    "oblique_render",
    "verify_clamp_no_sparkle",
]
