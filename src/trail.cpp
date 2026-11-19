#include "trail.h"

#include <algorithm>
#include <cmath>

void Particle::push(Vec2 p) {
    int capacity = static_cast<int>(history.size());
    if (count < capacity) {
        history[static_cast<size_t>(head)] = {p};
        head = (head + 1) % capacity;
        ++count;
    } else {
        history[static_cast<size_t>(head)] = {p};
        head = (head + 1) % capacity;
    }
}

HistoryPoint Particle::at(int i, int capacity) const {
    int start = (head - count + capacity) % capacity;
    return history[static_cast<size_t>((start + i) % capacity)];
}

void TrailSystem::spawn(const Particle& particle) { particles_.push_back(particle); }

void TrailSystem::advance(const std::vector<Vec2>& nextPositions) {
    for (size_t i = 0; i < particles_.size() && i < nextPositions.size(); ++i) {
        particles_[i].pos = nextPositions[i];
        particles_[i].push(nextPositions[i]);
    }
}

namespace {

struct Ring {
    Vec2 left;
    Vec2 right;
    float t;
    bool clamped;
};

float widthAt(float t, const TrailConfig& cfg) {
    return cfg.tailWidth + (cfg.headWidth - cfg.tailWidth) * t;
}

float alphaAt(float t, const TrailConfig& cfg) {
    return cfg.tailAlpha + (cfg.headAlpha - cfg.tailAlpha) * t;
}

Color colorAt(float t, const TrailConfig& cfg) {
    Color c = cfg.color;
    c.a = alphaAt(t, cfg);
    return c;
}

}  // namespace

StripMesh TrailSystem::buildStrip(int particleIndex) const {
    StripMesh mesh;
    const Particle& p = particles_[static_cast<size_t>(particleIndex)];
    mesh.particleId = p.id;
    int capacity = config_.historyLength;
    if (p.count < 2) {
        return mesh;
    }

    std::vector<Vec2> pts;
    pts.reserve(static_cast<size_t>(p.count));
    for (int i = 0; i < p.count; ++i) {
        pts.push_back(p.at(i, capacity).pos);
    }
    int rings = p.count;
    std::vector<Ring> ring;
    ring.reserve(static_cast<size_t>(rings));

    for (int i = 0; i < rings; ++i) {
        Vec2 tangent;
        if (i == 0) {
            tangent = normalize(pts[1] - pts[0]);
        } else if (i == rings - 1) {
            tangent = normalize(pts[rings - 1] - pts[rings - 2]);
        } else {
            tangent = normalize(normalize(pts[i] - pts[i - 1]) +
                                normalize(pts[i + 1] - pts[i]));
            if (length(tangent) <= 1e-6f) {
                tangent = normalize(pts[i + 1] - pts[i]);
            } else {
                tangent = normalize(tangent);
            }
        }
        Vec2 normal = perp(tangent);
        float t = rings > 1 ? static_cast<float>(i) /
                                  static_cast<float>(rings - 1)
                            : 1.0f;
        float halfWidth = 0.5f * widthAt(t, config_);

        // Standard miter length: 1 / sin(theta/2), where theta is the turn
        // angle between the two adjacent segment directions.
        float miterLen = 1.0f;
        bool clamped = false;
        if (i > 0 && i < rings - 1) {
            Vec2 dirIn = normalize(pts[i] - pts[i - 1]);
            Vec2 dirOut = normalize(pts[i + 1] - pts[i]);
            float cosHalf = std::sqrt(
                std::max(0.0f, 0.5f * (1.0f + dot(dirIn, dirOut))));
            if (cosHalf > 1e-4f) {
                miterLen = std::min(1.0f / cosHalf, config_.miterLimit);
                clamped = miterLen >= config_.miterLimit - 1e-5f;
            } else {
                miterLen = config_.miterLimit;
                clamped = true;
            }
        }
        Vec2 offset = normal * (halfWidth * miterLen);
        ring.push_back({pts[i] + offset, pts[i] - offset, t, clamped});
    }

    for (const Ring& r : ring) {
        mesh.vertices.push_back({r.left, colorAt(r.t, config_)});
        mesh.vertices.push_back({r.right, colorAt(r.t, config_)});
    }

    for (int i = 0; i < rings - 1; ++i) {
        int l0 = 2 * i;
        int r0 = 2 * i + 1;
        int l1 = 2 * (i + 1);
        int r1 = 2 * (i + 1) + 1;
        mesh.indices.insert(mesh.indices.end(), {l0, r0, l1, r0, r1, l1});
    }

    // Clamped miters would leave a wedge gap; fill it with a corner fan so
    // the strip stays watertight even on sharp turns.
    for (int i = 1; i < rings - 1; ++i) {
        if (!ring[i].clamped) {
            continue;
        }
        int centerIdx = static_cast<int>(mesh.vertices.size());
        mesh.vertices.push_back({pts[i], colorAt(ring[i].t, config_)});
        int l0 = 2 * (i - 1);
        int r0 = 2 * (i - 1) + 1;
        int l1 = 2 * i;
        int r1 = 2 * i + 1;
        mesh.indices.insert(mesh.indices.end(),
                            {l0, r0, centerIdx, l1, centerIdx, r1});
    }

    return mesh;
}

