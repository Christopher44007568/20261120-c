#pragma once
#include <algorithm>
#include <cstdint>
#include <numeric>
#include <vector>
#include "vec3.h"
#include "cache_sim.h"

enum Material : int { kDiffuse = 0, kSpecular = 1 };

struct Triangle {
  Vec3 v0, v1, v2;
  int material;
};

struct BVHNode {
  Vec3 bmin, bmax;
  int left = -1, right = -1;  // <0 => leaf
  int start = 0, count = 0;   // leaf range in triIdx
};

struct Hit {
  double t = 1e30;
  int tri = -1;
  Vec3 n;
  int material = kDiffuse;
};

struct Scene {
  std::vector<Triangle> tris;
  std::vector<BVHNode> nodes;
  std::vector<int> triIdx;
  Vec3 bmin, bmax;
};

static void expandBounds(const Scene& s, int tri, Vec3& lo, Vec3& hi) {
  const Triangle& t = s.tris[tri];
  for (const Vec3* v : {&t.v0, &t.v1, &t.v2}) {
    lo.x = std::min(lo.x, v->x); lo.y = std::min(lo.y, v->y); lo.z = std::min(lo.z, v->z);
    hi.x = std::max(hi.x, v->x); hi.y = std::max(hi.y, v->y); hi.z = std::max(hi.z, v->z);
  }
}

static int buildBVH(Scene& s, int start, int count) {
  BVHNode node;
  Vec3 lo(1e30, 1e30, 1e30), hi(-1e30, -1e30, -1e30);
  for (int i = start; i < start + count; ++i) expandBounds(s, s.triIdx[i], lo, hi);
  node.bmin = lo; node.bmax = hi;
  int idx = (int)s.nodes.size();
  s.nodes.push_back(node);
  if (count <= 4) {
    s.nodes[idx].start = start;
    s.nodes[idx].count = count;
    return idx;
  }
  Vec3 ext = hi - lo;
  int axis = ext.x > ext.y ? (ext.x > ext.z ? 0 : 2) : (ext.y > ext.z ? 1 : 2);
  auto centroid = [&](int ti) {
    const Triangle& t = s.tris[ti];
    Vec3 c = (t.v0 + t.v1 + t.v2) / 3.0;
    return axis == 0 ? c.x : (axis == 1 ? c.y : c.z);
  };
  std::sort(s.triIdx.begin() + start, s.triIdx.begin() + start + count,
            [&](int a, int b) { return centroid(a) < centroid(b); });
  int mid = start + count / 2;
  s.nodes[idx].left = buildBVH(s, start, mid - start);
  s.nodes[idx].right = buildBVH(s, mid, start + count - mid);
  return idx;
}

static Scene makeScene(std::vector<Triangle> tris) {
  Scene s;
  s.tris = std::move(tris);
  s.triIdx.resize(s.tris.size());
  std::iota(s.triIdx.begin(), s.triIdx.end(), 0);
  buildBVH(s, 0, (int)s.triIdx.size());
  s.bmin = s.nodes[0].bmin;
  s.bmax = s.nodes[0].bmax;
  return s;
}

// Address spaces for the cache model: nodes at 0, triangles at 1<<40.
static inline uint64_t nodeAddr(int ni) {
  return (uint64_t)ni * sizeof(BVHNode);
}
static inline uint64_t triAddr(int ti) {
  return (1ull << 40) + (uint64_t)ti * sizeof(Triangle);
}

static inline bool slabTest(const BVHNode& n, const Vec3& o, const Vec3& invD,
                            double tMax) {
  double t0x = (n.bmin.x - o.x) * invD.x, t1x = (n.bmax.x - o.x) * invD.x;
  double t0y = (n.bmin.y - o.y) * invD.y, t1y = (n.bmax.y - o.y) * invD.y;
  double t0z = (n.bmin.z - o.z) * invD.z, t1z = (n.bmax.z - o.z) * invD.z;
  double tNear = std::max(std::max(std::min(t0x, t1x), std::min(t0y, t1y)),
                          std::min(t0z, t1z));
  double tFar = std::min(std::min(std::max(t0x, t1x), std::max(t0y, t1y)),
                         std::max(t0z, t1z));
  return tFar >= tNear && tFar > 1e-9 && tNear < tMax;
}

// Iterative BVH traversal; records every node/triangle line touch in `cache`
// when non-null. Returns true on hit and fills `h`.
static bool intersect(const Scene& s, const Vec3& ro, const Vec3& rd, Hit& h,
                      CacheSim* cache) {
  Vec3 invD(1.0 / rd.x, 1.0 / rd.y, 1.0 / rd.z);
  int stack[64];
  int sp = 0;
  stack[sp++] = 0;
  bool found = false;
  while (sp > 0) {
    int ni = stack[--sp];
    const BVHNode& node = s.nodes[ni];
    if (cache) cache->access(nodeAddr(ni));
    if (!slabTest(node, ro, invD, h.t)) continue;
    if (node.left < 0) {
      for (int i = 0; i < node.count; ++i) {
        int ti = s.triIdx[node.start + i];
        if (cache) cache->access(triAddr(ti));
        const Triangle& t = s.tris[ti];
        Vec3 e1 = t.v1 - t.v0, e2 = t.v2 - t.v0;
        Vec3 p = rd.cross(e2);
        double det = e1.dot(p);
        if (std::abs(det) < 1e-12) continue;
        double inv = 1.0 / det;
        Vec3 tv = ro - t.v0;
        double u = tv.dot(p) * inv;
        if (u < 0 || u > 1) continue;
        Vec3 q = tv.cross(e1);
        double v = rd.dot(q) * inv;
        if (v < 0 || u + v > 1) continue;
        double tt = e2.dot(q) * inv;
        if (tt > 1e-6 && tt < h.t) {
          h.t = tt;
          h.tri = ti;
          h.n = e1.cross(e2).normalized();
          if (h.n.dot(rd) > 0) h.n = h.n * -1.0;
          h.material = t.material;
          found = true;
        }
      }
    } else {
      stack[sp++] = node.left;
      stack[sp++] = node.right;
    }
  }
  return found;
}
