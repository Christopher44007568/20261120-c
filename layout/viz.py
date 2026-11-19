"""Render routed boards and log-log spectra as standalone SVG files."""

import math

from .svg import Svg

NET_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd",
              "#ff7f0e", "#17becf", "#8c564b", "#e377c2",
              "#bcbd22", "#7f7f7f", "#393b79", "#637939"]
LAYER_TINTS = ["#eef4fb", "#fbf3ee"]


def render_board(board, pins, result, path):
    cell = 34
    gap = 24
    panel_w = board.width * cell
    panel_h = board.height * cell
    width = board.layers * panel_w + (board.layers + 1) * gap
    height = panel_h + gap * 2 + 34
    svg = Svg(width, height, "Orthogonal routing per layer")
    net_color = {net: NET_COLORS[i % len(NET_COLORS)]
                 for i, net in enumerate(sorted(result.nets))}
    for layer in range(board.layers):
        ox = gap + layer * (panel_w + gap)
        svg.rect(ox, gap, panel_w, panel_h,
                 LAYER_TINTS[layer % len(LAYER_TINTS)], "#888")
        for obs in board.obstacles:
            if obs.layer != layer:
                continue
            svg.rect(ox + obs.x0 * cell, gap + obs.y0 * cell,
                     (obs.x1 - obs.x0) * cell,
                     (obs.y1 - obs.y0) * cell,
                     "#444", "#222")
        _draw_paths(svg, result, layer, ox, gap, cell, net_color)
        _draw_vias(svg, result, layer, ox, gap, cell)
        _draw_pins(svg, pins, layer, ox, gap, cell, net_color)
        svg.text(ox + panel_w / 2, gap + panel_h + 22,
                 f"Layer {layer}", 13, anchor="middle", bold=True)
    svg.legend(gap, height - 12,
               [(net, net_color[net]) for net in sorted(net_color)])
    svg.save(path)


def _center(ox, oy, cell, layer_cell):
    x, y = layer_cell
    return ox + (x + 0.5) * cell, oy + (y + 0.5) * cell


def _draw_paths(svg, result, layer, ox, oy, cell, net_color):
    for net, path in result.nets.items():
        color = net_color[net]
        pts = [_center(ox, oy, cell, state[1])
               for state in path if state[0] == layer]
        for a, b in zip(pts, pts[1:]):
            svg.line(a[0], a[1], b[0], b[1], color, 3.0)


def _draw_vias(svg, result, layer, ox, oy, cell):
    for net, via_cell, lo, hi in result.vias:
        if lo <= layer <= hi:
            cx, cy = _center(ox, oy, cell, via_cell)
            svg.circle(cx, cy, 7, "white", "#111")
            svg.circle(cx, cy, 3, "#111")


def _draw_pins(svg, pins, layer, ox, oy, cell, net_color):
    for pin in pins:
        if pin.layer != layer:
            continue
        cx, cy = _center(ox, oy, cell, pin.cell)
        svg.circle(cx, cy, 6, net_color[pin.net], "black")


def render_spectra(spectra, path):
    """spectra: {name: (freqs, psd)}; log-log plot with slope reference."""
    width, height = 820, 520
    plot = (70, 50, width - 130, height - 110)
    x0, y0, pw, ph = plot
    f_min, f_max = 0.008, 0.5
    p_min = min(p for _, psd in spectra.values() for p in psd
                if p > 0) * 0.5
    p_max = max(p for _, psd in spectra.values() for p in psd) * 2.0
    lx = lambda f: x0 + (math.log10(f) - math.log10(f_min)) / (
        math.log10(f_max) - math.log10(f_min)) * pw
    ly = lambda p: y0 + ph - (math.log10(p) - math.log10(p_min)) / (
        math.log10(p_max) - math.log10(p_min)) * ph
    svg = Svg(width, height, "Welch PSD of white / pink / brown noise")
    for i in range(5):
        gx = x0 + i * pw / 4
        gy = y0 + i * ph / 4
        svg.line(gx, y0, gx, y0 + ph, "#ddd", 0.8)
        svg.line(x0, gy, x0 + pw, gy, "#ddd", 0.8)
    svg.line(x0, y0, x0, y0 + ph, "black", 1.2)
    svg.line(x0, y0 + ph, x0 + pw, y0 + ph, "black", 1.2)
    svg.text(x0 + pw / 2, height - 40, "normalized frequency f/fs (log)",
             12, anchor="middle")
    svg.text(18, y0 + ph / 2, "PSD (log)", 12, anchor="middle")
    colors = {"white": "#1f77b4", "pink": "#d62728", "brown": "#2ca02c"}
    for name, (freqs, psd) in spectra.items():
        pts = [(lx(f), ly(p)) for f, p in zip(freqs, psd)
               if f >= f_min and p > 0]
        svg.polyline(pts, colors[name], 2.0)
    _slope_guides(svg, lx, ly, f_min)
    entries = [(n, colors[n]) for n in spectra] + [
        ("slope guides 0, -1, -2", "#888")]
    svg.legend(x0 + pw + 14, y0 + 8, entries)
    svg.text(x0, y0 - 14,
             "all signals: same seed/params, unit variance, Hann 512",
             10, "#555")
    svg.save(path)


def _slope_guides(svg, lx, ly, f_min):
    for slope in (0.0, -1.0, -2.0):
        anchor_f, anchor_p = 0.05, 1.0
        pts = []
        for i in range(40):
            f = anchor_f * 10 ** (i / 40 * 0.9)
            if f > 0.45:
                break
            p = anchor_p * (f / anchor_f) ** slope
            pts.append((lx(f), ly(p)))
        for a, b in zip(pts, pts[1:]):
            svg.line(a[0], a[1], b[0], b[1], "#bbb", 1.0, "4,4")


def render_density_chart(summary, path):
    width, height = 860, 480
    x0, y0, pw, ph = 70, 50, width - 110, height - 130
    svg = Svg(width, height,
              "Layout parameters vs routed-cell density and crossings")
    groups = summary
    max_density = max(g["mean_cell_density"] for g in groups) or 1.0
    max_cross = max(g["mean_crossings"] for g in groups) or 1.0
    group_w = pw / len(groups)
    bar_w = group_w * 0.32
    base = y0 + ph
    svg.line(x0, base, x0 + pw, base, "black", 1.2)
    svg.line(x0, y0, x0, base, "black", 1.2)
    for i, g in enumerate(groups):
        gx = x0 + i * group_w + group_w * 0.18
        h1 = ph * g["mean_cell_density"] / max_density
        h2 = ph * g["mean_crossings"] / max_cross
        svg.rect(gx, base - h1, bar_w, h1, "#1f77b4")
        svg.rect(gx + bar_w + 4, base - h2, bar_w, h2, "#d62728")
        label = f'{g["width"]}|{g["obstacle_ratio"]:.2f}|{g["net_count"]}'
        svg.text(gx + bar_w, base + 14, label, 7.5, anchor="middle")
    svg.text(x0 + pw / 2, height - 55,
             "group label: grid | obstacle ratio | net count", 10,
             anchor="middle", color="#555")
    svg.text(18, y0 + ph / 2, "normalized metric", 11, anchor="middle")
    svg.legend(x0 + pw - 250, y0 - 24,
               [("mean cell density", "#1f77b4"),
                ("mean crossings", "#d62728")])
    svg.save(path)
