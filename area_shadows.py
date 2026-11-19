"""Analytic soft-shadow edges for capsule, disk and rectangle area lights.

A spherical occluder of radius ``OCC_R`` sits on the axis between the area
light (at height ``LIGHT_Z``) and a receiver plane at z=0. In the far field
(light and receiver both much farther than the light size) rays toward a
receiver point P are parallel, so the occluder's silhouette is a disk on the
light's plane and the problem reduces to the planar overlap area between:

  * the area-light shape (disk / rectangle / capsule), and
  * the occluder's projected silhouette disk.

The blocked fraction is overlap_area / light_area, so the received
irradiance is E * (1 - blocked_fraction). Overlap formulas are analytic:

  * disk-disk: classic two-circle segment formula,
  * disk-rectangle: exact integral over rectangle quadrants,
  * disk-capsule: analytic on-axis, adaptive-Simpson off-axis.

Every analytic result is cross-checked against an independent dense grid
sampler and a 3D Monte Carlo ray test. Run directly for reports and SVGs.
"""

import json
import math
import os
import random

from svgchart import line_chart

OCC_R = 1.6            # occluder radius (larger silhouette than the lights)
OCC_Z = 2.0            # occluder height above receiver
LIGHT_Z = 20.0         # area light height (far field)
TARGET_AREA = 4.0      # equal emitting area for all three lights

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")


# ---------------------------------------------------------------- geometry

def circle_circle_area(r1, r2, d):
    """Overlap area of two circles with radii r1, r2 and center distance d."""
    if d >= r1 + r2:
        return 0.0
    if d <= abs(r1 - r2):
        return math.pi * min(r1, r2) ** 2
    a = (r1 ** 2 - r2 ** 2 + d ** 2) / (2.0 * d)
    h = math.sqrt(max(r1 ** 2 - a ** 2, 0.0))
    seg1 = r1 ** 2 * math.acos(min(max(a / r1, -1.0), 1.0)) - a * h
    seg2 = r2 ** 2 * math.acos(min(max((d - a) / r2, -1.0), 1.0)) - (d - a) * h
    return seg1 + seg2


def _quarter_circle_integral(r, x):
    """Integral_0^x sqrt(r^2-t^2) dt for x in [0, r] (first-quadrant slice)."""
    x = min(max(x, 0.0), r)
    return 0.5 * (x * math.sqrt(max(r ** 2 - x ** 2, 0.0))
                  + r ** 2 * math.asin(x / r))


def circle_rect_area(cx, cy, r, x0, x1, y0, y1):
    """Exact overlap area between a circle and an axis-aligned rectangle."""
    x_lo, x_hi = max(x0 - cx, -r), min(x1 - cx, r)
    y_lo, y_hi = max(y0 - cy, -r), min(y1 - cy, r)
    if x_lo >= x_hi or y_lo >= y_hi:
        return 0.0

    def q(x, y):
        """Area of the circle inside the first-quadrant box [0,x] x [0,y]."""
        if x <= 0 or y <= 0:
            return 0.0
        if x * x + y * y <= r * r:
            return x * y                      # box corner inside the circle
        if x >= r and y >= r:
            return math.pi * r * r / 4.0      # quarter disk fully covered
        if x >= r:
            return _quarter_circle_integral(r, y)
        if y >= r:
            return _quarter_circle_integral(r, x)
        # Neither edge spans the circle: disk cuts both box edges.
        return (_quarter_circle_integral(r, x)
                + _quarter_circle_integral(r, y)
                - math.pi * r * r / 4.0)

    def f(x, y):
        return (q(abs(x), abs(y)) * (1 if x >= 0 else -1)
                * (1 if y >= 0 else -1))

    return (f(x_hi, y_hi) - f(x_lo, y_hi)
            - f(x_hi, y_lo) + f(x_lo, y_lo))


def _adaptive_simpson(func, a, b, eps=1e-9, depth=20):
    m = (a + b) / 2.0
    whole = (b - a) / 6.0 * (func(a) + 4.0 * func(m) + func(b))
    lm = (a + m) / 2.0
    rm = (m + b) / 2.0
    left = (m - a) / 6.0 * (func(a) + 4.0 * func(lm) + func(m))
    right = (b - m) / 6.0 * (func(m) + 4.0 * func(rm) + func(b))
    if depth <= 0 or abs(left + right - whole) <= 15.0 * eps:
        return left + right + (left + right - whole) / 15.0
    return (_adaptive_simpson(func, a, m, eps / 2.0, depth - 1)
            + _adaptive_simpson(func, m, b, eps / 2.0, depth - 1))


