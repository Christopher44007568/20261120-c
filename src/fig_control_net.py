"""Render the cubic Bezier control net of one PN-triangle as an SVG diagram.
The 10 geometry control points (b_ijk, i+j+k=3) are drawn with their labels
and connected by the Bezier net edges."""
import json
import os

from mesh import make_icosahedron
from pn_triangles import build_pn_patches

OUT = os.path.join(os.path.dirname(__file__), "..", "artifacts",
                   "figures", "pn_control_net.svg")

# Correct layout computed from actual barycentric weights.
def bary2d(ijk):
    i, j, k = ijk
    u, v, w = i / 3, j / 3, k / 3
    p0 = (0.0, 0.0)
    p1 = (1.0, 0.0)
    p2 = (0.5, 0.8660254)
    return (u * p0[0] + v * p1[0] + w * p2[0],
            u * p0[1] + v * p1[1] + w * p2[1])


def main():
    mesh = make_icosahedron()
    patches, _ = build_pn_patches(mesh)
    patch = patches[0]
    scale, ox, oy = 460.0, 130.0, 70.0
    pos = {k: (ox + bary2d(k)[0] * scale,
               oy + (0.8660254 - bary2d(k)[1]) * scale)
           for k in patch.b}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="720" '
             f'height="520" viewBox="0 0 720 520">']
    parts.append('<rect width="720" height="520" fill="white"/>')
    parts.append('<text x="360" y="34" font-size="18" font-weight="bold" '
                 'text-anchor="middle">PN-triangle: 10 cubic geometry '
                 'control points (b_ijk)</text>')
    # Bezier net edges: connect keys differing by one unit along i/j/k.
    keys = list(patch.b)
    for a in keys:
        for b in keys:
            if a >= b:
                continue
            diff = tuple(abs(x - y) for x, y in zip(a, b))
            if sum(diff) == 1:
                parts.append(
                    f'<line x1="{pos[a][0]:.1f}" y1="{pos[a][1]:.1f}" '
                    f'x2="{pos[b][0]:.1f}" y2="{pos[b][1]:.1f}" '
                    f'stroke="#9ecae1" stroke-width="1.5"/>')
    for k, (x, y) in pos.items():
        corner = k in ((3, 0, 0), (0, 3, 0), (0, 0, 3))
        fill = "#d62728" if corner else "#1f77b4"
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" '
                     f'fill="{fill}" stroke="white" stroke-width="1.5"/>')
        label = f"b{k[0]}{k[1]}{k[2]}"
        parts.append(f'<text x="{x+10:.1f}" y="{y+4:.1f}" font-size="12" '
                     f'fill="#222">{label}</text>')
    parts.append('<circle cx="150" cy="470" r="6.5" fill="#d62728"/>'
                 '<text x="165" y="474" font-size="13">corner control '
                 'points = original mesh vertices</text>')
    parts.append('<circle cx="420" cy="470" r="6.5" fill="#1f77b4"/>'
                 '<text x="435" y="474" font-size="13">edge/interior '
                 'control points (normal-driven)</text>')
    parts.append("</svg>")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        fh.write("".join(parts))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
