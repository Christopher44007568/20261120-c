#include "scene.hpp"

#include <algorithm>
#include <cstdint>

namespace hzb {
namespace {

constexpr std::size_t kVerticesPerBox = 36;

class Rng {
public:
    explicit Rng(std::uint32_t seed) : state_(seed) {}

    std::uint32_t next() {
        state_ ^= state_ << 13;
        state_ ^= state_ >> 17;
        state_ ^= state_ << 5;
        return state_;
    }

    float unit() {
        return static_cast<float>(next() & 0x00FFFFFFU) / 16777216.0f;
    }

    float range(float low, float high) {
        return low + (high - low) * unit();
    }

private:
    std::uint32_t state_;
};

void appendVertex(std::vector<float>& vertices, float x, float y, float z) {
    vertices.push_back(x);
    vertices.push_back(y);
    vertices.push_back(z);
}

void appendTriangle(std::vector<float>& vertices, const Vec3& a, const Vec3& b, const Vec3& c) {
    appendVertex(vertices, a.x, a.y, a.z);
    appendVertex(vertices, b.x, b.y, b.z);
    appendVertex(vertices, c.x, c.y, c.z);
}

void appendBox(std::vector<float>& vertices, const Aabb& box) {
    const Vec3& lo = box.min;
    const Vec3& hi = box.max;
    const Vec3 p000{lo.x, lo.y, lo.z};
    const Vec3 p001{lo.x, lo.y, hi.z};
    const Vec3 p010{lo.x, hi.y, lo.z};
    const Vec3 p011{lo.x, hi.y, hi.z};
    const Vec3 p100{hi.x, lo.y, lo.z};
    const Vec3 p101{hi.x, lo.y, hi.z};
    const Vec3 p110{hi.x, hi.y, lo.z};
    const Vec3 p111{hi.x, hi.y, hi.z};

    appendTriangle(vertices, p000, p100, p110);
    appendTriangle(vertices, p000, p110, p010);
    appendTriangle(vertices, p001, p011, p111);
    appendTriangle(vertices, p001, p111, p101);
    appendTriangle(vertices, p000, p010, p011);
    appendTriangle(vertices, p000, p011, p001);
    appendTriangle(vertices, p100, p101, p111);
    appendTriangle(vertices, p100, p111, p110);
    appendTriangle(vertices, p000, p001, p101);
    appendTriangle(vertices, p000, p101, p100);
    appendTriangle(vertices, p010, p110, p111);
    appendTriangle(vertices, p010, p111, p011);
}

Aabb centeredBox(float x, float y, float z, float sx, float sy, float sz) {
    const Vec3 half{sx * 0.5f, sy * 0.5f, sz * 0.5f};
    const Vec3 center{x, y, z};
    return {center - half, center + half};
}

}  // namespace

Scene makeDenseIndoorScene() {
    Scene scene;
    scene.camera.position = {6.0f, 1.72f, 9.15f};
    scene.camera.target = {6.0f, 1.42f, -3.0f};
    scene.camera.verticalFovDegrees = 62.0f;

    auto addArchitecture = [&](const Aabb& box) { scene.architecture.push_back(box); };
    auto addObject = [&](const Aabb& box) { scene.objects.push_back(box); };

    addArchitecture({{-1.3f, -0.25f, -11.3f}, {13.3f, 0.0f, 10.3f}});
    addArchitecture({{-1.3f, 4.2f, -11.3f}, {13.3f, 4.45f, 10.3f}});
    addArchitecture({{-1.3f, 0.0f, -11.3f}, {-1.0f, 4.2f, 10.3f}});
    addArchitecture({{13.0f, 0.0f, -11.3f}, {13.3f, 4.2f, 10.3f}});
    addArchitecture({{-1.3f, 0.0f, -11.3f}, {13.3f, 4.2f, -10.95f}});
    addArchitecture({{-1.3f, 0.0f, 10.05f}, {13.3f, 4.2f, 10.3f}});

    constexpr float rackCentersX[] = {1.7f, 4.6f, 7.3f, 10.1f};
    constexpr float rackCentersZ[] = {5.8f, 4.0f, 2.2f, 0.4f, -1.4f, -3.2f, -5.0f, -6.8f, -8.6f};
    constexpr float itemOffsetsX[] = {-0.72f, -0.24f, 0.24f, 0.72f};
    constexpr float itemLevelsY[] = {0.55f, 1.38f, 2.21f};

    for (float rackX : rackCentersX) {
        for (float rackZ : rackCentersZ) {
            addArchitecture({{rackX - 1.13f, 0.18f, rackZ - 0.08f},
                              {rackX + 1.13f, 2.68f, rackZ + 0.04f}});
            addArchitecture({{rackX - 1.13f, 0.18f, rackZ + 0.09f},
                              {rackX + 1.13f, 0.26f, rackZ + 0.82f}});
            addArchitecture({{rackX - 1.13f, 1.01f, rackZ + 0.09f},
                              {rackX + 1.13f, 1.09f, rackZ + 0.82f}});
            addArchitecture({{rackX - 1.13f, 1.84f, rackZ + 0.09f},
                              {rackX + 1.13f, 1.92f, rackZ + 0.82f}});
            addArchitecture({{rackX - 1.13f, 2.67f, rackZ + 0.09f},
                              {rackX + 1.13f, 2.75f, rackZ + 0.82f}});

            for (float offsetX : itemOffsetsX) {
                for (float levelY : itemLevelsY) {
                    addObject(centeredBox(rackX + offsetX, levelY + 0.20f,
                                          rackZ + 0.46f, 0.34f, 0.38f, 0.34f));
                    addObject(centeredBox(rackX + offsetX, levelY + 0.20f,
                                          rackZ - 0.52f, 0.32f, 0.36f, 0.32f));
                }
            }
        }
    }

    addArchitecture({{0.4f, 0.0f, 7.2f}, {2.25f, 2.9f, 7.32f}});
    addArchitecture({{9.75f, 0.0f, 7.2f}, {11.6f, 2.9f, 7.32f}});
    addArchitecture({{5.15f, 0.0f, -0.25f}, {6.85f, 2.65f, -0.13f}});
    addArchitecture({{3.0f, 0.0f, -7.1f}, {4.8f, 2.8f, -6.98f}});
    addArchitecture({{7.4f, 0.0f, -7.1f}, {9.2f, 2.8f, -6.98f}});

    Rng rng(0x5EED1234U);
    for (int index = 0; index < 72; ++index) {
        const float x = rng.range(0.2f, 12.2f);
        const float y = rng.range(0.24f, 2.8f);
        const float z = rng.range(-9.9f, 8.5f);
        const float sx = rng.range(0.24f, 0.62f);
        const float sy = rng.range(0.24f, 0.60f);
        const float sz = rng.range(0.24f, 0.62f);
        addObject(centeredBox(x, y, z, sx, sy, sz));
    }

    for (int index = 0; index < 36; ++index) {
        const float x = rng.range(1.0f, 11.8f);
        const float z = rng.range(-9.4f, 4.8f);
        addArchitecture(centeredBox(x, rng.range(1.0f, 2.0f), z,
                                    rng.range(0.45f, 1.15f), rng.range(0.8f, 1.8f), 0.12f));
    }

    scene.vertices.reserve((scene.architecture.size() + scene.objects.size()) * kVerticesPerBox * 3);
    for (const Aabb& box : scene.architecture) {
        appendBox(scene.vertices, box);
    }
    scene.architectureVertexCount = scene.vertices.size() / 3;
    for (const Aabb& box : scene.objects) {
        appendBox(scene.vertices, box);
    }
    return scene;
}

}  // namespace hzb