def circle_capsule_area(cx, cy, r, half_len, cap_r):
    """Overlap between a circle (cx,cy,r) and a horizontal capsule.

    Capsule: rectangle [-half_len, half_len] x [-cap_r, cap_r] plus two
    end disks of radius cap_r centered at (+/-half_len, 0).
    Adaptive Simpson quadrature over x; each x-slice integrand is analytic,
    so the result converges to the exact overlap (eps 1e-9).
    """
    def slice_half_height(x):
        ax = abs(x)
        if ax <= half_len:
            return cap_r
        dx = ax - half_len
        if dx >= cap_r:
            return 0.0
        return math.sqrt(cap_r * cap_r - dx * dx)

    def integrand(x):
        h = slice_half_height(x)
        if h == 0.0:
            return 0.0
        chord = math.sqrt(max(r * r - (x - cx) ** 2, 0.0))
        # Circle spans world y in [cy-chord, cy+chord]; capsule in [-h, h].
        lo = max(-h, cy - chord)
        hi = min(h, cy + chord)
        return max(hi - lo, 0.0)

    support_lo = max(cx - r, -half_len - cap_r)
    support_hi = min(cx + r, half_len + cap_r)
    if support_lo >= support_hi:
        return 0.0
    panels = 16
    step = (support_hi - support_lo) / panels
    return sum(_adaptive_simpson(integrand,
                                 support_lo + i * step,
                                 support_lo + (i + 1) * step)
               for i in range(panels))


# ---------------------------------------------------------------- validators

