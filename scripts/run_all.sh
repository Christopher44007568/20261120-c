#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== unit tests =="
python3 -m unittest discover -s tests -v

echo "== L-system depth experiments =="
python3 scripts/run_experiments.py >/dev/null

echo "== rule parameter sweep =="
python3 scripts/rule_sweep.py >/dev/null

echo "== mip heatmap / clamp verification =="
python3 scripts/mip_heatmap.py
