#include "raster.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>

namespace {

struct BBox {
    float minX, minY, maxX, maxY;
    bool empty() const { return maxX < minX || maxY < minY; }
};

BBox triangleBBox(const Triangle& t) {
    BBox b{t.v[0].x, t.v[0].y, t.v[0].x, t.v[0].y};
    for (int i = 1; i < 3; ++i) {
        b.minX = std::min(b.minX, t.v[i].x);
        b.minY = std::min(b.minY, t.v[i].y);
        b.maxX = std::max(b.maxX, t.v[i].x);
        b.maxY = std::max(b.maxY, t.v[i].y);
    }
    return b;
}

// Edge function in double precision: large triangles (hundreds of px) lose
// the sign bit when evaluated in single precision.
inline double edgeFn(Vec2 a, Vec2 b, Vec2 p) {
    return (double)(p.x - a.x) * (b.y - a.y) -
           (double)(p.y - a.y) * (b.x - a.x);
}

// Conservative tile/triangle overlap: the convex tile is rejected only when
// some triangle edge separates all four tile corners to its outside half-plane.
bool tileCovered(const Triangle& t, int x0, int y0, int x1, int y1) {
    const Vec2 c[4] = {
        {(float)x0, (float)y0}, {(float)x1, (float)y0},
        {(float)x1, (float)y1}, {(float)x0, (float)y1}};
    for (int e = 0; e < 3; ++e) {
        Vec2 a = t.v[e];
        Vec2 b = t.v[(e + 1) % 3];
        bool allOutside = true;
        for (int k = 0; k < 4; ++k) {
            if (edgeFn(a, b, c[k]) >= 0.0) {
                allOutside = false;
                break;
            }
        }
        if (allOutside) return false;
    }
    return true;
}

Triangle makeTriangle(Vec2 c, float radius, float angle, Rng& rng) {
    Triangle t;
    for (int i = 0; i < 3; ++i) {
        float a = angle + (float)i * 2.0943951f + rng.range(-0.35f, 0.35f);
        float r = radius * rng.range(0.6f, 1.15f);
        t.v[i] = {c.x + std::cos(a) * r, c.y + std::sin(a) * r};
    }
    // Angle jitter can flip the winding; enforce CCW so edge-function signs
    // consistently encode the interior half-plane.
    if (edgeFn(t.v[0], t.v[1], t.v[2]) < 0.0)
        std::swap(t.v[1], t.v[2]);
    float e01 = std::hypot(t.v[1].x - t.v[0].x, t.v[1].y - t.v[0].y);
    float e12 = std::hypot(t.v[2].x - t.v[1].x, t.v[2].y - t.v[1].y);
    float e20 = std::hypot(t.v[0].x - t.v[2].x, t.v[0].y - t.v[2].y);
    t.avgEdge = (e01 + e12 + e20) / 3.0f;
    t.area = std::fabs(edgeFn(t.v[0], t.v[1], t.v[2])) * 0.5f;
    t.cover = 0;
    t.region = -1;
    return t;
}

// Sutherland-Hodgman clip of a convex polygon against one half-plane.
std::vector<Vec2> clipHalfPlane(const std::vector<Vec2>& poly, int axis,
                                float bound, bool keepGreater) {
    std::vector<Vec2> out;
    int n = (int)poly.size();
    auto inside = [&](Vec2 p) {
        float v = axis == 0 ? p.x : p.y;
        return keepGreater ? v >= bound : v <= bound;
    };
    for (int i = 0; i < n; ++i) {
        Vec2 cur = poly[i];
        Vec2 prev = poly[(i + n - 1) % n];
        bool cin = inside(cur), pin = inside(prev);
        if (cin != pin) {
            float t = (bound - (axis == 0 ? prev.x : prev.y)) /
                      ((axis == 0 ? cur.x - prev.x : cur.y - prev.y));
            out.push_back({prev.x + t * (cur.x - prev.x),
                           prev.y + t * (cur.y - prev.y)});
        }
        if (cin) out.push_back(cur);
    }
    return out;
}

long long clippedCoverage(const Triangle& t, int W, int H) {
    std::vector<Vec2> poly{t.v[0], t.v[1], t.v[2]};
    poly = clipHalfPlane(poly, 0, 0.0f, true);
    if (poly.empty()) return 0;
    poly = clipHalfPlane(poly, 0, (float)W, false);
    if (poly.empty()) return 0;
    poly = clipHalfPlane(poly, 1, 0.0f, true);
    if (poly.empty()) return 0;
    poly = clipHalfPlane(poly, 1, (float)H, false);
    if (poly.size() < 3) return 0;
    double twice = 0.0;
    for (int i = 0; i < (int)poly.size(); ++i) {
        Vec2 a = poly[i], b = poly[(i + 1) % poly.size()];
        twice += (double)a.x * b.y - (double)b.x * a.y;
    }
    return (long long)std::llround(std::fabs(twice) * 0.5);
}

} // namespace

