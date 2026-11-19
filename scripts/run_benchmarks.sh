#!/usr/bin/env bash
# Reproduces every experiment in the report.
set -euo pipefail
cd "$(dirname "$0")/.."
BIN=./build/tile_rast
OUT=results
mkdir -p "$OUT"

TRIS=${TRIS:-100000}

echo "== 1. head-to-head comparison (tile=32, clustered $TRIS tris) =="
$BIN compare --tris "$TRIS" --scene clustered --tile 32 | tee "$OUT/compare_clustered.txt"

echo
echo "== 2. tile-size sweeps over four scene classes =="
for scene in clustered uniform large offscreen; do
    $BIN sweep --tris "$TRIS" --scene "$scene" "$OUT/sweep_${scene}.csv"
done

echo
echo "== 3. per-tile triangle counts and draw batches (tile=32) =="
$BIN tiles --tris "$TRIS" --scene clustered --tile 32 "$OUT/tiles_32.csv"
$BIN tiles --tris "$TRIS" --scene clustered --tile 128 "$OUT/tiles_128.csv"
for t in 16 32 64 128; do
    $BIN tilehist --tris "$TRIS" --scene clustered --tile "$t" \
        > "$OUT/tilehist_${t}.txt"
done
head -1 "$OUT/tilehist_32.txt"

echo
echo "== 4. tile-size x triangle-size balance matrix =="
$BIN matrix --tris "$TRIS" --scene clustered "$OUT/matrix_clustered.csv"

echo
echo "== 5. large-scale culling scaling (10k .. 1m triangles) =="
$BIN scaling --scene clustered --tile 32 "$OUT/scaling.csv"
column -t -s, "$OUT/scaling.csv"

echo
echo "== 6. SVG charts =="
python3 scripts/make_charts.py
echo "done. artifacts in $OUT/"
