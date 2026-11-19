"""Photometric web (IES) lab:
  1. read IES files, sample candela by incident angle, scale intensity
  2. compare point-light vs IES highlight shapes on a ground plane
  3. verify directionality of spot vs wall-wash webs
  4. report total luminous flux of both webs
  5. mip selection for the IES texture + moire test at minification
"""

import math

from ies_toolkit import IESFile, IESTexture

SPOT_PATH = "ies/spot.ies"
WASH_PATH = "ies/wallwash.ies"


def fmt_row(label, values, fmt="%8.2f"):
    return "%-14s" % label + " ".join(fmt % v for v in values)


def section_candela_sampling(spot, wash):
    print("== 1. Candela by incident angle (theta=from nadir, phi=azimuth) ==")
    thetas = [0, 15, 30, 45, 60, 75, 90]
    print("theta(deg):   " + " ".join("%8d" % t for t in thetas))
    print(fmt_row("spot phi=0",
                  [spot.candela_at(t, 0) for t in thetas]))
    print(fmt_row("wash phi=0",
                  [wash.candela_at(t, 0) for t in thetas]))
    print(fmt_row("wash phi=90",
                  [wash.candela_at(t, 90) for t in thetas]))
    print(fmt_row("wash phi=180",
                  [wash.candela_at(t, 180) for t in thetas]))
    # intensity scaling: doubling scale must double candela
    base = wash.candela_at(45, 0, intensity_scale=1.0)
    doubled = wash.candela_at(45, 0, intensity_scale=2.0)
    ok = abs(doubled - 2.0 * base) < 1e-9
    print("intensity scale x2 at (45,0): %.3f -> %.3f cd  [%s]"
          % (base, doubled, "OK" if ok else "FAIL"))
    print()


def ground_irradiance(ies, x, y, height, iso_candela=None):
    """Irradiance on floor at (x,y) from a luminaire at origin, height h."""
    d2 = x * x + y * y + height * height
    d = math.sqrt(d2)
    cos_t = height / d
    theta = math.degrees(math.acos(cos_t))
    phi = math.degrees(math.atan2(y, x)) % 360.0
    if iso_candela is not None:
        cd = iso_candela
    else:
        cd = ies.candela_at(theta, phi)
    return cd * cos_t / d2


def ascii_map(grid, rows, cols):
    peak = max(max(r) for r in grid)
    chars = " .:-=+*#%@"
    out = []
    for r in range(rows):
        line = ""
        for c in range(cols):
            v = grid[r][c] / peak if peak > 0 else 0.0
            line += chars[min(int(v * (len(chars) - 1) + 0.5),
                              len(chars) - 1)]
        out.append(line)
    return out