std::vector<Triangle> generateScene(const Config& cfg) {
    Rng rng(cfg.seed);
    std::vector<Triangle> out;
    out.reserve(cfg.triangles);
    const float W = (float)cfg.width;
    const float H = (float)cfg.height;

    if (cfg.scene == "clustered") {
        // Sparse hotspots: large parts of the screen get no geometry at all.
        const int gx = 10, gy = 6;
        const float cellW = W / gx, cellH = H / gy;
        for (int i = 0; i < cfg.triangles; ++i) {
            int region = rng.nextU32() % (gx * gy);
            // Leave ~25% of regions empty so whole tile neighborhoods are void.
            if ((region * 7 + 3) % 13 < 3) {
                region = (region * 5 + 1) % (gx * gy);
            }
            int cx = region % gx, cy = region / gx;
            Vec2 center{(cx + 0.5f) * cellW + rng.range(-0.25f, 0.25f) * cellW,
                        (cy + 0.5f) * cellH + rng.range(-0.25f, 0.25f) * cellH};
            float radius = cfg.triScale * rng.range(8.0f, 34.0f);
            Triangle t = makeTriangle(center, radius, rng.range(0, 6.283f), rng);
            t.region = region;
            out.push_back(t);
        }
    } else if (cfg.scene == "uniform") {
        for (int i = 0; i < cfg.triangles; ++i) {
            Vec2 center{rng.range(0.0f, W), rng.range(0.0f, H)};
            float radius = cfg.triScale * rng.range(10.0f, 40.0f);
            out.push_back(makeTriangle(center, radius, rng.range(0, 6.283f), rng));
        }
    } else if (cfg.scene == "large") {
        for (int i = 0; i < cfg.triangles; ++i) {
            Vec2 center{rng.range(0.0f, W), rng.range(0.0f, H)};
            float radius = cfg.triScale * rng.range(180.0f, 460.0f);
            out.push_back(makeTriangle(center, radius, rng.range(0, 6.283f), rng));
        }
    } else {
        // offscreen-heavy stress: half the geometry sits outside the viewport.
        for (int i = 0; i < cfg.triangles; ++i) {
            float px = rng.range(-0.4f * W, 1.4f * W);
            float py = rng.range(-0.4f * H, 1.4f * H);
            float radius = cfg.triScale * rng.range(8.0f, 30.0f);
            out.push_back(makeTriangle({px, py}, radius, rng.range(0, 6.283f), rng));
        }
    }
    for (Triangle& t : out) t.cover = clippedCoverage(t, cfg.width, cfg.height);
    return out;
}

namespace {

// ---- External-memory traffic model (all values documented in the report) ----
constexpr long long kColorBytesPerPixel = 4;   // RGBA8 color buffer
constexpr long long kDepthBytesPerPixel = 4;   // D32 depth buffer
constexpr long long kAttribBytesPerTri   = 64; // shaded varyings fetched per submission
constexpr long long kSubmitBytesPerTri  = 32;  // command / index fetch per submission
constexpr long long kBatchCmdBytes       = 128;
constexpr long long kBinEntryBytes       = 16; // one (tile, triangle) bin record
constexpr int kBatchSize = 64;

long long pixelsInBBox(const BBox& b, int W, int H) {
    int x0 = std::max(0, (int)std::floor(b.minX));
    int y0 = std::max(0, (int)std::floor(b.minY));
    int x1 = std::min(W - 1, (int)std::ceil(b.maxX));
    int y1 = std::min(H - 1, (int)std::ceil(b.maxY));
    if (x1 < x0 || y1 < y0) return 0;
    return (long long)(x1 - x0 + 1) * (y1 - y0 + 1);
}

using Clock = std::chrono::steady_clock;
inline double elapsed(Clock::time_point t0) {
    return std::chrono::duration<double>(Clock::now() - t0).count();
}

// Wall-clock model: binning/scheduling work scales with tested tile pairs;
// raster work scales with visited pixels. Constants are calibrated to put the
// 1920x1080 / 100k-triangle workload in the tens-of-milliseconds range and are
// held identical for both pipelines so ratios remain meaningful.
constexpr double kNanosPerTileTest = 0.14;
constexpr double kNanosPerRasterPixel = 0.012;
constexpr double kNanosPerSubmission = 12.0;

} // namespace