def grid_overlap(shape, circle, spacing=0.001, bounds=None):
    """Independent dense-grid estimate of overlap area (numerical reference)."""
    cx, cy, r = circle
    x_min = cx - r if bounds is None else max(cx - r, bounds[0])
    x_max = cx + r if bounds is None else min(cx + r, bounds[1])
    y_min = cy - r if bounds is None else max(cy - r, bounds[2])
    y_max = cy + r if bounds is None else min(cy + r, bounds[3])
    nx = max(int(math.ceil((x_max - x_min) / spacing)), 1)
    ny = max(int(math.ceil((y_max - y_min) / spacing)), 1)
    count = 0
    for i in range(nx):
        x = x_min + (i + 0.5) * spacing
        for j in range(ny):
            y = y_min + (j + 0.5) * spacing
            if (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2 and shape["inside"](x, y):
                count += 1
    return count * spacing * spacing


# ---------------------------------------------------------------- scene setup

def make_lights():
    """Disk, rectangle and capsule with identical emitting area TARGET_AREA."""
    disk_r = math.sqrt(TARGET_AREA / math.pi)
    rect_w = math.sqrt(TARGET_AREA)            # square rectangle
    cap_r = 0.7
    # capsule area = pi*r^2 + 2*r*(2*half_len); solve for half length
    half_len = max((TARGET_AREA - math.pi * cap_r ** 2) / (4.0 * cap_r), 0.05)
    lights = {
        "disk": {
            "area": math.pi * disk_r ** 2,
            "inside": lambda x, y, r=disk_r: x * x + y * y <= r * r,
            "overlap": lambda cx, cy, r: circle_circle_area(r, disk_r,
                                                             math.hypot(cx, cy)),
        },
        "rectangle": {
            "area": rect_w ** 2,
            "inside": lambda x, y, h=rect_w / 2: abs(x) <= h and abs(y) <= h,
            "overlap": lambda cx, cy, r, h=rect_w / 2:
                circle_rect_area(cx, cy, r, -h, h, -h, h),
        },
        "capsule": {
            "area": math.pi * cap_r ** 2 + 4.0 * cap_r * half_len,
            "inside": _capsule_inside(half_len, cap_r),
            "overlap": lambda cx, cy, r:
                circle_capsule_area(cx, cy, r, half_len, cap_r),
        },
    }
    return lights


def _capsule_inside(half_len, cap_r):
    def inside(x, y):
        if abs(x) <= half_len:
            return abs(y) <= cap_r
        dx = abs(x) - half_len
        return dx * dx + y * y <= cap_r * cap_r
    return inside


def projected_occluder_radius(receiver_radius):
    """Radius of the occluder silhouette projected onto the light plane.

    Parallel-ray far-field projection through the sphere onto the light
    plane: similar triangles give R = OCC_R * LIGHT_Z / (LIGHT_Z - OCC_Z).
    The silhouette center is shifted from the axis by the same scaling.
    """
    scale = LIGHT_Z / (LIGHT_Z - OCC_Z)
    return OCC_R * scale, scale


def shadow_profile(lights, axis_points):
    """Blocked fraction vs receiver offset along the x axis."""
    r_proj, scale = projected_occluder_radius(0.0)
    rows = []
    for rho in axis_points:
        row = {"receiver_offset": rho, "projected_radius": r_proj}
        for name, light in lights.items():
            cx, cy = rho * scale, 0.0
            overlap = light["overlap"](cx, cy, r_proj)
            row[name] = min(max(overlap / light["area"], 0.0), 1.0)
        rows.append(row)
    return rows


def monte_carlo_blocked(lights, rho, samples=40000, seed=7):
    """3D Monte Carlo: sample the real area light, ray-test the sphere."""
    rng = random.Random(seed)
    r_proj, scale = projected_occluder_radius(rho)
    out = {}
    for name, light in lights.items():
        hits = 0
        used = 0
        # Rejection sampling inside a bounding box; enough for all shapes.
        bound = 3.0
        while used < samples:
            lx = rng.uniform(-bound, bound)
            ly = rng.uniform(-bound, bound)
            if not light["inside"](lx, ly):
                continue
            used += 1
            # Receiver point P=(rho,0,0); parallel ray direction toward light.
            px, py = rho * scale, 0.0
            if (lx - px) ** 2 + (ly - py) ** 2 <= r_proj ** 2:
                hits += 1
        out[name] = hits / samples
    return out


def validate_analytic_vs_grid(lights):
    """Sweep projected-disk centers including off-axis positions."""
    r_proj, _ = projected_occluder_radius(0.0)
    cases = [(dx, 0.0) for dx in (0.0, 0.4, 0.8, 1.2, 1.6, 2.0, 2.4)]
    cases += [(0.8, 0.6), (1.2, 0.9), (0.3, 0.3)]
    results = []
    for cx, cy in cases:
        for name, light in lights.items():
            analytic = light["overlap"](cx, cy, r_proj)
            disk_r = math.sqrt(TARGET_AREA / math.pi)
            cap_r = 0.7
            cap_hl = max((TARGET_AREA - math.pi * cap_r ** 2) / (4.0 * cap_r), 0.05)
            half = math.sqrt(TARGET_AREA) / 2.0
            bounds = {
                "disk": (-disk_r, disk_r, -disk_r, disk_r),
                "rectangle": (-half, half, -half, half),
                "capsule": (-cap_hl - cap_r, cap_hl + cap_r, -cap_r, cap_r),
            }[name]
            numeric = grid_overlap(light, (cx, cy, r_proj), bounds=bounds)
            denom = max(light["area"], 1e-12)
            results.append({
                "shape": name,
                "center": [cx, cy],
                "analytic_overlap": analytic,
                "grid_overlap": numeric,
                "abs_error": abs(analytic - numeric),
                "relative_fraction_error": abs(analytic - numeric) / denom,
            })
    return results


def penumbra_metrics(rows, lights):
    """Umbra/penumbra extents where blocked fraction crosses 1.0 and 0.0."""
    metrics = {}
    for name in lights:
        umbra = next((r["receiver_offset"] for r in rows if r[name] < 0.999), None)
        penumbra = next((r["receiver_offset"] for r in reversed(rows) if r[name] > 0.001), None)
        edge50 = next((r["receiver_offset"] for r in rows if r[name] <= 0.5), None)
        metrics[name] = {"umbra_radius": umbra, "penumbra_radius": penumbra,
                         "half_shadow_offset": edge50}
    return metrics


def main():
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    lights = make_lights()
    axis = [i * 0.08 for i in range(61)]
    rows = shadow_profile(lights, axis)
    validation = validate_analytic_vs_grid(lights)
    mc_points = [0.0, 0.8, 1.6, 2.4]
    mc = {rho: monte_carlo_blocked(lights, rho) for rho in mc_points}
    mc_compare = []
    for rho in mc_points:
        row = next(r for r in rows if abs(r["receiver_offset"] - rho) < 1e-9)
        for name in lights:
            mc_compare.append({
                "receiver_offset": rho,
                "shape": name,
                "analytic_blocked": row[name],
                "monte_carlo_blocked": mc[rho][name],
                "abs_difference": abs(row[name] - mc[rho][name]),
            })
    metrics = penumbra_metrics(rows, lights)

    report = {
        "config": {
            "occluder_radius": OCC_R,
            "occluder_height": OCC_Z,
            "light_height": LIGHT_Z,
            "equal_light_area": TARGET_AREA,
            "projected_occluder_radius": projected_occluder_radius(0.0)[0],
        },
        "light_areas": {k: v["area"] for k, v in lights.items()},
        "shadow_profile": rows,
        "analytic_vs_grid": validation,
        "analytic_vs_monte_carlo": mc_compare,
        "penumbra_metrics": metrics,
    }
    with open(os.path.join(ARTIFACT_DIR, "area_shadow_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    _write_markdown(report, validation, mc_compare, metrics)

    colors = {"disk": "#1f77b4", "rectangle": "#2ca02c", "capsule": "#d62728"}
    line_chart(
        os.path.join(ARTIFACT_DIR, "shadow_edges.svg"),
        [{"name": f"{name} blocked fraction", "color": colors[name],
          "points": [(r["receiver_offset"], r[name]) for r in rows]}
         for name in lights],
        "Receiver offset from shadow axis", "Blocked fraction",
        "Analytic soft-shadow edges: equal-area capsule, disk, rectangle")
    line_chart(
        os.path.join(ARTIFACT_DIR, "analytic_validation.svg"),
        [{"name": f"{name} |analytic - grid|", "color": colors[name],
          "points": [(v["center"][0], v["abs_error"])
                     for v in validation if v["shape"] == name]}
         for name in lights],
        "Projected-disk center offset", "Absolute area error",
        "Analytic overlap vs independent dense-grid integration")
    max_grid = max(v["abs_error"] for v in validation)
    max_mc = max(v["abs_difference"] for v in mc_compare)
    print(f"lights={ {k: round(v['area'],4) for k,v in lights.items()} }; "
          f"max analytic-grid error={max_grid:.2e}; "
          f"max analytic-MC difference={max_mc:.2e}")


def _write_markdown(report, validation, mc_compare, metrics):
    lines = [
        "# Area-Light Soft-Shadow Analytic Report",
        "",
        f"- Occluder sphere r={OCC_R} at z={OCC_Z}, area lights at z={LIGHT_Z}",
        f"- Equal emitting area {TARGET_AREA}; projected silhouette radius "
        f"{report['config']['projected_occluder_radius']:.4f}",
        f"- Light areas: " + ", ".join(f"{k}={v:.4f}" for k, v in report["light_areas"].items()),
        "",
        "## Shadow edge metrics",
        "",
        "| Light | Umbra radius (blocked>0.999) | 50% shadow offset | Penumbra radius (blocked<0.001) |",
        "|---|---|---|---|",
    ]
    for name, m in metrics.items():
        lines.append(
            f"| {name} | {m['umbra_radius']:.2f} | {m['half_shadow_offset']:.2f} | "
            f"{m['penumbra_radius']:.2f} |")
    lines += [
        "",
        "## Analytic vs dense-grid overlap validation",
        "",
        "| Shape | Center (x,y) | Analytic area | Grid area | Abs error |",
        "|---|---|---|---|---|",
    ]
    for v in validation:
        lines.append(
            f"| {v['shape']} | ({v['center'][0]:.1f},{v['center'][1]:.1f}) | "
            f"{v['analytic_overlap']:.5f} | {v['grid_overlap']:.5f} | {v['abs_error']:.2e} |")
    lines += [
        "",
        "## Analytic vs 3D Monte Carlo ray test",
        "",
        "| Offset | Shape | Analytic blocked | Monte Carlo blocked | Abs difference |",
        "|---|---|---|---|---|",
    ]
    for v in mc_compare:
        lines.append(
            f"| {v['receiver_offset']:.1f} | {v['shape']} | "
            f"{v['analytic_blocked']:.4f} | {v['monte_carlo_blocked']:.4f} | "
            f"{v['abs_difference']:.2e} |")
    lines += [
        "",
        f"- Max analytic-grid absolute error: {max(v['abs_error'] for v in validation):.2e}",
        f"- Max analytic-Monte Carlo difference: "
        f"{max(v['abs_difference'] for v in mc_compare):.2e} (Monte Carlo noise ~1/sqrt(N))",
        "",
    ]
    with open(os.path.join(ARTIFACT_DIR, "area_shadow_report.md"), "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
