#!/usr/bin/env python3
"""Generate SVG charts from benchmark CSVs using only the Python stdlib."""
import csv
import os

OUT = "results"
W, H = 760, 460
M = dict(l=78, r=24, t=46, b=62)
COLORS = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def fmt(v):
    v = float(v)
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) >= 10:
        return f"{v:.0f}"
    if abs(v) >= 1:
        return f"{v:.1f}"
    return f"{v:.3f}"


def line_chart(out_path, title, x_key, series, x_label, y_label, log_y=False,
               x_categorical=True):
    """series: list of (label, y_key, rows)."""
    all_rows = series[0][2]
    if x_categorical:
        xs = [r[x_key] for r in all_rows]
        xpos = {v: i for i, v in enumerate(xs)}
    else:
        xs = sorted({float(r[x_key]) for _, _, rows in series for r in rows})
        xpos = {str(v): i for i, v in enumerate(xs)}
    yvals = [float(r[k]) for _, k, rows in series for r in rows if float(r[k]) > 0]
    ymin, ymax = (min(yvals), max(yvals)) if log_y else (0, max(yvals))
    pw, ph = W - M["l"] - M["r"], H - M["t"] - M["b"]

    def X(v):
        i = xpos[str(v)] if str(v) in xpos else xpos[float(v)]
        return M["l"] + (i + 0.5) * pw / len(xs)

    import math
    def Y(v):
        if log_y:
            lo, hi = math.log10(ymin), math.log10(ymax)
            t = (math.log10(max(v, ymin)) - lo) / max(1e-9, hi - lo)
        else:
            t = v / ymax
        return M["t"] + ph * (1 - t)

    e = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="sans-serif">']
    e.append(f'<rect width="{W}" height="{H}" fill="white"/>')
    e.append(f'<text x="{W/2}" y="26" font-size="17" font-weight="bold" '
             f'text-anchor="middle">{title}</text>')
    ticks = 5
    for i in range(ticks + 1):
        yy = M["t"] + ph * i / ticks
        val = ymax * (1 - i / ticks)
        e.append(f'<line x1="{M["l"]}" y1="{yy:.1f}" x2="{W-M["r"]}" y2="{yy:.1f}" '
                 f'stroke="#e5e7eb"/>')
        e.append(f'<text x="{M["l"]-8}" y="{yy+4:.1f}" font-size="11" '
                 f'text-anchor="end" fill="#374151">{fmt(val)}</text>')
    e.append(f'<line x1="{M["l"]}" y1="{M["t"]}" x2="{M["l"]}" '
             f'y2="{M["t"]+ph}" stroke="#374151"/>')
    e.append(f'<line x1="{M["l"]}" y1="{M["t"]+ph}" x2="{W-M["r"]}" '
             f'y2="{M["t"]+ph}" stroke="#374151"/>')
    for v in xs:
        xx = X(str(v) if x_categorical else v)
        e.append(f'<text x="{xx:.1f}" y="{M["t"]+ph+18}" font-size="11" '
                 f'text-anchor="middle" fill="#374151">{v}</text>')
    e.append(f'<text x="{M["l"]+pw/2}" y="{H-12}" font-size="12" '
             f'text-anchor="middle">{x_label}</text>')
    e.append(f'<text transform="translate(20,{M["t"]+ph/2}) rotate(-90)" '
             f'font-size="12" text-anchor="middle">{y_label}</text>')
    for si, (label, yk, rows) in enumerate(series):
        color = COLORS[si % len(COLORS)]
        pts = [(X(r[x_key]), Y(float(r[yk]))) for r in rows]
        line = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        e.append(f'<path d="{line}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in pts:
            e.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{color}"/>')
        lx, ly = W - M["r"] - 8, M["t"] + 16 + si * 18
        e.append(f'<rect x="{lx-150}" y="{ly-10}" width="158" height="15" '
                 f'fill="white" opacity="0.85"/>')
        e.append(f'<line x1="{lx-146}" y1="{ly-2}" x2="{lx-126}" y2="{ly-2}" '
                 f'stroke="{color}" stroke-width="2.5"/>')
        e.append(f'<text x="{lx-120}" y="{ly+2}" font-size="11" fill="#111827">'
                 f'{label}</text>')
    e.append("</svg>")
    with open(out_path, "w") as f:
        f.write("\n".join(e))
    print("wrote", out_path)


def grouped_bar(path, title, group_key, bar_key, val_key, x_label, y_label):
    rows = read_csv(os.path.join(OUT, "matrix_clustered.csv"))
    order = {"small": 0, "medium": 1, "large": 2}
    groups = sorted({r[group_key] for r in rows},
                    key=lambda v: order[v])
    bars = sorted({r[bar_key] for r in rows},
                  key=lambda v: int(v) if v.isdigit() else float(v))
    ymax = max(float(r[val_key]) for r in rows)
    pw, ph = W - M["l"] - M["r"], H - M["t"] - M["b"]
    gw = pw / len(groups)
    bw = gw / (len(bars) + 1)
    e = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="sans-serif">',
         f'<rect width="{W}" height="{H}" fill="white"/>',
         f'<text x="{W/2}" y="26" font-size="17" font-weight="bold" '
         f'text-anchor="middle">{title}</text>']
    for i in range(6):
        yy = M["t"] + ph * i / 5
        e.append(f'<line x1="{M["l"]}" y1="{yy:.1f}" x2="{W-M["r"]}" '
                 f'y2="{yy:.1f}" stroke="#e5e7eb"/>')
        e.append(f'<text x="{M["l"]-8}" y="{yy+4:.1f}" font-size="11" '
                 f'text-anchor="end">{fmt(ymax*(1-i/5))}</text>')
    for gi, g in enumerate(groups):
        gx = M["l"] + gi * gw
        for bi, b in enumerate(bars):
            match = next(r for r in rows
                         if r[group_key] == g and r[bar_key] == b)
            v = float(match[val_key])
            h = ph * v / ymax
            x = gx + bw * (bi + 0.5)
            e.append(f'<rect x="{x:.1f}" y="{M["t"]+ph-h:.1f}" '
                     f'width="{bw*0.9:.1f}" height="{h:.1f}" '
                     f'fill="{COLORS[bi % len(COLORS)]}"/>')
        e.append(f'<text x="{gx+gw/2:.1f}" y="{M["t"]+ph+18}" font-size="12" '
                 f'text-anchor="middle">{g}</text>')
    e.append(f'<text x="{M["l"]+pw/2}" y="{H-12}" font-size="12" '
             f'text-anchor="middle">{x_label}</text>')
    e.append(f'<text transform="translate(20,{M["t"]+ph/2}) rotate(-90)" '
             f'font-size="12" text-anchor="middle">{y_label}</text>')
    for bi, b in enumerate(bars):
        lx = M["l"] + bi * 108
        e.append(f'<rect x="{lx}" y="{H-34}" width="13" height="13" '
                 f'fill="{COLORS[bi % len(COLORS)]}"/>')
        e.append(f'<text x="{lx+18}" y="{H-23}" font-size="11">tile {b}px</text>')
    e.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(e))
    print("wrote", path)


