#pragma once
#include "bvh.h"
#include <array>
#include <random>

struct BoxedPrim {
    AABB b;
    AABB bounds() const { return b; }
};

// ---- procedural meshes (local space, built once per unique mesh) ----
inline std::vector<Tri> makeIcosphere(int subdiv) {
    const float t = (1.0f + std::sqrt(5.0f)) / 2.0f;
    std::vector<Vec3> v = {
        {-1, t, 0}, {1, t, 0}, {-1, -t, 0}, {1, -t, 0},
        {0, -1, t}, {0, 1, t}, {0, -1, -t}, {0, 1, -t},
        {t, 0, -1}, {t, 0, 1}, {-t, 0, -1}, {-t, 0, 1}};
    for (auto& p : v) p = p.normalized();
    std::vector<std::array<int, 3>> f = {
        {0, 11, 5}, {0, 5, 1}, {0, 1, 7}, {0, 7, 10}, {0, 10, 11},
        {1, 5, 9}, {5, 11, 4}, {11, 10, 2}, {10, 7, 6}, {7, 1, 8},
        {3, 9, 4}, {3, 4, 2}, {3, 2, 6}, {3, 6, 8}, {3, 8, 9},
        {4, 9, 5}, {2, 4, 11}, {6, 2, 10}, {8, 6, 7}, {9, 8, 1}};
    for (int s = 0; s < subdiv; ++s) {
        std::vector<std::array<int, 3>> nf;
        for (auto& tri : f) {
            Vec3 a = v[tri[0]], b = v[tri[1]], c = v[tri[2]];
            v.push_back(((a + b) * 0.5f).normalized());
            v.push_back(((b + c) * 0.5f).normalized());
            v.push_back(((c + a) * 0.5f).normalized());
            int ab = (int)v.size() - 3, bc = (int)v.size() - 2, ca = (int)v.size() - 1;
            nf.push_back({tri[0], ab, ca});
            nf.push_back({tri[1], bc, ab});
            nf.push_back({tri[2], ca, bc});
            nf.push_back({ab, bc, ca});
        }
        f = std::move(nf);
    }
    std::vector<Tri> out;
    out.reserve(f.size());
    for (auto& tri : f) out.push_back({v[tri[0]], v[tri[1]], v[tri[2]]});
    return out;
}

inline std::vector<Tri> makeTorus(int segU, int segV, float R, float r) {
    auto pt = [&](int i, int j) {
        float u = 2.0f * 3.14159265f * i / segU;
        float w = 2.0f * 3.14159265f * j / segV;
        float cx = (R + r * std::cos(w)) * std::cos(u);
        float cy = r * std::sin(w);
        float cz = (R + r * std::cos(w)) * std::sin(u);
        return Vec3{cx, cy, cz};
    };
    std::vector<Tri> out;
    for (int i = 0; i < segU; ++i)
        for (int j = 0; j < segV; ++j) {
            Vec3 p00 = pt(i, j), p10 = pt(i + 1, j), p01 = pt(i, j + 1), p11 = pt(i + 1, j + 1);
            out.push_back({p00, p10, p11});
            out.push_back({p00, p11, p01});
        }
    return out;
}

inline std::vector<Tri> makeSpikyBlob(int n, uint32_t seed) {
    std::mt19937 rng(seed);
    std::uniform_real_distribution<float> uf(-1.0f, 1.0f);
    std::vector<Tri> base = makeIcosphere(2);
    std::vector<Tri> out;
    out.reserve(base.size());
    for (auto& tri : base) {
        Vec3 c = tri.centroid();
        float bump = 1.0f + 0.35f * std::sin(c.x * n) * std::cos(c.y * n) * std::sin(c.z * n + uf(rng));
        out.push_back({tri.v0 * bump, tri.v1 * bump, tri.v2 * bump});
    }
    return out;
}

// ---- BLAS: one per unique mesh, shared by all instances of that mesh ----
struct Mesh {
    std::vector<Tri> tris;
    BVH bvh;
    void finalize() { bvh.build(tris); }
    uint64_t memoryBytes() const {
        return tris.size() * sizeof(Tri) + bvh.memoryBytes() + orderBytes();
    }
    uint64_t orderBytes() const { return bvh.order.size() * sizeof(int); }
};

struct Instance {
    int meshId;
    Mat4 xform;
    Mat4 invXform;
    AABB worldBox; // only top-level data affected by transform updates
};

inline float traceBLAS(const Mesh& mesh, const Ray& ray, RayStats& stats, float& t) {
    int stack[64];
    int sp = 0;
    stack[sp++] = 0;
    while (sp > 0) {
        const BVHNode& node = mesh.bvh.nodes[stack[--sp]];
        stats.nodeVisits++;
        if (!node.box.intersect(ray.origin, ray.invDir, t)) continue;
        if (node.count > 0) {
            for (int i = node.start; i < node.start + node.count; ++i) {
                stats.triTests++;
                mesh.tris[mesh.bvh.order[i]].intersect(ray, t);
            }
        } else {
            stack[sp++] = node.left;
            stack[sp++] = node.right;
        }
    }
    return t;
}

