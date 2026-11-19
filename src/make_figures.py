"""Generate SVG figures from the computed JSON artifacts."""
import json
import os

from svg_plot import SvgCanvas

ROOT = os.path.join(os.path.dirname(__file__), "..")
ART = os.path.join(ROOT, "artifacts")
FIG = os.path.join(ART, "figures")


def load(name):
    with open(os.path.join(ART, name)) as fh:
        return json.load(fh)


def fig_silhouette_turning():
    data = load("silhouette.json")
    pn = [(d["triangles"], d["mean_turn_deg"])
          for d in data if d["method_name"].startswith("PN")]
    cc = [(d["triangles"], d["mean_turn_deg"])
          for d in data if d["method_name"].startswith("Catmull")]
    base = data[0]["mean_turn_deg"]
    xs = [1] + [p[0] for p in pn] + [c[0] for c in cc]
    ys = [base] + [p[1] for p in pn] + [c[1] for c in cc]
    cv = SvgCanvas()
    cv.set_limits((0, max(xs) * 1.05), (0, max(ys) * 1.1))
    cv.labels("Contour smoothness on low-poly icosahedron",
              "triangles", "mean contour turn angle (deg)")
    cv.axes()
    cv.hline(base, color="#d62728")
    cv.line(sorted(pn), color="#1f77b4", marker=True)
    cv.line(sorted(cc), color="#ff7f0e", marker=True)
    cv.legend([("PN-triangles", "#1f77b4"),
               ("Catmull-Clark", "#ff7f0e"),
               ("low-poly baseline", "#d62728")])
    cv.save(os.path.join(FIG, "silhouette_turning.svg"))


def fig_silhouette_radial():
    data = load("silhouette.json")
    pn = [(d["triangles"], d["radial_rms"])
          for d in data if d["method_name"].startswith("PN")]
    cc = [(d["triangles"], d["radial_rms"])
          for d in data if d["method_name"].startswith("Catmull")]
    cv = SvgCanvas()
    allv = pn + cc
    cv.set_limits((0, max(x for x, _ in allv) * 1.05),
                  (0, max(y for _, y in allv) * 1.15))
    cv.labels("Contour radial deviation vs unit sphere",
              "triangles", "RMS radial deviation")
    cv.axes()
    cv.line(sorted(pn), color="#1f77b4", marker=True)
    cv.line(sorted(cc), color="#ff7f0e", marker=True)
    cv.legend([("PN-triangles", "#1f77b4"),
               ("Catmull-Clark", "#ff7f0e")])
    cv.save(os.path.join(FIG, "silhouette_radial.svg"))


def fig_curvature_errors():
    data = load("curvature_errors.json")
    bins = [b["bin"] for b in data["pn"]]
    x = list(range(len(bins)))
    cv = SvgCanvas(width=760)
    cv.set_limits((-0.5, len(bins) - 0.5),
                  (0, max(b["pos_rms"] for b in data["pn"]
                          + data["catmull_clark"]) * 1.2))
    cv.labels("Position error vs analytic torus (stratified by |dk|)",
              "curvature-variation bin", "RMS position error")
    cv.axes(xticks=x)
    width = 0.18
    for i, b in enumerate(data["pn"]):
        cx = cv._px(i) - width * 60
        cv.items.append(
            f'<rect x="{cx}" y="{cv._py(b["pos_rms"])}" width="26" '
            f'height="{cv._py(cv.ylim[0])-cv._py(b["pos_rms"])}" '
            f'fill="#1f77b4"/>')
    for i, b in enumerate(data["catmull_clark"]):
        cx = cv._px(i) + 6
        cv.items.append(
            f'<rect x="{cx}" y="{cv._py(b["pos_rms"])}" width="26" '
            f'height="{cv._py(cv.ylim[0])-cv._py(b["pos_rms"])}" '
            f'fill="#ff7f0e"/>')
    for i, lab in enumerate(bins):
        cv.items.append(
            f'<text x="{cv._px(i)}" y="{cv.h-cv.m+34}" font-size="11" '
            f'text-anchor="middle">{lab}</text>')
    cv.legend([("PN-triangles", "#1f77b4"),
               ("Catmull-Clark", "#ff7f0e")])
    cv.save(os.path.join(FIG, "curvature_position_error.svg"))


def main():
    os.makedirs(FIG, exist_ok=True)
    fig_silhouette_turning()
    fig_silhouette_radial()
    fig_curvature_errors()
    fig_volume_bias()
    print("figures written to", FIG)


def fig_volume_bias():
    data = load("volume_render.json")
    het = data["media"]["heterogeneous"]
    truth = het["analytic_transmittance"]
    left = [(r["dt"], r["rel_error_vs_analytic_pct"])
            for r in het["ray_marching"] if r["rule"] == "left"]
    mid = [(r["dt"], r["rel_error_vs_analytic_pct"])
           for r in het["ray_marching"] if r["rule"] == "midpoint"]
    cv = SvgCanvas()
    xs = [d for d, _ in left] + [d for d, _ in mid]
    ys = [v for _, v in left] + [v for _, v in mid]
    cv.set_limits((min(xs) * 0.8, max(xs) * 1.1),
                  (0, max(ys) * 1.15))
    cv.labels("Ray-march transmittance bias vs step size (heterogeneous)",
              "step size dt", "relative error (%)")
    cv.axes()
    cv.line(sorted(left), color="#d62728", marker=True)
    cv.line(sorted(mid), color="#2ca02c", marker=True)
    cv.legend([("left Riemann (1st order)", "#d62728"),
               ("midpoint rule (2nd order)", "#2ca02c")])
    cv.save(os.path.join(FIG, "volume_bias.svg"))


if __name__ == "__main__":
    main()
