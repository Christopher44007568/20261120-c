#!/usr/bin/env python3
from __future__ import annotations

import math
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_experiments as exp  # noqa: E402


def render(scene: str, method: str, out: Path) -> None:
    subprocess.run([
        str(ROOT / "rpt"), "render", "--scene", scene, "--integrator", method,
        "--spp", "24", "--width", "64", "--height", "48", "--threads", "4",
        "--out", str(out), "--seed", "77",
    ], check=True, stdout=subprocess.DEVNULL)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rpt_smoke_") as temp_name:
        temp = Path(temp_name)
        render("indirect", "pt", temp / "pt")
        render("indirect", "bdpt", temp / "bdpt")
        _, _, pt = exp.read_pfm(temp / "pt.pfm")
        _, _, bdpt = exp.read_pfm(temp / "bdpt.pfm")
        pt_mean = sum(exp.luminance(p) for p in pt) / len(pt)
        bdpt_mean = sum(exp.luminance(p) for p in bdpt) / len(bdpt)
        relative = abs(pt_mean - bdpt_mean) / max(pt_mean, 1e-9)
        assert relative < 0.20, f"PT/BDPT mean mismatch: {relative:.3f}"

        render("caustic", "bdpt", temp / "caustic")
        _, _, caustic = exp.read_pfm(temp / "caustic.pfm")
        assert all(math.isfinite(v) and v >= 0.0 for p in caustic for v in p)
        assert max(exp.luminance(p) for p in caustic) > 1.0
    print(f"smoke test passed; indirect mean delta={relative:.3%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
