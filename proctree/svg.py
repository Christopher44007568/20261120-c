"""SVG rendering for generated trees (no external dependencies)."""

from __future__ import annotations

from .plant import Tree


def _normalizer(tree: Tree, panel_w: float, panel_h: float):
    xmin, ymin, xmax, ymax = tree.bbox
    width = max(xmax - xmin, 1e-9)
    height = max(ymax - ymin, 1e-9)
    margin = 18.0
    scale = min((panel_w - 2 * margin) / width, (panel_h - 2 * margin) / height)

    def project(x: float, y: float) -> tuple[float, float]:
        px = (x - xmin) * scale + (panel_w - width * scale) / 2.0
        py = panel_h - ((y - ymin) * scale + (panel_h - height * scale) / 2.0)
        return px, py

    return project, scale


def render_tree_svg(tree: Tree, width: float = 360.0, height: float = 460.0) -> str:
    project, _ = _normalizer(tree, width, height)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" '
        f'height="{height:g}" viewBox="0 0 {width:g} {height:g}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    for seg in tree.segments:
        x0, y0 = project(*seg.start)
        x1, y1 = project(*seg.end)
        parts.append(
            f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" '
            f'stroke="#6b4a2b" stroke-width="{max(0.7, 3.2 * 0.72 ** seg.level):.2f}" '
            'stroke-linecap="round"/>'
        )
    for leaf in tree.leaves:
        bx, by = project(*leaf.base)
        tx, ty = project(*leaf.tip)
        parts.append(
            f'<ellipse cx="{(bx + tx) / 2:.2f}" cy="{(by + ty) / 2:.2f}" '
            f'rx="{max(1.6, abs(tx - bx) * 0.9 + 1.2):.2f}" '
            f'ry="{max(1.2, abs(ty - by) * 0.9 + 0.8):.2f}" '
            f'fill="#3f8f3f" opacity="0.82"/>'
        )
    parts.append(
        f'<text x="10" y="22" font-family="monospace" font-size="14" '
        f'fill="#222">{tree.params.name} depth={tree.depth}</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def render_comparison_svg(trees: list[Tree], panel_w: float = 300.0,
                          panel_h: float = 420.0) -> str:
    width = panel_w * len(trees)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" '
        f'height="{panel_h:g}" viewBox="0 0 {width:g} {panel_h:g}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    for index, tree in enumerate(trees):
        offset = index * panel_w
        parts.append(f'<g transform="translate({offset:g},0)">')
        project, _ = _normalizer(tree, panel_w, panel_h - 30.0)
        for seg in tree.segments:
            x0, y0 = project(*seg.start)
            x1, y1 = project(*seg.end)
            parts.append(
                f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" '
                f'y2="{y1:.2f}" stroke="#6b4a2b" '
                f'stroke-width="{max(0.5, 2.4 * 0.72 ** seg.level):.2f}" '
                'stroke-linecap="round"/>'
            )
        for leaf in tree.leaves:
            bx, by = project(*leaf.base)
            tx, ty = project(*leaf.tip)
            parts.append(
                f'<ellipse cx="{(bx + tx) / 2:.2f}" cy="{(by + ty) / 2:.2f}" '
                f'rx="{max(1.4, abs(tx - bx) * 0.9 + 1.0):.2f}" '
                f'ry="{max(1.1, abs(ty - by) * 0.9 + 0.7):.2f}" '
                f'fill="#3f8f3f" opacity="0.8"/>'
            )
        parts.append(
            f'<text x="10" y="{panel_h - 10:g}" font-family="monospace" '
            f'font-size="13" fill="#222">depth={tree.depth} '
            f"seg={len(tree.segments)} leaf={len(tree.leaves)}</text>"
        )
        parts.append("</g>")
        if index:
            parts.append(
                f'<line x1="{offset:g}" y1="0" x2="{offset:g}" '
                f'y2="{panel_h:g}" stroke="#dddddd" stroke-dasharray="4 4"/>'
            )
    parts.append("</svg>")
    return "\n".join(parts)
