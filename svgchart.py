"""Minimal dependency-free SVG line chart / scatter helpers."""


def _fmt(v):
    av = abs(v)
    if av != 0 and (av < 1e-4 or av >= 1e5):
        return f"{v:.3e}"
    return f"{v:.4g}"


def line_chart(path, series, x_label, y_label, title,
               width=900, height=520, markers=None, y_min=None, y_max=None):
    """series: list of dicts(name, points=[(x,y)...], color, dash=None)."""
    ml, mr, mt, mb = 78, 200, 54, 64
    pw, ph = width - ml - mr, height - mt - mb
    xs = [p[0] for s in series for p in s["points"]]
    ys = [p[1] for s in series for p in s["points"]]
    x0, x1 = min(xs), max(xs)
    y0 = min(ys) if y_min is None else y_min
    y1 = max(ys) if y_max is None else y_max
    if y0 == y1:
        y0, y1 = y0 - 1e-9, y1 + 1e-9
    pad_y = (y1 - y0) * 0.05
    y0, y1 = y0 + pad_y if y_min is not None else y0 - pad_y, y1 - pad_y if y_max is not None else y1 + pad_y

    def sx(x):
        return ml + (x - x0) / (x1 - x0) * pw

    def sy(y):
        return mt + ph - (y - y0) / (y1 - y0) * ph

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="28" font-size="20" text-anchor="middle" font-weight="bold">{title}</text>',
    ]
    for i in range(6):
        gy = y0 + (y1 - y0) * i / 5
        yy = sy(gy)
        parts.append(f'<line x1="{ml}" y1="{yy:.1f}" x2="{ml+pw}" y2="{yy:.1f}" stroke="#e3e3e3"/>')
        parts.append(f'<text x="{ml-8}" y="{yy+4:.1f}" font-size="12" text-anchor="end" fill="#444">{_fmt(gy)}</text>')
    for i in range(7):
        gx = x0 + (x1 - x0) * i / 6
        xx = sx(gx)
        parts.append(f'<line x1="{xx:.1f}" y1="{mt}" x2="{xx:.1f}" y2="{mt+ph}" stroke="#f0f0f0"/>')
        parts.append(f'<text x="{xx:.1f}" y="{mt+ph+18}" font-size="12" text-anchor="middle" fill="#444">{_fmt(gx)}</text>')
    parts.append(f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#333"/>')
    parts.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#333"/>')
    parts.append(f'<text x="{ml+pw/2}" y="{height-14}" font-size="14" text-anchor="middle">{x_label}</text>')
    parts.append(f'<text x="20" y="{mt+ph/2}" font-size="14" text-anchor="middle" '
                 f'transform="rotate(-90 20 {mt+ph/2})">{y_label}</text>')
    for mx, label, color in markers or []:
        xx = sx(mx)
        parts.append(f'<line x1="{xx:.1f}" y1="{mt}" x2="{xx:.1f}" y2="{mt+ph}" stroke="{color}" '
                     f'stroke-dasharray="6 5" stroke-width="1.4"/>')
        parts.append(f'<text x="{xx+4:.1f}" y="{mt+12}" font-size="11" fill="{color}">{label}</text>')
    for s in series:
        pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in s["points"])
        dash = f' stroke-dasharray="{s["dash"]}"' if s.get("dash") else ""
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{s["color"]}" stroke-width="2.2"{dash}/>')
    ly = mt + 10
    for s in series:
        dash = f' stroke-dasharray="{s["dash"]}"' if s.get("dash") else ""
        parts.append(f'<line x1="{ml+pw+18}" y1="{ly}" x2="{ml+pw+46}" y2="{ly}" stroke="{s["color"]}" stroke-width="2.2"{dash}/>')
        parts.append(f'<text x="{ml+pw+52}" y="{ly+4}" font-size="12.5" fill="#222">{s["name"]}</text>')
        ly += 22
    for mx, label, color in markers or []:
        parts.append(f'<line x1="{ml+pw+18}" y1="{ly}" x2="{ml+pw+46}" y2="{ly}" stroke="{color}" stroke-dasharray="6 5"/>')
        parts.append(f'<text x="{ml+pw+52}" y="{ly+4}" font-size="12.5" fill="#222">{label}</text>')
        ly += 22
    parts.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(parts))


def heatmap(path, cells, width, height, title, cell_px, points=None):
    """cells: dict((cx,cy), density); optional LOD0 points list (x,y)."""
    vmax = max(cells.values()) if cells else 1.0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height+40}" '
        f'viewBox="0 0 {width} {height+40}" font-family="sans-serif">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="26" font-size="18" text-anchor="middle" font-weight="bold">{title}</text>',
    ]
    for (cx, cy), v in cells.items():
        t = min(v / vmax, 1.0)
        r = int(255)
        g = int(255 - 215 * t)
        b = int(255 - 255 * t)
        parts.append(
            f'<rect x="{cx*cell_px}" y="{cy*cell_px+40}" width="{cell_px}" height="{cell_px}" '
            f'fill="rgb({r},{g},{b})" stroke="none"/>')
    for x, y in (points or [])[::7]:
        parts.append(f'<circle cx="{x:.1f}" cy="{y+40:.1f}" r="1.1" fill="#1139ff" opacity="0.55"/>')
    parts.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(parts))
