"""Entry point: run routing, via checks, sweeps and spectra; emit reports."""

import csv
import json
import os

from .noise import (HIGH_FREQ_SLOPES, generate_noises,
                    high_frequency_artifacts, spectral_slope, welch_psd)
from .router import Router
from .scenario import build_demo_board
from .sweep import aggregate, run_sweep
from .viz import render_board, render_density_chart, render_spectra


def run(output_dir="artifacts"):
    os.makedirs(output_dir, exist_ok=True)
    routing_report = _run_routing(output_dir)
    sweep_report = _run_sweep(output_dir)
    noise_report = _run_noise(output_dir)
    report = {
        "routing": routing_report,
        "density_sweep": sweep_report,
        "noise_spectra": noise_report,
    }
    with open(os.path.join(output_dir, "report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return report


def _run_sweep(output_dir):
    rows = run_sweep()
    summary = aggregate(rows)
    csv_path = os.path.join(output_dir, "density_sweep.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    render_density_chart(summary,
                         os.path.join(output_dir, "density.svg"))
    with open(os.path.join(output_dir, "density_summary.json"), "w",
              encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    effects = _parameter_effects(summary)
    return {"row_count": len(rows), "effects": effects,
            "summary_head": summary[:6]}


def _parameter_effects(summary):
    def mean_where(mask):
        items = [g for g in summary if mask(g)]
        return sum(g["mean_cell_density"] for g in items) / len(items)
    base = {"width": 24, "obstacle_ratio": 0.15, "net_count": 8}
    low_density = mean_where(
        lambda g: g["obstacle_ratio"] == 0.05
        and g["width"] == base["width"] and g["net_count"] == base["net_count"])
    high_density = mean_where(
        lambda g: g["obstacle_ratio"] == 0.25
        and g["width"] == base["width"] and g["net_count"] == base["net_count"])
    few_nets = mean_where(
        lambda g: g["net_count"] == 4 and g["width"] == base["width"]
        and g["obstacle_ratio"] == base["obstacle_ratio"])
    many_nets = mean_where(
        lambda g: g["net_count"] == 12 and g["width"] == base["width"]
        and g["obstacle_ratio"] == base["obstacle_ratio"])
    small_grid = mean_where(
        lambda g: g["width"] == 16
        and g["obstacle_ratio"] == base["obstacle_ratio"]
        and g["net_count"] == base["net_count"])
    big_grid = mean_where(
        lambda g: g["width"] == 24
        and g["obstacle_ratio"] == base["obstacle_ratio"]
        and g["net_count"] == base["net_count"])
    return {
        "obstacle_ratio_5_to_25_density_change": round(
            high_density - low_density, 4),
        "net_count_4_to_12_density_change": round(
            many_nets - few_nets, 4),
        "grid_16_to_24_density_change": round(
            big_grid - small_grid, 4),
        "mean_crossings_overall": round(
            sum(g["mean_crossings"] for g in summary) / len(summary), 3),
        "routed_fraction_overall": round(
            sum(g["routed_fraction"] for g in summary) / len(summary), 3),
    }


def _run_noise(output_dir):
    noises = generate_noises(n=4096, seed=20261120)
    spectra = {}
    checks = {}
    for name, samples in noises.items():
        freqs, psd = welch_psd(samples, nperseg=512)
        spectra[name] = (freqs, psd)
        artifacts = high_frequency_artifacts(freqs, psd)
        checks[name] = {
            "measured_slope_0.02_0.45": round(spectral_slope(freqs, psd), 3),
            "measured_slope_low_band_0.02_0.12": round(
                spectral_slope(freqs, psd, 0.02, 0.12), 3),
            "theoretical_slope": HIGH_FREQ_SLOPES[name],
            "top_band_to_mid_band_energy_ratio": round(
                artifacts["ratio"], 3),
            "no_high_frequency_surge": not artifacts["artifact_detected"],
            "surge_threshold": artifacts["surge_threshold"],
            "unit_variance": round(
                sum(v * v for v in samples) / len(samples), 4),
        }
    render_spectra(spectra, os.path.join(output_dir, "spectra.svg"))
    return {"sample_count": 4096, "nperseg": 512, "window": "Hann",
            "checks": checks}


def _run_routing(output_dir):
    board, pins = build_demo_board()
    result = Router(board, pins, rip_up_passes=3).route()
    render_board(board, pins, result,
                 os.path.join(output_dir, "routing.svg"))
    net_report = {}
    for net, path in result.nets.items():
        via_layers = [
            {"cell": list(cell), "from_layer": lo, "to_layer": hi}
            for n, cell, lo, hi in result.vias if n == net]
        net_report[net] = {
            "states": len(path),
            "planar_length": sum(
                1 for a, b in zip(path, path[1:]) if a[0] == b[0]),
            "vias": via_layers,
        }
    report = {
        "routed": result.routed,
        "planar_length": result.planar_length,
        "via_count": result.via_count,
        "total_weighted_length": result.total_length,
        "crossings": result.crossings,
        "crossing_events": [_serialize_event(event)
                            for event in result.crossing_events],
        "via_validation": {
            "passed": not result.via_errors,
            "errors": result.via_errors,
            "vias": [
                {"net": n, "cell": list(cell), "from_layer": lo,
                 "to_layer": hi}
                for n, cell, lo, hi in result.vias],
        },
        "nets": net_report,
    }
    return report


def _serialize_event(event):
    kind = event[0]
    if kind == "cell":
        _, layer, cell, owners = event
        return {"kind": "cell", "layer": layer, "cell": list(cell),
                "nets": owners}
    _, edge, owners = event
    return {"kind": "edge", "edge": str(edge), "nets": owners}
