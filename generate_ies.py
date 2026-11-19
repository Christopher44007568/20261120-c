"""Generate two synthetic LM-63 IES files with identical total flux:
  ies/spot.ies      - narrow symmetric spotlight (rotationally symmetric)
  ies/wallwash.ies  - asymmetric wall-wash (bilateral symmetry, throws +x)
"""

import math
import os

from ies_toolkit import IESFile

TARGET_FLUX_LM = 1500.0


def write_ies(path, ies, test_label, description):
    lines = [
        "IESNA:LM-63-2002",
        "[TEST] %s" % test_label,
        "[MANUFAC] SyntheticLab",
        "[LUMINAIRE] %s" % description,
        "TILT=NONE",
        "1 %d %.1f %.1f %d %d %d %d %.2f %.2f %.2f" % (
            ies.num_lamps, ies.lumens_per_lamp, ies.multiplier,
            ies.n_vertical, ies.n_horizontal, ies.photometric_type,
            ies.units_type, ies.width, ies.length, ies.height),
        "%.3f %.1f %.1f" % (ies.ballast_factor, 0.0, ies.input_watts),
    ]
    lines.append(" ".join("%.1f" % a for a in ies.vertical_angles))
    lines.append(" ".join("%.1f" % a for a in ies.horizontal_angles))
    for h in range(ies.n_horizontal):
        lines.append(" ".join("%.3f" % c for c in ies.candela[h]))
    with open(path, "w", encoding="ascii") as fh:
        fh.write("\n".join(lines) + "\n")


def normalize_flux(ies, target_lm):
    flux = ies.total_flux()
    scale = target_lm / flux
    ies.candela = [[c * scale for c in row] for row in ies.candela]
    ies.lumens_per_lamp = target_lm
    return ies


def make_spot():
    ies = IESFile()
    ies.num_lamps = 1
    ies.multiplier = 1.0
    ies.photometric_type = 1
    ies.units_type = 1
    ies.ballast_factor = 1.0
    ies.input_watts = 17.0
    ies.vertical_angles = [5.0 * i for i in range(19)]   # 0..90
    ies.horizontal_angles = [0.0]                        # full symmetry
    ies.n_vertical = len(ies.vertical_angles)
    ies.n_horizontal = 1
    sigma = math.radians(14.0)
    col = []
    for deg in ies.vertical_angles:
        th = math.radians(deg)
        col.append(math.exp(-0.5 * (th / sigma) ** 2))
    ies.candela = [col]
    return normalize_flux(ies, TARGET_FLUX_LM)


def make_wallwash():
    ies = IESFile()
    ies.num_lamps = 1
    ies.multiplier = 1.0
    ies.photometric_type = 1
    ies.units_type = 1
    ies.ballast_factor = 1.0
    ies.input_watts = 17.0
    ies.vertical_angles = [5.0 * i for i in range(19)]   # 0..90
    ies.horizontal_angles = [15.0 * i for i in range(13)]  # 0..180, x2 symm
    ies.n_vertical = len(ies.vertical_angles)
    ies.n_horizontal = len(ies.horizontal_angles)
    candela = []
    for phi in ies.horizontal_angles:
        # throw factor: 1 toward phi=0 (wall side), ~0.15 behind
        throw = 0.15 + 0.85 * (0.5 + 0.5 * math.cos(math.radians(phi))) ** 2
        col = []
        for deg in ies.vertical_angles:
            th = math.radians(deg)
            # batwing: peaks near 45 deg so light climbs the wall
            lobe = math.exp(-0.5 * ((th - math.radians(45.0))
                                    / math.radians(28.0)) ** 2)
            col.append(throw * (0.25 + 0.75 * lobe))
        candela.append(col)
    ies.candela = candela
    return normalize_flux(ies, TARGET_FLUX_LM)


def main():
    os.makedirs("ies", exist_ok=True)
    spot = make_spot()
    wash = make_wallwash()
    write_ies("ies/spot.ies", spot, "LAB-SPOT-001",
              "narrow symmetric spotlight")
    write_ies("ies/wallwash.ies", wash, "LAB-WASH-001",
              "asymmetric wall-wash, throw toward +x")
    print("spot.ies     flux = %.2f lm  peak = %.1f cd"
          % (spot.total_flux(), max(max(r) for r in spot.candela)))
    print("wallwash.ies flux = %.2f lm  peak = %.1f cd"
          % (wash.total_flux(), max(max(r) for r in wash.candela)))


if __name__ == "__main__":
    main()
