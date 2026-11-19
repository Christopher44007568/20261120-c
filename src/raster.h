#pragma once
#include <cstdint>
#include <string>
#include <vector>

struct Vec2 {
    float x, y;
};

struct Triangle {
    Vec2 v[3];
    float area;          // absolute screen-space area
    float avgEdge;       // mean edge length, used as triangle-size class proxy
    long long cover;     // exact clipped pixel-coverage estimate (pixel units)
    int   region;        // spatial region id (for clustered scenes)
};

struct Config {
    int   width = 1920;
    int   height = 1080;
    int   tile = 32;
    int   macroTiles = 4;     // fine tiles per macro tile per axis
    std::string scene = "clustered";
    int   triangles = 100000;
    unsigned seed = 1234;
    float triScale = 1.0f;    // multiplies generated triangle size
    int   repeat = 3;         // timed repetitions
};

struct TileStat {
    int tx, ty;
    int candidates;   // triangles surviving macro-level bbox test
    int accepted;     // triangles with real coverage (edge-function test)
    int batches;      // draw batches issued for the tile
    int coveredPixels;
};

struct Result {
    // timing (seconds), minimum over repetitions
    double binTime = 0;
    double rasterTime = 0;
    // counts
    long long totalTris = 0;
    long long offscreen = 0;
    long long macroReject = 0;   // rejected at macro-tile bbox level
    long long fineReject = 0;    // candidate but no fine-tile coverage
    long long accepted = 0;      // total (triangle, fine tile) coverage pairs
    long long emptyTiles = 0;
    long long totalTiles = 0;
    long long batches = 0;
    long long coveredPixels = 0;
    long long framePixels = 0;
    // bandwidth model (bytes)
    long long bwColor = 0;
    long long bwDepth = 0;
    long long bwAttrib = 0;
    long long bwSubmit = 0;
    long long bwBinning = 0;
    long long bwTotal = 0;
    std::vector<TileStat> tiles;
};

std::vector<Triangle> generateScene(const Config& cfg);

// Immediate-mode baseline: every on-screen triangle is submitted once and
// rasterized over its full bounding box against the whole framebuffer.
Result runImmediate(const std::vector<Triangle>& tris, const Config& cfg);

// Hierarchical tile rasterizer: macro-tile bounding-box reject, then per-fine-tile
// edge-function coverage test; only covered triangles are submitted per tile.
Result runTiled(const std::vector<Triangle>& tris, const Config& cfg);

// Deterministic xorshift PRNG so scenes are reproducible.
class Rng {
public:
    explicit Rng(uint64_t s) : state(s ? s : 0x9e3779b97f4a7c15ULL) {}
    uint32_t nextU32() {
        uint64_t x = state;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        state = x;
        return static_cast<uint32_t>(x >> 32);
    }
    float nextFloat() { return (nextU32() >> 8) * (1.0f / 16777216.0f); }
    float range(float lo, float hi) { return lo + nextFloat() * (hi - lo); }
private:
    uint64_t state;
};
