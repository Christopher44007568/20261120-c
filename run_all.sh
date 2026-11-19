#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

$PY src/run_galaxy.py
$PY src/run_trees.py
$PY src/make_contact_sheets.py
$PY src/verify.py
