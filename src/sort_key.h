#pragma once
#include <algorithm>
#include <cstdint>
#include <numeric>
#include <vector>
#include "vec3.h"

// Octahedral encode a unit direction into [0,1]^2.
static inline void octEncode(const Vec3& d, double& u, double& v) {
  double invL1 = 1.0 / (std::abs(d.x) + std::abs(d.y) + std::abs(d.z) + 1e-30);
  double px = d.x * invL1, py = d.y * invL1;
  if (d.z < 0) {
    double ox = (1.0 - std::abs(py)) * (px >= 0 ? 1.0 : -1.0);
    double oy = (1.0 - std::abs(px)) * (py >= 0 ? 1.0 : -1.0);
    px = ox; py = oy;
  }
  u = px * 0.5 + 0.5;
  v = py * 0.5 + 0.5;
}

static inline uint64_t part1by1(uint32_t x) {
  uint64_t v = x & 0xffffffffull;
  v = (v | (v << 16)) & 0x0000ffff0000ffffull;
  v = (v | (v << 8)) & 0x00ff00ff00ff00ffull;
  v = (v | (v << 4)) & 0x0f0f0f0f0f0f0f0full;
  v = (v | (v << 2)) & 0x3333333333333333ull;
  v = (v | (v << 1)) & 0x5555555555555555ull;
  return v;
}

static inline uint64_t morton2(uint32_t x, uint32_t y) {
  return part1by1(x) | (part1by1(y) << 1);
}

static inline uint64_t part1by2(uint32_t x) {
  uint64_t v = x & 0x1fffffull;
  v = (v | (v << 32)) & 0x1f00000000ffffull;
  v = (v | (v << 16)) & 0x1f0000ff0000ffull;
  v = (v | (v << 8)) & 0x100f00f00f00f00full;
  v = (v | (v << 4)) & 0x10c30c30c30c30c3ull;
  v = (v | (v << 2)) & 0x1249249249249249ull;
  return v;
}

static inline uint64_t morton3(uint32_t x, uint32_t y, uint32_t z) {
  return part1by2(x) | (part1by2(y) << 1) | (part1by2(z) << 2);
}

// Sort key (high -> low bits):
//   1. coarse origin cell (4 bits/axis): nearby origins traverse the same
//      BVH region back-to-back -> node cache locality.
//   2. direction (octahedral + Morton, 10 bits/axis): within a cell, rays
//      with similar directions stay adjacent -> directional coherence.
//   3. fine origin cell (6 bits/axis): residual spatial tie-break.
// For primary rays all origins coincide, so the direction part drives order.
static inline uint64_t rayKey(const Vec3& o, const Vec3& d, const Vec3& bmin,
                              const Vec3& bmax) {
  double u, v;
  octEncode(d, u, v);
  uint32_t du = (uint32_t)(u * 1023.0) & 1023;
  uint32_t dv = (uint32_t)(v * 1023.0) & 1023;
  Vec3 ext(bmax.x - bmin.x + 1e-9, bmax.y - bmin.y + 1e-9,
           bmax.z - bmin.z + 1e-9);
  auto cell = [&](double c, double lo, double e, uint32_t maxv) {
    double t = (c - lo) / e;
    t = t < 0 ? 0 : (t > 1 ? 1 : t);
    return (uint32_t)(t * maxv) & maxv;
  };
  uint32_t kx = cell(o.x, bmin.x, ext.x, 15);
  uint32_t ky = cell(o.y, bmin.y, ext.y, 15);
  uint32_t kz = cell(o.z, bmin.z, ext.z, 15);
  uint32_t fx = cell(o.x, bmin.x, ext.x, 63);
  uint32_t fy = cell(o.y, bmin.y, ext.y, 63);
  uint32_t fz = cell(o.z, bmin.z, ext.z, 63);
  return (morton3(kx, ky, kz) << 38) | (morton2(du, dv) << 18) |
         morton3(fx, fy, fz);
}

// Return indices sorted by ray key (stable, deterministic).
template <typename RayT>
static std::vector<uint32_t> sortedOrder(const std::vector<RayT>& rays,
                                         const Vec3& bmin, const Vec3& bmax) {
  std::vector<uint32_t> idx(rays.size());
  std::iota(idx.begin(), idx.end(), 0);
  std::vector<uint64_t> keys(rays.size());
  for (size_t i = 0; i < rays.size(); ++i)
    keys[i] = rayKey(rays[i].o, rays[i].d, bmin, bmax);
  std::stable_sort(idx.begin(), idx.end(),
                   [&](uint32_t a, uint32_t b) { return keys[a] < keys[b]; });
  return idx;
}
