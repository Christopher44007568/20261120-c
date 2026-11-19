#include "scenes.h"
#include <random>

namespace {
Triangle randomTriAt(const Vec3& c, float size, std::mt19937& rng) {
  std::uniform_real_distribution<float> u(-1.0f, 1.0f);
  Triangle t;
  t.v0 = c;
  t.v1 = {c.x + size * u(rng), c.y + size * u(rng), c.z + size * u(rng)};
  t.v2 = {c.x + size * u(rng), c.y + size * u(rng), c.z + size * u(rng)};
  return t;
}
}  // namespace

std::vector<Triangle> uniformScene(int n, uint32_t seed) {
  std::mt19937 rng(seed);
  std::uniform_real_distribution<float> u(0.0f, 1.0f);
  std::vector<Triangle> tris;
  tris.reserve(n);
  for (int i = 0; i < n; ++i)
    tris.push_back(randomTriAt({u(rng), u(rng), u(rng)}, 0.05f, rng));
  return tris;
}

std::vector<Triangle> clusteredScene(int n, int k, uint32_t seed) {
  std::mt19937 rng(seed);
  std::uniform_real_distribution<float> u(0.15f, 0.85f);
  std::normal_distribution<float> gauss(0.0f, 0.05f);
  std::uniform_int_distribution<int> pick(0, k - 1);
  std::vector<Vec3> centers(k);
  for (auto& c : centers) c = {u(rng), u(rng), u(rng)};
  std::vector<Triangle> tris;
  tris.reserve(n);
  for (int i = 0; i < n; ++i) {
    Vec3 c = centers[pick(rng)];
    Vec3 p{c.x + gauss(rng), c.y + gauss(rng), c.z + gauss(rng)};
    tris.push_back(randomTriAt(p, 0.02f, rng));
  }
  return tris;
}

std::vector<Triangle> pointCloudScene(int n, uint32_t seed) {
  std::mt19937 rng(seed);
  std::uniform_real_distribution<float> u(0.0f, 1.0f);
  std::vector<Triangle> tris;
  tris.reserve(n);
  for (int i = 0; i < n; ++i) {
    float z = 2.0f * u(rng) - 1.0f;
    float phi = 6.2831853f * u(rng);
    float r = std::sqrt(std::max(0.0f, 1.0f - z * z));
    Vec3 p{0.5f + 0.45f * r * std::cos(phi), 0.5f + 0.45f * r * std::sin(phi),
           0.5f + 0.45f * z};
    tris.push_back(randomTriAt(p, 0.004f, rng));
  }
  return tris;
}

std::vector<Triangle> denseMeshScene(int slices, int stacks) {
  std::vector<Triangle> tris;
  tris.reserve(slices * stacks * 2);
  auto vtx = [&](int i, int j) {
    float theta = 6.2831853f * i / slices;
    float phi = 3.1415926f * j / stacks;
    return Vec3{0.5f + 0.45f * std::sin(phi) * std::cos(theta),
                0.5f + 0.45f * std::sin(phi) * std::sin(theta),
                0.5f + 0.45f * std::cos(phi)};
  };
  for (int j = 0; j < stacks; ++j)
    for (int i = 0; i < slices; ++i) {
      Vec3 a = vtx(i, j), b = vtx(i + 1, j);
      Vec3 c = vtx(i + 1, j + 1), d = vtx(i, j + 1);
      tris.push_back({a, b, c});
      tris.push_back({a, c, d});
    }
  return tris;
}

std::vector<Triangle> planarScene(uint32_t seed) {
  std::mt19937 rng(seed);
  std::uniform_real_distribution<float> u(0.1f, 0.9f);
  std::vector<Triangle> tris;
  // Triangles exactly ON the planes x/y/z = 0.5 (degenerate bbox thickness 0).
  for (int axis = 0; axis < 3; ++axis)
    for (int i = 0; i < 60; ++i) {
      Triangle t;
      Vec3 c{u(rng), u(rng), u(rng)};
      c[axis] = 0.5f;
      t = randomTriAt(c, 0.06f, rng);
      t.v0[axis] = t.v1[axis] = t.v2[axis] = 0.5f;  // exactly coplanar
      tris.push_back(t);
    }
  // Symmetric background pairs (mirror about 0.5) to keep things balanced.
  for (int i = 0; i < 400; ++i) {
    Vec3 c{u(rng), u(rng), u(rng)};
    Vec3 m{1.0f - c.x, 1.0f - c.y, 1.0f - c.z};
    tris.push_back(randomTriAt(c, 0.03f, rng));
    tris.push_back(randomTriAt(m, 0.03f, rng));
  }
  // Pin the scene bbox to exactly [0,1]^3 so that midpoint splits land
  // exactly on 0.5 (depth 0 -> x, depth 1 -> y, depth 2 -> z), i.e. the
  // split plane passes exactly through the coplanar triangles above.
  tris.push_back({{0, 0, 0}, {0.001f, 0, 0}, {0, 0.001f, 0}});
  tris.push_back({{1, 1, 1}, {0.999f, 1, 1}, {1, 0.999f, 1}});
  return tris;
}

std::vector<Ray> makeRays(int n, const AABB& sb, uint32_t seed) {
  std::mt19937 rng(seed);
  std::uniform_real_distribution<float> u(0.0f, 1.0f);
  Vec3 center = (sb.mn + sb.mx) * 0.5f;
  Vec3 e = sb.mx - sb.mn;
  float radius = 0.5f * std::sqrt(e.x * e.x + e.y * e.y + e.z * e.z);
  std::vector<Ray> rays;
  rays.reserve(n);
  for (int i = 0; i < n; ++i) {
    float z = 2.0f * u(rng) - 1.0f;
    float phi = 6.2831853f * u(rng);
    float r = std::sqrt(std::max(0.0f, 1.0f - z * z));
    Vec3 o = center + Vec3{r * std::cos(phi), r * std::sin(phi), z} *
                         (radius * 2.5f);
    Vec3 target{sb.mn.x + e.x * u(rng), sb.mn.y + e.y * u(rng),
                sb.mn.z + e.z * u(rng)};
    Ray ray;
    ray.o = o;
    ray.d = (target - o).normalized();
    ray.precompute();
    rays.push_back(ray);
  }
  return rays;
}

Hit bruteForce(const std::vector<Triangle>& tris, const Ray& ray, float tMin) {
  Hit h;
  for (size_t i = 0; i < tris.size(); ++i) {
    float t;
    if (intersectTriangle(ray, tris[i], t) && t >= tMin && t < h.t) {
      h.t = t;
      h.triId = (int)i;
    }
  }
  return h;
}
