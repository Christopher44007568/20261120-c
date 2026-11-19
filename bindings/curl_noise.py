#!/usr/bin/env python3
"""ctypes binding for the curl-noise C ABI."""

from __future__ import annotations

import argparse
import ctypes as ct
import json
import os
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = Path(
    os.environ.get("CURLNOISE_LIB", ROOT / "build" / "libcurlnoise.so")
).resolve()


class Vec2(ct.Structure):
    _fields_ = [("x", ct.c_float), ("y", ct.c_float)]


class FlowParams(ct.Structure):
    _fields_ = [
        ("version", ct.c_uint32),
        ("seed", ct.c_uint32),
        ("octaves", ct.c_uint32),
        ("modes_per_octave", ct.c_uint32),
        ("frequency", ct.c_float),
        ("lacunarity", ct.c_float),
        ("gain", ct.c_float),
        ("speed", ct.c_float),
        ("box_size", ct.c_float),
    ]


class ExperimentConfig(ct.Structure):
    _fields_ = [
        ("version", ct.c_uint32),
        ("seed", ct.c_uint32),
        ("particle_count", ct.c_uint32),
        ("steps", ct.c_uint32),
        ("trace_count", ct.c_uint32),
        ("trace_every", ct.c_uint32),
        ("frequency", ct.c_float),
        ("lacunarity", ct.c_float),
        ("gain", ct.c_float),
        ("speed", ct.c_float),
        ("dt", ct.c_float),
        ("box_size", ct.c_float),
        ("jitter", ct.c_float),
    ]


class Particle(ct.Structure):
    _fields_ = [
        ("id", ct.c_uint32),
        ("flags", ct.c_uint32),
        ("x", ct.c_float),
        ("y", ct.c_float),
        ("vx", ct.c_float),
        ("vy", ct.c_float),
        ("age", ct.c_float),
    ]


class FieldSample(ct.Structure):
    _fields_ = [
        ("x", ct.c_float),
        ("y", ct.c_float),
        ("vx", ct.c_float),
        ("vy", ct.c_float),
        ("potential", ct.c_float),
        ("divergence", ct.c_float),
        ("speed", ct.c_float),
    ]


class TrajectorySample(ct.Structure):
    _fields_ = [
        ("particle_id", ct.c_uint32),
        ("step", ct.c_uint32),
        ("time", ct.c_float),
        ("x", ct.c_float),
        ("y", ct.c_float),
        ("vx", ct.c_float),
        ("vy", ct.c_float),
        ("speed", ct.c_float),
        ("curvature", ct.c_float),
    ]


class Layout(ct.Structure):
    _fields_ = [
        ("version", ct.c_uint32),
        ("pointer_size", ct.c_uint32),
        ("flow_params_size", ct.c_uint32),
        ("flow_params_align", ct.c_uint32),
        ("experiment_size", ct.c_uint32),
        ("experiment_align", ct.c_uint32),
        ("particle_size", ct.c_uint32),
        ("particle_align", ct.c_uint32),
        ("field_sample_size", ct.c_uint32),
        ("field_sample_align", ct.c_uint32),
        ("trajectory_sample_size", ct.c_uint32),
        ("trajectory_sample_align", ct.c_uint32),
        ("vec2_size", ct.c_uint32),
        ("vec2_align", ct.c_uint32),
        ("particle_stride", ct.c_uint32),
        ("field_sample_stride", ct.c_uint32),
        ("trajectory_sample_stride", ct.c_uint32),
        ("array_rank", ct.c_uint32),
        ("array_order", ct.c_uint32),
        ("struct_count", ct.c_uint32),
        ("scalar_bits", ct.c_uint32),
        ("little_endian", ct.c_uint32),
        ("ieee754_float", ct.c_uint32),
        ("reserved", ct.c_uint32),
    ]


STRUCT_TYPES = {
    "CNVec2": Vec2,
    "CNFlowParams": FlowParams,
    "CNExperimentConfig": ExperimentConfig,
    "CNParticle": Particle,
    "CNFieldSample": FieldSample,
    "CNTrajectorySample": TrajectorySample,
}


def _field_offsets(structure: type[ct.Structure]) -> dict[str, int]:
    return {name: getattr(structure, name).offset for name, _ in structure._fields_}


def layout_descriptor() -> dict:
    """Describe the ctypes-side memory layout using the canonical JSON schema."""
    structs = {}
    for name, structure in STRUCT_TYPES.items():
        structs[name] = {
            "size": ct.sizeof(structure),
            "align": ct.alignment(structure),
            "fields": _field_offsets(structure),
        }
    return {
        "schema": "curl-noise-abi",
        "abi_version": 1,
        "pointer_size": ct.sizeof(ct.c_void_p),
        "scalar_bits": ct.sizeof(ct.c_float) * 8,
        "little_endian": 1 if sys.byteorder == "little" else 0,
        "ieee754_float": 1 if struct.calcsize("f") == 4 else 0,
        "structs": structs,
        "arrays": {
            "particles": {
                "element": "CNParticle",
                "stride": ct.sizeof(Particle),
                "rank": 1,
                "order": "c_contiguous",
                "index": "i",
            },
            "flow_samples": {
                "element": "CNFieldSample",
                "stride": ct.sizeof(FieldSample),
                "rank": 2,
                "order": "c_contiguous",
                "index": "row * cols + col",
            },
            "trajectory_samples": {
                "element": "CNTrajectorySample",
                "stride": ct.sizeof(TrajectorySample),
                "rank": 2,
                "order": "c_contiguous",
                "index": "trace * samples_per_trace + sample",
            },
        },
    }