std::vector<StripMesh> TrailSystem::buildAllStrips() const {
    std::vector<StripMesh> meshes;
    meshes.reserve(particles_.size());
    for (size_t i = 0; i < particles_.size(); ++i) {
        StripMesh mesh = buildStrip(static_cast<int>(i));
        if (!mesh.indices.empty()) {
            meshes.push_back(std::move(mesh));
        }
    }
    return meshes;
}

DrawStats TrailSystem::stats() const {
    DrawStats s;
    s.particleCount = static_cast<int>(particles_.size());
    for (size_t i = 0; i < particles_.size(); ++i) {
        StripMesh mesh = buildStrip(static_cast<int>(i));
        if (mesh.indices.empty()) {
            continue;
        }
        ++s.renderedStrips;
        s.totalVertices += static_cast<int>(mesh.vertices.size());
        s.totalIndices += static_cast<int>(mesh.indices.size());
        s.totalTriangles += static_cast<int>(mesh.indices.size()) / 3;
    }
    s.drawBatchesPerStrip = s.renderedStrips;
    s.drawBatchesMerged = s.renderedStrips > 0 ? 1 : 0;
    return s;
}

void renderTrails(Framebuffer& fb, const std::vector<StripMesh>& meshes) {
    for (const StripMesh& mesh : meshes) {
        for (size_t i = 0; i + 2 < mesh.indices.size(); i += 3) {
            const Vertex& a = mesh.vertices[static_cast<size_t>(mesh.indices[i])];
            const Vertex& b =
                mesh.vertices[static_cast<size_t>(mesh.indices[i + 1])];
            const Vertex& c =
                mesh.vertices[static_cast<size_t>(mesh.indices[i + 2])];
            fb.drawTriangle(a, b, c);
        }
    }
}

int countCoveragePixels(Framebuffer& probe,
                        const std::vector<StripMesh>& meshes) {
    probe.clear({0, 0, 0, 0});
    for (const StripMesh& mesh : meshes) {
        for (size_t i = 0; i + 2 < mesh.indices.size(); i += 3) {
            const Vertex& a = mesh.vertices[static_cast<size_t>(mesh.indices[i])];
            const Vertex& b =
                mesh.vertices[static_cast<size_t>(mesh.indices[i + 1])];
            const Vertex& c =
                mesh.vertices[static_cast<size_t>(mesh.indices[i + 2])];
            Vertex oa{a.pos, {1, 1, 1, 1}};
            Vertex ob{b.pos, {1, 1, 1, 1}};
            Vertex oc{c.pos, {1, 1, 1, 1}};
            probe.drawTriangle(oa, ob, oc);
        }
    }
    int covered = 0;
    for (int y = 0; y < probe.height(); ++y) {
        for (int x = 0; x < probe.width(); ++x) {
            if (probe.readPixel(x, y).a > 0.0f) {
                ++covered;
            }
        }
    }
    return covered;
}