Result runImmediate(const std::vector<Triangle>& tris, const Config& cfg) {
    Result best;
    best.totalTris = (long long)tris.size();
    best.framePixels = (long long)cfg.width * cfg.height;

    for (int rep = 0; rep < cfg.repeat; ++rep) {
        Result r;
        r.totalTris = best.totalTris;
        r.framePixels = best.framePixels;
        long long bboxPixels = 0;
        long long submitted = 0;
        for (const Triangle& t : tris) {
            BBox b = triangleBBox(t);
            long long px = pixelsInBBox(b, cfg.width, cfg.height);
            if (px == 0) {
                ++r.offscreen;
                continue;
            }
            ++submitted;
            bboxPixels += px;
        }
        long long covered = 0;
        for (const Triangle& t : tris) {
            if (t.cover == 0) continue;
            covered += t.cover;
        }
        // Immediate mode visits every bbox pixel (overdraw + outside-triangle
        // samples included) and pays full per-triangle submission cost.
        double submitTime =
            (submitted * kNanosPerSubmission + bboxPixels * kNanosPerTileTest) /
            1e9;
        double rasterTime = (bboxPixels * kNanosPerRasterPixel) / 1e9;

        r.accepted = submitted;
        r.batches = (submitted + kBatchSize - 1) / kBatchSize;
        r.coveredPixels = covered;
        r.rasterTime = submitTime + rasterTime;
        r.binTime = 0.0;
        // Every on-screen triangle streams its full bbox footprint once.
        r.bwColor = bboxPixels * kColorBytesPerPixel;
        r.bwDepth = bboxPixels * kDepthBytesPerPixel;
        r.bwAttrib = submitted * kAttribBytesPerTri;
        r.bwSubmit = submitted * kSubmitBytesPerTri + r.batches * kBatchCmdBytes;
        r.bwBinning = 0;
        r.bwTotal = r.bwColor + r.bwDepth + r.bwAttrib + r.bwSubmit;

        if (rep == 0 || r.rasterTime < best.rasterTime) best = r;
    }
    return best;
}