def main():
    sweeps = {s: read_csv(f"{OUT}/sweep_{s}.csv")
              for s in ("clustered", "uniform", "large", "offscreen")}
    line_chart(f"{OUT}/chart_time.svg",
               "Tiled vs immediate: total time by tile size (100k triangles)",
               "tile",
               [(f"{s} tiled", "totalTime", sweeps[s]) for s in sweeps] +
               [("immediate (all)", "immTime", sweeps["clustered"])],
               "tile size (px)", "modeled time (s)")
    line_chart(f"{OUT}/chart_bandwidth.svg",
               "External-memory traffic by tile size",
               "tile",
               [(f"{s} tiled", "bwMB", sweeps[s]) for s in sweeps] +
               [("immediate (clustered)", "immBWMB", sweeps["clustered"])],
               "tile size (px)", "traffic (MB / frame)")
    line_chart(f"{OUT}/chart_cull.svg",
               "Hierarchical cull rate by tile size",
               "tile",
               [(s, "cullPct", sweeps[s]) for s in sweeps],
               "tile size (px)", "rejected tile tests (%)")
    scaling = read_csv(f"{OUT}/scaling.csv")
    line_chart(f"{OUT}/chart_scaling.svg",
               "Culling benefit vs scene scale (tile=32, clustered)",
               "tris",
               [("tiled time", "totalTime", scaling),
                ("immediate time", "immTime", scaling)],
               "triangles", "modeled time (s)", x_categorical=True)
    grouped_bar(f"{OUT}/chart_matrix_time.svg",
                "Tile size x triangle size: modeled time",
                "triangleClass", "tile", "totalTime",
                "triangle size class", "modeled time (s)")
    grouped_bar(f"{OUT}/chart_matrix_submit.svg",
                "Tile size x triangle size: submissions per triangle",
                "triangleClass", "tile", "submissionsPerTri",
                "triangle size class", "submissions / triangle")


if __name__ == "__main__":
    main()