// ---- Two-level scene: TLAS over instance AABBs + shared BLAS per mesh ----
struct TwoLevelScene {
    std::vector<Mesh> meshes;      // bottom level, uploaded once per unique mesh
    std::vector<Instance> instances;
    BVH tlas;                      // top level over instance world AABBs
    std::vector<BoxedPrim> instBoxes;
    uint64_t geometryUploads = 0;  // bytes of triangle data (re)uploaded

    void uploadGeometry() {
        for (auto& m : meshes) {
            m.finalize();
            geometryUploads += m.tris.size() * sizeof(Tri); // shared: once per mesh
        }
    }
    // transform update: only touches top-level boxes, never re-uploads geometry
    void updateInstances(const std::vector<Mat4>& newXforms) {
        for (size_t i = 0; i < instances.size(); ++i) {
            instances[i].xform = newXforms[i];
            instances[i].invXform = newXforms[i].inverse();
            const Mesh& m = meshes[instances[i].meshId];
            instances[i].worldBox = m.bvh.nodes[0].box.transformed(newXforms[i]);
        }
        rebuildTLAS();
    }
    void rebuildTLAS() {
        instBoxes.resize(instances.size());
        for (size_t i = 0; i < instances.size(); ++i) instBoxes[i].b = instances[i].worldBox;
        tlas.build(instBoxes);
    }
    float trace(const Ray& ray, RayStats& stats) const {
        float t = std::numeric_limits<float>::max();
        int stack[64];
        int sp = 0;
        stack[sp++] = 0;
        while (sp > 0) {
            const BVHNode& node = tlas.nodes[stack[--sp]];
            stats.nodeVisits++;
            if (!node.box.intersect(ray.origin, ray.invDir, t)) continue;
            if (node.count > 0) {
                for (int i = node.start; i < node.start + node.count; ++i) {
                    const Instance& inst = instances[tlas.order[i]];
                    stats.nodeVisits++; // per-instance AABB test at top level
                    if (!inst.worldBox.intersect(ray.origin, ray.invDir, t)) continue;
                    Vec3 lo = inst.invXform.transformPoint(ray.origin);
                    Vec3 ld = inst.invXform.transformVector(ray.dir);
                    Ray local = Ray::make(lo, ld);
                    traceBLAS(meshes[inst.meshId], local, stats, t);
                }
            } else {
                stack[sp++] = node.left;
                stack[sp++] = node.right;
            }
        }
        return t;
    }
    uint64_t tlasNodeCount() const { return tlas.nodeCount(); }
    uint64_t blasNodeCount() const {
        uint64_t n = 0;
        for (auto& m : meshes) n += m.bvh.nodeCount();
        return n;
    }
    uint64_t memoryBytes() const {
        uint64_t b = tlas.memoryBytes() + tlas.order.size() * sizeof(int)
                     + instances.size() * sizeof(Instance);
        for (auto& m : meshes) b += m.memoryBytes();
        return b;
    }
};

// ---- Flat single-level scene: every instance's triangles baked to world ----
struct FlatScene {
    std::vector<Tri> tris; // duplicated per instance
    BVH bvh;
    uint64_t geometryUploads = 0;

    void build(const std::vector<Mesh>& meshes, const std::vector<Instance>& instances) {
        tris.clear();
        for (const auto& inst : instances) {
            const Mesh& m = meshes[inst.meshId];
            for (const auto& tri : m.tris) {
                tris.push_back({inst.xform.transformPoint(tri.v0),
                                inst.xform.transformPoint(tri.v1),
                                inst.xform.transformPoint(tri.v2)});
            }
        }
        geometryUploads += tris.size() * sizeof(Tri); // full re-upload per build
        bvh.build(tris);
    }
    float trace(const Ray& ray, RayStats& stats) const {
        float t = std::numeric_limits<float>::max();
        int stack[64];
        int sp = 0;
        stack[sp++] = 0;
        while (sp > 0) {
            const BVHNode& node = bvh.nodes[stack[--sp]];
            stats.nodeVisits++;
            if (!node.box.intersect(ray.origin, ray.invDir, t)) continue;
            if (node.count > 0) {
                for (int i = node.start; i < node.start + node.count; ++i) {
                    stats.triTests++;
                    tris[bvh.order[i]].intersect(ray, t);
                }
            } else {
                stack[sp++] = node.left;
                stack[sp++] = node.right;
            }
        }
        return t;
    }
    uint64_t nodeCount() const { return bvh.nodeCount(); }
    uint64_t memoryBytes() const {
        return tris.size() * sizeof(Tri) + bvh.memoryBytes() + bvh.order.size() * sizeof(int);
    }
};