def section_highlight_shapes(spot, wash):
    print("== 2. Highlight shape on floor (h=2m, 21x21 grid, step 0.4m) ==")
    height, n, step = 2.0, 21, 0.4
    iso = spot.total_flux() / (4.0 * math.pi)  # same-flux point light
    grids = {}
    for name in ("point", "spot", "wallwash"):
        grid = []
        for r in range(n):
            y = (r - n // 2) * step
            row = []
            for c in range(n):
                x = (c - n // 2) * step
                if name == "point":
                    row.append(ground_irradiance(None, x, y, height, iso))
                else:
                    ies = spot if name == "spot" else wash
                    row.append(ground_irradiance(ies, x, y, height))
            grid.append(row)
        grids[name] = grid
    for name in ("point", "spot", "wallwash"):
        print("-- %s (peak %.2f lux) --"
              % (name, max(max(r) for r in grids[name])))
        for line in ascii_map(grids[name], n, n):
            print(line)
        print()
    # numeric profile along +x at y=0
    mid = n // 2
    print("profile y=0, x=-4m..+4m (lux):")
    print(fmt_row("point", grids["point"][mid], "%8.3f"))
    print(fmt_row("spot", grids["spot"][mid], "%8.3f"))
    print(fmt_row("wallwash", grids["wallwash"][mid], "%8.3f"))
    print()


def section_directionality(spot, wash):
    print("== 3. Directionality check ==")
    # spot must be symmetric: candela at +x equals -x for same theta
    diffs = [abs(spot.candela_at(t, 0) - spot.candela_at(t, 180))
             for t in range(0, 91, 5)]
    spot_sym = max(diffs) < 1e-6
    print("spot axial symmetry max |I(+x)-I(-x)| = %.3e cd  [%s]"
          % (max(diffs), "OK" if spot_sym else "FAIL"))
    # wall-wash must throw toward +x: I(45deg, phi=0) >> I(45deg, phi=180)
    fwd = wash.candela_at(45, 0)
    back = wash.candela_at(45, 180)
    ratio = fwd / back if back > 0 else float("inf")
    print("wallwash I(45,+x)=%.1f cd  I(45,-x)=%.1f cd  ratio=%.2f  [%s]"
          % (fwd, back, ratio, "OK" if ratio > 3.0 else "FAIL"))
    print()
    return spot_sym, ratio > 3.0


def section_flux(spot, wash):
    print("== 4. Total luminous flux ==")
    f_spot = spot.total_flux()
    f_wash = wash.total_flux()
    print("spot     total flux = %.2f lm" % f_spot)
    print("wallwash total flux = %.2f lm" % f_wash)
    consistent = abs(f_spot - f_wash) < 1.0
    print("flux consistent (|dF| < 1 lm): %s (dF = %.4f lm)"
          % ("OK" if consistent else "FAIL", abs(f_spot - f_wash)))
    print()
    return consistent


def rasterize_ies_texture(ies, width=256, height=128, fine_detail=True):
    """Rasterize candela into a (u=azimuth, v=polar) texture. A fine
    sinusoidal modulation simulates the high-frequency lamp detail that
    causes moire when minified without mip mapping."""
    tex = []
    for j in range(height):
        theta = (j + 0.5) / height * 90.0
        row = []
        for i in range(width):
            phi = (i + 0.5) / width * 360.0
            cd = ies.candela_at(theta, phi)
            if fine_detail:
                cd *= 1.0 + 0.30 * math.sin(2.0 * math.pi * 32.0
                                            * i / width)
            row.append(cd)
        tex.append(row)
    return tex


def section_mip(wash):
    print("== 5. IES texture mip selection & moire test ==")
    width, height = 256, 128
    tex = IESTexture(rasterize_ies_texture(wash, width, height))
    print("mip chain: " + " -> ".join(
        "%dx%d" % (len(m[0]), len(m)) for m in tex.mips))
    # mip selection for growing screen-space footprints (near -> far)
    print("footprint(texels)  selected LOD")
    for fp in (1.0, 2.0, 8.0, 32.0, 128.0):
        lod = IESTexture.select_lod(fp / width, fp / height, width, height)
        print("%8.1f            %.2f (mip %d)" % (fp, lod, round(lod)))
    # moire test: a distant pixel covers a 64-texel footprint; slide its
    # center slowly across one fine-stripe period and watch the sample.
    # mip0 point-sampling oscillates (moire); the mipmapped value must
    # stay glued to the true footprint average.
    fp_u = 64.0 / width
    fp_v = 64.0 / height
    lod = IESTexture.select_lod(fp_u, fp_v, width, height)
    stripe_period_u = 1.0 / 32.0          # 32 stripe cycles across width
    u0, v0 = 0.10, 0.55
    steps = 16
    raw, filtered, truths = [], [], []
    n = 32
    for k in range(steps):
        uc = u0 + fp_u / 2.0 + stripe_period_u * k / steps
        raw.append(tex.sample(uc, v0, lod=0.0))
        filtered.append(tex.sample(uc, v0, lod=lod))
        # ground truth: dense 2D supersampled footprint average at mip0
        acc = 0.0
        for iu in range(n):
            for iv in range(n):
                uu = uc - fp_u / 2.0 + fp_u * (iu + 0.5) / n
                vv = v0 - fp_v / 2.0 + fp_v * (iv + 0.5) / n
                acc += tex.sample(uu, vv, lod=0.0)
        truths.append(acc / (n * n))

    def stats(vals):
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        return mean, math.sqrt(var), min(vals), max(vals)

    m0, s0, lo0, hi0 = stats(raw)
    m1, s1, lo1, hi1 = stats(filtered)
    truth = sum(truths) / len(truths)
    print("distant pixel (footprint=64 texels, auto LOD=%.2f)," % lod)
    print("center slid across one fine-detail period:")
    print("  true footprint average = %.2f cd" % truth)
    print("  mip0 only : mean=%.2f std=%.2f range=[%.2f, %.2f]"
          % (m0, s0, lo0, hi0))
    print("  mipmapped : mean=%.2f std=%.2f range=[%.2f, %.2f]"
          % (m1, s1, lo1, hi1))
    moire_free = (s1 < 0.05 * abs(m1) and s0 > 5.0 * s1
                  and abs(m1 - truth) < 0.05 * truth)
    print("moire check: mip0 oscillation/mip oscillation = %.1fx,"
          " mipmapped vs truth = %+.2f%%  [%s]"
          % (s0 / s1 if s1 > 0 else float("inf"),
             100.0 * (m1 - truth) / truth,
             "OK" if moire_free else "FAIL"))
    print()
    return moire_free


def main():
    spot = IESFile.parse(SPOT_PATH)
    wash = IESFile.parse(WASH_PATH)
    section_candela_sampling(spot, wash)
    section_highlight_shapes(spot, wash)
    sym_ok, wash_ok = section_directionality(spot, wash)
    flux_ok = section_flux(spot, wash)
    mip_ok = section_mip(wash)
    print("== Summary ==")
    print("spot symmetric directionality : %s" % ("OK" if sym_ok else "FAIL"))
    print("wallwash forward throw        : %s" % ("OK" if wash_ok else "FAIL"))
    print("total flux consistent         : %s" % ("OK" if flux_ok else "FAIL"))
    print("mip selection kills moire     : %s" % ("OK" if mip_ok else "FAIL"))


if __name__ == "__main__":
    main()
