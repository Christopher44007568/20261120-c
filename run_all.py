"""Run all validation and rendering for the Ashikhmin velvet BRDF project."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import validate
import render

if __name__ == "__main__":
    rc = validate.main()
    render.main()
    print("DONE" if rc == 0 else "VALIDATION FAILED")
    sys.exit(rc)
