"""Sweep roughness, fit LTC matrices to GGX, verify highlight-shape continuity."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ltc_fit import hemisphere_samples, fit_ltc

ALPHAS = [0.05 + 0.05 * i for i in range(20)]  # 0.05 .. 1.0
VIEWS = [("0deg", 0.0), ("45deg", math.radians(45)), ("75deg", math.radians(75))]


def view_dir(theta):
    return (math.sin(theta), 0.0, math.cos(theta))


def main():
    samples = hemisphere_samples()
    rows = []
    print("alpha  view    m00     m02     m11     m20     ampl    relRMS")
    for vname, vtheta in VIEWS:
        view = view_dir(vtheta)
        init = None
        prev = None
        max_jump = 0.0
        for alpha in ALPHAS:
            if init is None:
                a0 = max(alpha, 0.05)
                init = [a0, 0.0, a0, 0.0]
            params, err, ampl = fit_ltc(view, alpha, samples, init)
            init = params  # continuation: warm start next fit
            rel_rms = math.sqrt(err)
            rows.append((alpha, vname, *params, ampl, rel_rms))
            print(f"{alpha:.2f}  {vname:6s} {params[0]:+.4f} {params[1]:+.4f} "
                  f"{params[2]:+.4f} {params[3]:+.4f}  {ampl:.4f}  {rel_rms:.5f}")
            if prev is not None:
                jump = max(abs(a - b) for a, b in zip(params, prev))
                max_jump = max(max_jump, jump)
            prev = params
        print(f"  -> {vname}: max successive parameter jump = {max_jump:.4f} "
            f"(continuous if << 1)")
        print()

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "results", "ltc_curve.csv")
    with open(out, "w") as f:
        f.write("alpha,view,m00,m02,m11,m20,amplitude,rel_rms\n")
        for r in rows:
            f.write(f"{r[0]:.2f},{r[1]},{r[2]:.6f},{r[3]:.6f},"
                    f"{r[4]:.6f},{r[5]:.6f},{r[6]:.6f},{r[7]:.6f}\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
