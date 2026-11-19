#include <algorithm>
#include <chrono>
#include <cstdio>
#include <random>
#include <string>
#include <vector>
#include "cache_sim.h"
#include "scene.h"
#include "sort_key.h"
#include "vec3.h"

struct Ray {
  Vec3 o, d;
  int type;  // -1 primary, kDiffuse, kSpecular
};

static std::mt19937_64 rng(20261120);

// ---------------------------------------------------------------- scene
// Heightfield terrain (64x64 quads = 8192 triangles). Material is randomly
// diffuse/specular per triangle so path hits interleave both types.
static Scene buildTerrainScene() {
  const int N = 64;
  std::vector<Vec3> grid((N + 1) * (N + 1));
  std::uniform_real_distribution<double> U(-1.0, 1.0);
  for (int j = 0; j <= N; ++j)
    for (int i = 0; i <= N; ++i) {
      double x = -4.0 + 8.0 * i / N;
      double z = -4.0 + 8.0 * j / N;
      double y = 0.6 * std::sin(1.7 * x) * std::cos(1.3 * z) + 0.15 * U(rng);
      grid[j * (N + 1) + i] = Vec3(x, y, z);
    }
  std::vector<Triangle> tris;
  tris.reserve(2 * N * N);
  std::uniform_real_distribution<double> pick(0.0, 1.0);
  auto emit = [&](Vec3 a, Vec3 b, Vec3 c) {
    tris.push_back({a, b, c, pick(rng) < 0.5 ? kDiffuse : kSpecular});
  };
  for (int j = 0; j < N; ++j)
    for (int i = 0; i < N; ++i) {
      Vec3 v00 = grid[j * (N + 1) + i], v10 = grid[j * (N + 1) + i + 1];
      Vec3 v01 = grid[(j + 1) * (N + 1) + i], v11 = grid[(j + 1) * (N + 1) + i + 1];
      emit(v00, v10, v11);
      emit(v00, v11, v01);
    }
  return makeScene(std::move(tris));
}

// ---------------------------------------------------------------- rays
static std::vector<Ray> genPrimaryRays(int w, int h) {
  Vec3 eye(0, 3.0, 7.0), at(0, 0, 0), up(0, 1, 0);
  Vec3 fwd = (at - eye).normalized();
  Vec3 right = fwd.cross(up).normalized();
  Vec3 camUp = right.cross(fwd);
  std::vector<Ray> rays;
  rays.reserve(w * h);
  std::uniform_real_distribution<double> U(0.0, 1.0);
  for (int j = 0; j < h; ++j)
    for (int i = 0; i < w; ++i) {
      double sx = 2.0 * (i + U(rng)) / w - 1.0;
      double sy = 1.0 - 2.0 * (j + U(rng)) / h;
      Vec3 d = (fwd * 2.2 + right * (sx * 1.6) + camUp * (sy * 0.9)).normalized();
      rays.push_back({eye, d, -1});
    }
  return rays;
}

static Vec3 cosineHemisphere(const Vec3& n) {
  std::uniform_real_distribution<double> U(0.0, 1.0);
  double u1 = U(rng), u2 = U(rng);
  double r = std::sqrt(u1), phi = 2.0 * M_PI * u2;
  Vec3 t, b;
  onb(n, t, b);
  return (t * (r * std::cos(phi)) + b * (r * std::sin(phi)) +
          n * std::sqrt(std::max(0.0, 1.0 - u1)))
      .normalized();
}

// Path-tracing bounce: intersect each primary ray, spawn one secondary ray
// according to the hit material (diffuse lobe vs. jittered mirror).
static void genSecondaryRays(const Scene& sc, const std::vector<Ray>& primary,
                             std::vector<Ray>& diffuse, std::vector<Ray>& specular) {
  std::uniform_real_distribution<double> U(-1.0, 1.0);
  Hit h;
  for (const Ray& r : primary) {
    h = Hit();
    if (!intersect(sc, r.o, r.d, h, nullptr)) continue;
    Vec3 p = r.o + r.d * h.t + h.n * 1e-5;
    if (h.material == kDiffuse) {
      diffuse.push_back({p, cosineHemisphere(h.n), kDiffuse});
    } else {
      Vec3 jitter(U(rng) * 0.05, U(rng) * 0.05, U(rng) * 0.05);
      specular.push_back({p, reflect(r.d, h.n).normalized() + jitter, kSpecular});
      specular.back().d = specular.back().d.normalized();
    }
  }
}

// ---------------------------------------------------------------- metrics
struct Metrics {
  uint64_t hits = 0, misses = 0;
  double msPerFrame = 0;
  double meanAdjCos = 0;  // mean dot(d[i-1], d[i]) in processing order
  double meanAdjDist = 0;  // mean |o[i] - o[i-1]| in processing order
};

