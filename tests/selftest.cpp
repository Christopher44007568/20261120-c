#include "../src/raster.h"
#include <cassert>
#include <cstdio>
#include <cmath>

int main() {
    // 1. Determinism: identical seeds must produce identical geometry.
    Config c;
    c.scene = "clustered";
    c.triangles = 5000;
    auto a = generateScene(c);
    auto b = generateScene(c);
    assert(a.size() == b.size());
    for (size_t i = 0; i < a.size(); ++i)
        for (int k = 0; k < 3; ++k) {
            assert(a[i].v[k].x == b[i].v[k].x);
            assert(a[i].v[k].y == b[i].v[k].y);
        }

    // 2. Coverage must match between pipelines within rounding tolerance.
    Result imm = runImmediate(a, c);
    Result tiled = runTiled(a, c);
    double rel = std::fabs((double)imm.coveredPixels - tiled.coveredPixels) /
                 std::max(1LL, imm.coveredPixels);
    std::printf("coverage imm=%lld tiled=%lld relErr=%.4f\n",
                imm.coveredPixels, tiled.coveredPixels, rel);
    assert(rel < 0.01);

    // 3. Tiled culling never accepts more work than bbox tile pairs, and
    //    every active tile carries at least one batch.
    long long active = 0;
    for (const TileStat& t : tiled.tiles) {
        if (t.accepted > 0) {
            ++active;
            assert(t.batches >= 1);
        } else {
            assert(t.batches == 0 && t.coveredPixels == 0);
        }
    }
    assert(active == tiled.totalTiles - tiled.emptyTiles);

    // 4. Offscreen-heavy scene must reject a large fraction of geometry.
    Config o = c;
    o.scene = "offscreen";
    auto ot = generateScene(o);
    Result oi = runImmediate(ot, o);
    assert(oi.offscreen > (long long)(ot.size() * 0.2));

    // 5. Larger tiles reject fewer fine tests (cull benefit shrinks).
    Config s = c;
    s.tile = 16;
    Result r16 = runTiled(a, s);
    s.tile = 128;
    Result r128 = runTiled(a, s);
    auto rate = [](const Result& r) {
        long long tested = r.macroReject + r.fineReject + r.accepted;
        return 1.0 - (double)r.accepted / std::max(1LL, tested);
    };
    std::printf("cull rate tile16=%.3f tile128=%.3f\n", rate(r16), rate(r128));
    assert(rate(r16) > rate(r128));

    std::puts("all self-tests passed");
    return 0;
}