class CurlNoise:
    def __init__(self, library: str | Path = LIB_PATH):
        self.path = Path(library)
        if not self.path.exists():
            raise FileNotFoundError(f"missing shared library: {self.path}")
        self.lib = ct.CDLL(str(self.path))
        self._configure()

    def _configure(self) -> None:
        lib = self.lib
        lib.cn_flow_params_default.restype = FlowParams
        lib.cn_experiment_config_default.restype = ExperimentConfig
        lib.cn_abi_layout.restype = Layout
        lib.cn_write_abi_json.argtypes = [ct.c_char_p]
        lib.cn_write_abi_json.restype = ct.c_int
        lib.cn_field_create.argtypes = [ct.POINTER(FlowParams)]
        lib.cn_field_create.restype = ct.c_void_p
        lib.cn_field_destroy.argtypes = [ct.c_void_p]
        lib.cn_field_destroy.restype = None
        lib.cn_field_mode_count.argtypes = [ct.c_void_p]
        lib.cn_field_mode_count.restype = ct.c_uint32
        lib.cn_field_velocity.argtypes = [ct.c_void_p, Vec2]
        lib.cn_field_velocity.restype = Vec2
        lib.cn_field_velocity_d.argtypes = [
            ct.c_void_p,
            ct.c_double,
            ct.c_double,
            ct.POINTER(ct.c_double),
            ct.POINTER(ct.c_double),
        ]
        lib.cn_field_velocity_d.restype = None
        lib.cn_field_divergence_d.argtypes = [
            ct.c_void_p,
            ct.c_double,
            ct.c_double,
            ct.c_double,
        ]
        lib.cn_field_divergence_d.restype = ct.c_double
        lib.cn_particles_init.argtypes = [
            ct.POINTER(Particle),
            ct.c_uint32,
            ct.c_float,
            ct.c_uint32,
            ct.c_float,
        ]
        lib.cn_particles_init.restype = None
        lib.cn_particle_advect.argtypes = [
            ct.c_void_p,
            ct.POINTER(Particle),
            ct.c_uint32,
            ct.c_float,
            ct.c_uint32,
        ]
        lib.cn_particle_advect.restype = None

    def runtime_layout(self) -> Layout:
        return self.lib.cn_abi_layout()

    def default_params(self) -> FlowParams:
        return self.lib.cn_flow_params_default()

    def field(self, params: FlowParams | None = None) -> "_Field":
        source = params if params is not None else self.default_params()
        pointer = self.lib.cn_field_create(ct.byref(source))
        if not pointer:
            raise MemoryError("cn_field_create returned NULL")
        return _Field(self, pointer)

    def velocity(self, field: "_Field", x: float, y: float) -> tuple[float, float]:
        vx = ct.c_double()
        vy = ct.c_double()
        self.lib.cn_field_velocity_d(
            field.pointer, float(x), float(y), ct.byref(vx), ct.byref(vy)
        )
        return vx.value, vy.value

    def divergence(self, field: "_Field", x: float, y: float, h: float) -> float:
        return float(
            self.lib.cn_field_divergence_d(field.pointer, float(x), float(y), h)
        )


class _Field:
    def __init__(self, owner: CurlNoise, pointer: int):
        self.owner = owner
        self.pointer = pointer
        self._closed = False

    def close(self) -> None:
        if not self._closed:
            self.owner.lib.cn_field_destroy(self.pointer)
            self._closed = True

    def __enter__(self) -> "_Field":
        return self

    def __exit__(self, *_args) -> None:
        self.close()


def verify_layout(c_layout_path: str | Path, library: str | Path = LIB_PATH) -> dict:
    expected = layout_descriptor()
    with open(c_layout_path, "r", encoding="utf-8") as handle:
        actual = json.load(handle)
    if actual != expected:
        for section in ("structs", "arrays"):
            if actual.get(section) != expected.get(section):
                raise AssertionError(
                    f"{section} mismatch:\nC={actual.get(section)}\n"
                    f"Python={expected.get(section)}"
                )
        raise AssertionError("C and Python ABI descriptors differ")
    binding = CurlNoise(library)
    runtime = binding.runtime_layout()
    checks = {
        "flow_params_size": (runtime.flow_params_size, ct.sizeof(FlowParams)),
        "experiment_size": (runtime.experiment_size, ct.sizeof(ExperimentConfig)),
        "particle_size": (runtime.particle_size, ct.sizeof(Particle)),
        "field_sample_size": (runtime.field_sample_size, ct.sizeof(FieldSample)),
        "trajectory_sample_size": (
            runtime.trajectory_sample_size,
            ct.sizeof(TrajectorySample),
        ),
        "particle_stride": (runtime.particle_stride, ct.sizeof(Particle)),
        "field_sample_stride": (runtime.field_sample_stride, ct.sizeof(FieldSample)),
        "trajectory_sample_stride": (
            runtime.trajectory_sample_stride,
            ct.sizeof(TrajectorySample),
        ),
    }
    for name, (c_value, py_value) in checks.items():
        if c_value != py_value:
            raise AssertionError(f"{name}: C={c_value}, Python={py_value}")
    return expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", default=str(LIB_PATH))
    parser.add_argument("--layout-json", help="write Python ctypes layout JSON")
    parser.add_argument("--verify-c", help="compare a C layout JSON with ctypes")
    args = parser.parse_args(argv)
    if args.layout_json:
        destination = Path(args.layout_json)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(layout_descriptor(), indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote ctypes ABI layout: {destination}")
    if args.verify_c:
        descriptor = verify_layout(args.verify_c, args.library)
        print(
            "ABI layout matches: "
            f"{len(descriptor['structs'])} structs, "
            f"{len(descriptor['arrays'])} arrays"
        )
    if not args.layout_json and not args.verify_c:
        print(json.dumps(layout_descriptor(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