static Metrics runBatch(const Scene& sc, const std::vector<Ray>& rays,
                        int frames) {
  Metrics m;
  Hit h;
  // Pass 1: cache simulation (32KB, 64B lines, 8-way LRU).
  CacheSim cache(32 * 1024, 64, 8);
  for (const Ray& r : rays) {
    h = Hit();
    intersect(sc, r.o, r.d, h, &cache);
  }
  m.hits = cache.hits();
  m.misses = cache.misses();
  // Pass 2: timing, `frames` frames of the full batch, sim off.
  volatile double sink = 0;
  auto t0 = std::chrono::steady_clock::now();
  for (int f = 0; f < frames; ++f)
    for (const Ray& r : rays) {
      h = Hit();
      intersect(sc, r.o, r.d, h, nullptr);
      sink += h.t;
    }
  auto t1 = std::chrono::steady_clock::now();
  (void)sink;
  m.msPerFrame = std::chrono::duration<double, std::milli>(t1 - t0).count() / frames;
  // Pass 3: adjacent-ray direction cosine / origin distance in order.
  double sumCos = 0, sumDist = 0;
  for (size_t i = 1; i < rays.size(); ++i) {
    sumCos += rays[i - 1].d.dot(rays[i].d);
    sumDist += (rays[i].o - rays[i - 1].o).length();
  }
  m.meanAdjCos = rays.size() > 1 ? sumCos / (rays.size() - 1) : 1.0;
  m.meanAdjDist = rays.size() > 1 ? sumDist / (rays.size() - 1) : 0.0;
  return m;
}

static std::vector<Ray> reorder(const std::vector<Ray>& rays,
                                const std::vector<uint32_t>& order) {
  std::vector<Ray> out;
  out.reserve(rays.size());
  for (uint32_t i : order) out.push_back(rays[i]);
  return out;
}

static void report(const char* name, const Metrics& m, size_t nRays) {
  double total = double(m.hits + m.misses);
  double hitRate = total > 0 ? 100.0 * m.hits / total : 0.0;
  double mb = m.misses * 64.0 / (1024.0 * 1024.0);
  std::printf("%-34s rays=%6zu miss=%8llu hit=%5.1f%% bw=%7.2fMB "
              "t=%7.3fms/f adjCos=%+.4f adjDist=%.3f\n",
              name, nRays, (unsigned long long)m.misses, hitRate, mb,
              m.msPerFrame, m.meanAdjCos, m.meanAdjDist);
}

int main() {
  const int W = 192, H = 192, FRAMES = 10;
  Scene sc = buildTerrainScene();
  std::printf("scene: %zu triangles, %zu BVH nodes (%.1f KB nodes + %.1f KB "
              "tris vs 32 KB cache)\n",
              sc.tris.size(), sc.nodes.size(),
              sc.nodes.size() * sizeof(BVHNode) / 1024.0,
              sc.tris.size() * sizeof(Triangle) / 1024.0);

  std::vector<Ray> primary = genPrimaryRays(W, H);

  std::printf("\n== A. primary rays: unsorted vs sorted ==\n");
  Metrics a0 = runBatch(sc, primary, FRAMES);
  report("primary unsorted", a0, primary.size());
  std::vector<Ray> primarySorted =
      reorder(primary, sortedOrder(primary, sc.bmin, sc.bmax));
  Metrics a1 = runBatch(sc, primarySorted, FRAMES);
  report("primary sorted", a1, primarySorted.size());

  std::vector<Ray> secDiffuse, secSpecular;
  genSecondaryRays(sc, primary, secDiffuse, secSpecular);
  std::vector<Ray> secMixed;
  secMixed.reserve(secDiffuse.size() + secSpecular.size());
  secMixed.insert(secMixed.end(), secDiffuse.begin(), secDiffuse.end());
  secMixed.insert(secMixed.end(), secSpecular.begin(), secSpecular.end());
  std::printf("\n== B. path-tracing secondary rays (diffuse=%zu, "
              "specular=%zu) ==\n",
              secDiffuse.size(), secSpecular.size());
  Metrics b0 = runBatch(sc, secMixed, FRAMES);
  report("secondary mixed unsorted", b0, secMixed.size());
  std::vector<Ray> secMixedSorted =
      reorder(secMixed, sortedOrder(secMixed, sc.bmin, sc.bmax));
  Metrics b1 = runBatch(sc, secMixedSorted, FRAMES);
  report("secondary mixed sorted", b1, secMixedSorted.size());

  std::printf("\n== C. split diffuse/specular streams, sort each ==\n");
  std::vector<Ray> sepSorted =
      reorder(secDiffuse, sortedOrder(secDiffuse, sc.bmin, sc.bmax));
  std::vector<Ray> specSorted =
      reorder(secSpecular, sortedOrder(secSpecular, sc.bmin, sc.bmax));
  Metrics cD = runBatch(sc, sepSorted, FRAMES);
  report("diffuse stream sorted", cD, sepSorted.size());
  Metrics cS = runBatch(sc, specSorted, FRAMES);
  report("specular stream sorted", cS, specSorted.size());
  std::vector<Ray> sepAll = sepSorted;
  sepAll.insert(sepAll.end(), specSorted.begin(), specSorted.end());
  Metrics cAll = runBatch(sc, sepAll, FRAMES);
  report("separated+sorted (combined)", cAll, sepAll.size());

  std::printf("\n== summary: sorted vs unsorted ==\n");
  auto delta = [](const char* tag, const Metrics& u, const Metrics& s) {
    double missCut = 100.0 * (1.0 - double(s.misses) / double(u.misses));
    double bwCut = 100.0 * (1.0 - double(s.misses) / double(u.misses));
    double speedup = u.msPerFrame / s.msPerFrame;
    std::printf("%-30s miss -%5.1f%%  bandwidth -%5.1f%%  speedup x%.2f  "
                "adjCos %+.3f->%+.3f adjDist %.2f->%.2f\n",
                tag, missCut, bwCut, speedup, u.meanAdjCos, s.meanAdjCos,
                u.meanAdjDist, s.meanAdjDist);
  };
  delta("primary", a0, a1);
  delta("secondary mixed", b0, b1);
  delta("secondary separated", b0, cAll);
  return 0;
}