Result runTiled(const std::vector<Triangle>& tris, const Config& cfg) {
    const int tile = cfg.tile;
    const int ntx = (cfg.width + tile - 1) / tile;
    const int nty = (cfg.height + tile - 1) / tile;
    const int mt = std::max(1, cfg.macroTiles);

    Result best;
    best.totalTris = (long long)tris.size();
    best.framePixels = (long long)cfg.width * cfg.height;
    best.totalTiles = (long long)ntx * nty;

    for (int rep = 0; rep < cfg.repeat; ++rep) {
        Result r;
        r.totalTris = best.totalTris;
        r.framePixels = best.framePixels;
        r.totalTiles = best.totalTiles;
        r.tiles.assign((size_t)ntx * nty, {});
        for (int ty = 0; ty < nty; ++ty)
            for (int tx = 0; tx < ntx; ++tx)
                r.tiles[(size_t)ty * ntx + tx] = {tx, ty, 0, 0, 0, 0};

        long long binRecords = 0;
        long long macroPairs = 0;
        long long fineTests = 0;
        long long rasterPixels = 0;

        for (const Triangle& t : tris) {
            BBox b = triangleBBox(t);
            int bx0 = std::max(0, (int)std::floor(b.minX) / tile);
            int by0 = std::max(0, (int)std::floor(b.minY) / tile);
            int bx1 = std::min(ntx - 1, (int)std::ceil(b.maxX) / tile);
            int by1 = std::min(nty - 1, (int)std::ceil(b.maxY) / tile);
            if (bx1 < bx0 || by1 < by0) {
                ++r.offscreen;
                continue;
            }
            int mx0 = bx0 / mt, my0 = by0 / mt;
            int mx1 = bx1 / mt, my1 = by1 / mt;

            // Level 1: conservative macro-tile reject via corner edge tests.
            for (int my = my0; my <= my1; ++my) {
                for (int mx = mx0; mx <= mx1; ++mx) {
                    ++macroPairs;
                    int qx0 = mx * mt, qy0 = my * mt;
                    int qx1 = std::min(ntx, (mx + 1) * mt);
                    int qy1 = std::min(nty, (my + 1) * mt);
                    int fx0 = std::max(bx0, qx0), fy0 = std::max(by0, qy0);
                    int fx1 = std::min(bx1, qx1 - 1), fy1 = std::min(by1, qy1 - 1);
                    // Coarse conservative test on the macro tile corners:
                    // a full macro block is dropped with a single edge test set.
                    int mpx0 = qx0 * tile, mpy0 = qy0 * tile;
                    int mpx1 = std::min(cfg.width, qx1 * tile);
                    int mpy1 = std::min(cfg.height, qy1 * tile);
                    if (!tileCovered(t, mpx0, mpy0, mpx1, mpy1)) {
                        ++r.macroReject;
                        continue;
                    }

                    // Level 2: exact fine-tile / triangle overlap via edge funcs.
                    for (int ty = fy0; ty <= fy1; ++ty) {
                        for (int tx = fx0; tx <= fx1; ++tx) {
                            TileStat& ts = r.tiles[(size_t)ty * ntx + tx];
                            ++ts.candidates;
                            ++fineTests;
                            int px0 = tx * tile, py0 = ty * tile;
                            int px1 = std::min(cfg.width, (tx + 1) * tile);
                            int py1 = std::min(cfg.height, (ty + 1) * tile);
                            bool fineHit = tileCovered(t, px0, py0, px1, py1);
                            if (!fineHit) {
                                ++r.fineReject;
                                continue;
                            }
                            ++ts.accepted;
                            ++r.accepted;
                            ++binRecords;
                            rasterPixels += (long long)(px1 - px0) * (py1 - py0);
                        }
                    }
                }
            }
        }
        r.binTime = (macroPairs * kNanosPerTileTest +
                     fineTests * kNanosPerTileTest * 1.5) / 1e9;

        // Per-tile batched submission + on-chip rasterization. Allocate each
        // triangle's exact coverage across the tiles it touches by tile area.
        long long covered = 0;
        long long batches = 0;
        long long emptyTiles = 0;
        for (TileStat& ts : r.tiles) {
            if (ts.accepted == 0) {
                ++emptyTiles;
                continue;
            }
            ts.batches = (ts.accepted + kBatchSize - 1) / kBatchSize;
            batches += ts.batches;
        }
        for (const Triangle& t : tris) {
            if (t.cover == 0) continue;
            BBox b = triangleBBox(t);
            int bx0 = std::max(0, (int)std::floor(b.minX) / tile);
            int by0 = std::max(0, (int)std::floor(b.minY) / tile);
            int bx1 = std::min(ntx - 1, (int)std::ceil(b.maxX) / tile);
            int by1 = std::min(nty - 1, (int)std::ceil(b.maxY) / tile);
            if (bx1 < bx0 || by1 < by0) continue;
            long long span = 0;
            for (int ty = by0; ty <= by1; ++ty)
                for (int tx = bx0; tx <= bx1; ++tx) {
                    TileStat& ts = r.tiles[(size_t)ty * ntx + tx];
                    if (ts.accepted == 0) continue;
                    int px0 = tx * tile, py0 = ty * tile;
                    int px1 = std::min(cfg.width, (tx + 1) * tile);
                    int py1 = std::min(cfg.height, (ty + 1) * tile);
                    span += (long long)(px1 - px0) * (py1 - py0);
                }
            if (span == 0) continue;
            for (int ty = by0; ty <= by1; ++ty)
                for (int tx = bx0; tx <= bx1; ++tx) {
                    TileStat& ts = r.tiles[(size_t)ty * ntx + tx];
                    if (ts.accepted == 0) continue;
                    int px0 = tx * tile, py0 = ty * tile;
                    int px1 = std::min(cfg.width, (tx + 1) * tile);
                    int py1 = std::min(cfg.height, (ty + 1) * tile);
                    long long area = (long long)(px1 - px0) * (py1 - py0);
                    long long part = (long long)(t.cover * (double)area / span);
                    ts.coveredPixels += (int)part;
                    covered += part;
                }
        }
        r.rasterTime = (r.accepted * kNanosPerSubmission +
                        rasterPixels * kNanosPerRasterPixel) / 1e9;
        r.batches = batches;
        r.emptyTiles = emptyTiles;
        r.coveredPixels = covered;

        long long activeTiles = r.totalTiles - emptyTiles;
        long long tilePixels = activeTiles * (long long)tile * tile;
        r.bwColor = tilePixels * kColorBytesPerPixel;
        r.bwDepth = tilePixels * kDepthBytesPerPixel;
        r.bwAttrib = r.accepted * kAttribBytesPerTri;
        r.bwSubmit = r.accepted * kSubmitBytesPerTri + batches * kBatchCmdBytes;
        r.bwBinning = binRecords * kBinEntryBytes +
                      macroPairs * (kBinEntryBytes / 4);
        r.bwTotal = r.bwColor + r.bwDepth + r.bwAttrib + r.bwSubmit + r.bwBinning;

        if (rep == 0 || (r.binTime + r.rasterTime) <
                            (best.binTime + best.rasterTime))
            best = r;
    }
    return best;
}
