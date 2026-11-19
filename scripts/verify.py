#!/usr/bin/env python3
"""Generate twice, compare artifacts, and publish the reproducible run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], check: bool = True) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=check)


def finalize(run_dir: Path) -> None:
    run(
        [
            sys.executable,
            str(Path(__file__).with_name("finalize.py")),
            str(run_dir),
        ]
    )


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def comparison_rows(run1: Path, run2: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    selected = []
    for path in sorted(run1.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(run1)
        if relative.name in {"report.md", "reproducibility.csv"}:
            continue
        selected.append(relative)

    for relative in selected:
        first = sha256(run1 / relative)
        second = sha256(run2 / relative)
        rows.append(
            {
                "check": f"sha256:{relative.as_posix()}",
                "run1": first,
                "run2": second,
                "absolute_difference": "0" if first == second else "1",
                "pass": "true" if first == second else "false",
            }
        )

    for relative, fields in (
        ("data/pixel_summary.csv", ("mean_relative_error",
                                    "p99_relative_error",
                                    "normalized_rmse")),
        ("data/flux_validation.csv", ("relative_error",)),
        ("data/penumbra.csv", ("width_error_m",)),
    ):
        first_rows = read_rows(run1 / relative)
        second_rows = read_rows(run2 / relative)
        for first, second in zip(first_rows, second_rows):
            for field in fields:
                first_value = first[field]
                second_value = second[field]
                difference = abs(float(first_value) - float(second_value))
                rows.append(
                    {
                        "check": f"{first['shape']}:{field}",
                        "run1": f"{float(first_value):.12g}",
                        "run2": f"{float(second_value):.12g}",
                        "absolute_difference": f"{difference:.3e}",
                        "pass": "true" if difference == 0.0 else "false",
                    }
                )
    return rows


def write_reproducibility(run_dir: Path,
                          rows: list[dict[str, str]]) -> None:
    path = run_dir / "data" / "reproducibility.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "check",
                "run1",
                "run2",
                "absolute_difference",
                "pass",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)


def publish(run_dir: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("data", "images"):
        target = destination / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(run_dir / name, target)
    shutil.copy2(run_dir / "report.md", destination / "report.md")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, default=Path("build/area_lights"))
    parser.add_argument("--destination", type=Path, default=Path("artifacts"))
    parser.add_argument("--pixel-samples", type=int, default=131072)
    parser.add_argument("--flux-samples", type=int, default=2000000)
    parser.add_argument("--penumbra-samples", type=int, default=131072)
    args = parser.parse_args()

    root = Path("build") / "verify"
    if root.exists():
        shutil.rmtree(root)
    run1 = root / "run1"
    run2 = root / "run2"
    common = [
        str(args.binary),
        "--pixel-samples",
        str(args.pixel_samples),
        "--flux-samples",
        str(args.flux_samples),
        "--penumbra-samples",
        str(args.penumbra_samples),
    ]

    run(common + ["--out", str(run1)], check=False)
    if not (run1 / "data" / "parameters.csv").exists():
        raise SystemExit("first generation failed before producing data")
    finalize(run1)
    run(common + ["--out", str(run2)], check=False)
    if not (run2 / "data" / "parameters.csv").exists():
        raise SystemExit("second generation failed before producing data")
    finalize(run2)

    rows = comparison_rows(run1, run2)
    write_reproducibility(run1, rows)
    finalize(run1)
    publish(run1, args.destination)

    validation_pass = all(
        row["pass"] == "true"
        for relative in (
            "data/pixel_summary.csv",
            "data/flux_validation.csv",
            "data/penumbra.csv",
        )
        for row in read_rows(run1 / relative)
    )
    passed = (
        all(row["pass"] == "true" for row in rows) and validation_pass
    )
    print(
        f"reproducibility: {sum(row['pass'] == 'true' for row in rows)}"
        f"/{len(rows)} checks passed",
        flush=True,
    )
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
