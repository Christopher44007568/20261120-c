#pragma once

#include <cstddef>
#include <vector>

#include "math_util.h"
#include "rasterizer.h"

struct TrailConfig {
    int historyLength = 16;
    float headWidth = 6.0f;
    float tailWidth = 0.5f;
    float headAlpha = 0.85f;
    float tailAlpha = 0.0f;
    Color color = {0.25f, 0.65f, 1.0f, 1.0f};
    float miterLimit = 2.0f;
};

struct HistoryPoint {
    Vec2 pos;
};

struct Particle {
    int id = 0;
    Vec2 pos;
    Vec2 vel;
    std::vector<HistoryPoint> history;
    int count = 0;
    int head = 0;

    Particle() = default;
    Particle(int pid, Vec2 p, Vec2 v, int capacity)
        : id(pid), pos(p), vel(v), history(static_cast<size_t>(capacity)) {}

    void push(Vec2 p);
    // Oldest -> newest ordering over the valid history window.
    HistoryPoint at(int i, int capacity) const;
};

struct StripMesh {
    std::vector<Vertex> vertices;
    std::vector<int> indices;
    int particleId = -1;
};

struct DrawStats {
    int particleCount = 0;
    int renderedStrips = 0;
    int totalVertices = 0;
    int totalTriangles = 0;
    int totalIndices = 0;
    // One draw per strip without batching; one batched draw when merged.
    int drawBatchesPerStrip = 0;
    int drawBatchesMerged = 0;
};

class TrailSystem {
public:
    explicit TrailSystem(TrailConfig config) : config_(config) {}

    void spawn(const Particle& particle);
    void advance(const std::vector<Vec2>& nextPositions);

    StripMesh buildStrip(int particleIndex) const;
    std::vector<StripMesh> buildAllStrips() const;
    DrawStats stats() const;

    const TrailConfig& config() const { return config_; }
    const std::vector<Particle>& particles() const { return particles_; }

private:
    TrailConfig config_;
    std::vector<Particle> particles_;
};

// Rasterizes every strip mesh with alpha blending into the framebuffer.
void renderTrails(Framebuffer& fb, const std::vector<StripMesh>& meshes);

// Number of pixels covered by the strip triangles (pre-blend coverage test).
int countCoveragePixels(Framebuffer& probe, const std::vector<StripMesh>& meshes);
