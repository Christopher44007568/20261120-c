"""Tiny dependency-free SVG plotting helpers (2D lines, points, bars)."""


class SvgCanvas:
    def __init__(self, width=720, height=480, margin=56):
        self.w = width
        self.h = height
        self.m = margin
        self.items = []
        self.xlim = (0.0, 1.0)
        self.ylim = (0.0, 1.0)
        self.xlabel = ""
        self.ylabel = ""
        self.title = ""

    def set_limits(self, xlim, ylim):
        self.xlim, self.ylim = xlim, ylim

    def labels(self, title, xlabel, ylabel):
        self.title, self.xlabel, self.ylabel = title, xlabel, ylabel

    def _px(self, x):
        lo, hi = self.xlim
        return self.m + (x - lo) / (hi - lo) * (self.w - 2 * self.m)

    def _py(self, y):
        lo, hi = self.ylim
        return self.h - self.m - (y - lo) / (hi - lo) * (self.h - 2 * self.m)

    def axes(self, xticks=None, yticks=None, logy=False):
        x0, y0 = self._px(self.xlim[0]), self._py(self.ylim[0])
        x1, y1 = self._px(self.xlim[1]), self._py(self.ylim[1])
        self.items.append(
            f'<rect x="{x0}" y="{y1}" width="{x1-x0}" height="{y0-y1}" '
            f'fill="white" stroke="#333" stroke-width="1.2"/>')
        ticks = yticks or self._auto_ticks(self.ylim)
        for t in ticks:
            yy = self._py(t)
            self.items.append(
                f'<line x1="{x0}" y1="{yy}" x2="{x1}" y2="{yy}" '
                f'stroke="#eee"/>')
            self.items.append(
                f'<text x="{x0-6}" y="{yy+4}" font-size="11" '
                f'text-anchor="end" fill="#333">{self._fmt(t)}</text>')
        ticks = xticks or self._auto_ticks(self.xlim)
        for t in ticks:
            xx = self._px(t)
            self.items.append(
                f'<text x="{xx}" y="{y0+16}" font-size="11" '
                f'text-anchor="middle" fill="#333">{self._fmt(t)}</text>')
        self.items.append(
            f'<text x="{(x0+x1)/2}" y="{self.h-12}" font-size="13" '
            f'text-anchor="middle">{self.xlabel}</text>')
        self.items.append(
            f'<text transform="translate(16,{(y0+y1)/2}) rotate(-90)" '
            f'font-size="13" text-anchor="middle">{self.ylabel}</text>')
        self.items.append(
            f'<text x="{(x0+x1)/2}" y="24" font-size="15" font-weight="bold" '
            f'text-anchor="middle">{self.title}</text>')

    @staticmethod
    def _auto_ticks(lim, n=5):
        lo, hi = lim
        step = (hi - lo) / n
        return [lo + step * i for i in range(n + 1)]

    @staticmethod
    def _fmt(v):
        return f"{v:.3g}" if abs(v) < 0.01 or abs(v) >= 1000 else f"{v:.3f}"

    def line(self, points, color="#1f77b4", width=2.0, dash=None,
             marker=None):
        pts = " ".join(f"{self._px(x):.2f},{self._py(y):.2f}"
                       for x, y in points)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.items.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" '
            f'stroke-width="{width}"{d}/>')
        if marker:
            for x, y in points:
                self.items.append(
                    f'<circle cx="{self._px(x):.2f}" cy="{self._py(y):.2f}" '
                    f'r="3.2" fill="{color}"/>')

    def hline(self, y, color="#555", dash="6,4"):
        self.items.append(
            f'<line x1="{self._px(self.xlim[0])}" y1="{self._py(y)}" '
            f'x2="{self._px(self.xlim[1])}" y2="{self._py(y)}" '
            f'stroke="{color}" stroke-dasharray="{dash}"/>')

    def legend(self, entries):
        x = self.w - self.m - 150
        y = self.m + 10
        for i, (label, color) in enumerate(entries):
            yy = y + i * 18
            self.items.append(
                f'<line x1="{x}" y1="{yy}" x2="{x+22}" y2="{yy}" '
                f'stroke="{color}" stroke-width="2.5"/>')
            self.items.append(
                f'<text x="{x+28}" y="{yy+4}" font-size="11">{label}</text>')

    def save(self, path):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" '
               f'height="{self.h}" viewBox="0 0 {self.w} {self.h}">'
               + "".join(self.items) + "</svg>")
        with open(path, "w") as fh:
            fh.write(svg)
