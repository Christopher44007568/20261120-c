#!/usr/bin/env bash
# GLSL -> SPIR-V transpile, reflection, layout validation and
# consistency comparison. Outputs land in artifacts/.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 tools/pipeline.py
python3 tools/compare.py
python3 tools/gen_report.py
