#!/usr/bin/env bash
# Reproduce the full Poisson reconstruction experiment.
set -euo pipefail
cd "$(dirname "$0")"

# Open3D needs libusb-1.0; on systems where it is only available in a user
# directory (no root), prepend that directory to the loader path.
if [ -d "${HOME}/locallibs" ]; then
  export LD_LIBRARY_PATH="${HOME}/locallibs:${LD_LIBRARY_PATH:-}"
fi

python3 run_experiment.py
