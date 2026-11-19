"""Convert VTK vtkMarchingCellsContourCases.cxx hexahedron table to a Python module."""
import re
import sys


def main(src_path, out_path):
    text = open(src_path).read()
    m = re.search(r"HexahedronCase HexahedronCases\[256\] = \{(.*?)\n\};", text, re.S)
    if not m:
        raise SystemExit("table not found")
    body = m.group(1)
    rows = re.findall(r"\{([^}]*)\}", body)
    if len(rows) != 256:
        raise SystemExit(f"expected 256 rows, got {len(rows)}")
    lines = [
        "# Auto-generated from VTK vtkMarchingCellsContourCases.cxx (BSD-3-Clause).",
        "# Each entry: triangles as cube-edge indices, -1 padding removed.",
        "MC_TRI_TABLE = [",
    ]
    for row in rows:
        vals = [int(v) for v in row.replace("/*", " ").split("*/")[0].split(",")]
        vals = [v for v in vals if v != -1]
        lines.append(f"    {vals},")
    lines.append("]")
    open(out_path, "w").write("\n".join(lines) + "\n")
    print(f"wrote {out_path} with {len(rows)} cases")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
