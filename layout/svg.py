"""Tiny hand-rolled SVG helpers (no external plotting libraries)."""


class Svg:
    def __init__(self, width, height, title=""):
        self.width = width
        self.height = height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" '
            f'font-family="Helvetica,Arial,sans-serif">',
            '<rect width="100%" height="100%" fill="white"/>',
        ]
        if title:
            self.parts.append(
                f'<text x="{width / 2}" y="22" font-size="16" '
                f'font-weight="bold" text-anchor="middle">{title}</text>')

    def line(self, x1, y1, x2, y2, color="black", width=1.0, dash=None):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
            f'y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"'
            f'{dash_attr}/>')

    def rect(self, x, y, w, h, fill, stroke="none", opacity=1.0):
        self.parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
            f'height="{h:.1f}" fill="{fill}" stroke="{stroke}" '
            f'opacity="{opacity}"/>')

    def circle(self, cx, cy, r, fill, stroke="none"):
        self.parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
            f'fill="{fill}" stroke="{stroke}"/>')

    def text(self, x, y, content, size=10, color="black", anchor="start",
             bold=False):
        weight = ' font-weight="bold"' if bold else ""
        self.parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
            f'fill="{color}" text-anchor="{anchor}"{weight}>'
            f'{content}</text>')

    def polyline(self, points, color, width=1.2):
        joined = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        self.parts.append(
            f'<polyline points="{joined}" fill="none" stroke="{color}" '
            f'stroke-width="{width}"/>')

    def legend(self, x, y, entries):
        for i, (label, color) in enumerate(entries):
            yy = y + i * 16
            self.line(x, yy, x + 22, yy, color, 2.0)
            self.text(x + 27, yy + 4, label, 10)

    def save(self, path):
        self.parts.append("</svg>")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.parts))
