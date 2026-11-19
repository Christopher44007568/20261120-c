"""Procedural walking and terrain-contact analysis."""

from .gait import GaitParams, simulate_scenario, stride_for_slope
from .ik import LegGeometry, LegPose, solve_leg
from .terrain import PlaneTerrain, WaveTerrain, make_terrain

__all__ = [
    "GaitParams",
    "LegGeometry",
    "LegPose",
    "PlaneTerrain",
    "WaveTerrain",
    "make_terrain",
    "simulate_scenario",
    "solve_leg",
    "stride_for_slope",
]
