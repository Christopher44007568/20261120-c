#include "kdtree.h"
#include "scenes.h"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <map>
#include <string>
#include <vector>

using Clock = std::chrono::steady_clock;
static double msSince(Clock::time_point t0) {
  return std::chrono::duration<double, std::milli>(Clock::now() - t0).count();
}

static const char* stratName(SplitStrategy s) {
  return s == SplitStrategy::SAH ? "SAH" : "AxisMid";
}

// Aggregate split-plane positions per tree depth (normalized to scene bounds).
static void printSplitProfile(const BuildStats& bs, const char* csvPath) {
  std::map<int, std::vector<float>> byDepth;
  for (auto& s : bs.splits) byDepth[s.depth].push_back(s.normPos);
  printf("    depth  splits  meanPos  minPos  maxPos   (pos normalized to scene "
         "bbox)\n");
  for (auto& [d, v] : byDepth) {
    float mn = 1e9f, mx = -1e9f, sum = 0;
    for (float p : v) {
      mn = std::min(mn, p);
      mx = std::max(mx, p);
      sum += p;
    }
    printf("    %5d  %6zu  %7.3f  %6.3f  %6.3f\n", d, v.size(), sum / v.size(),
           mn, mx);
  }
  FILE* f = std::fopen(csvPath, "w");
  if (f) {
    std::fprintf(f, "depth,axis,normPos\n");
    for (auto& s : bs.splits)
      std::fprintf(f, "%d,%d,%.6f\n", s.depth, s.axis, s.normPos);
    std::fclose(f);
  }
}

static void runExperiment(const std::string& name,
                          const std::vector<Triangle>& tris,
                          SplitStrategy strat, const std::vector<Ray>& rays) {
  KdTree tree;
  auto t0 = Clock::now();
  tree.build(tris, strat);
  double buildMs = msSince(t0);
  const BuildStats& bs = tree.buildStats();

  // Correctness: kd-tree closest hit must match brute force.
  int mismatches = 0;
  TraversalStats vstats;
  int nVerify = std::min<int>(500, (int)rays.size());
  for (int i = 0; i < nVerify; ++i) {
    Hit hk;
    tree.intersect(rays[i], hk, vstats);
    Hit hb = bruteForce(tris, rays[i], 1e-6f);
    bool bothMiss = hk.triId < 0 && hb.triId < 0;
    bool close = hk.triId >= 0 && hb.triId >= 0 &&
                 std::fabs(hk.t - hb.t) <= 1e-4f * std::max(1.0f, hb.t);
    if (!bothMiss && !close) mismatches++;
  }

  // Performance run.
  TraversalStats st;
  t0 = Clock::now();
  long long hits = 0;
  for (const Ray& r : rays) {
    Hit h;
    if (tree.intersect(r, h, st)) hits++;
  }
  double travMs = msSince(t0);
  double nr = (double)rays.size();

  printf("[%s | %s]\n", name.c_str(), stratName(strat));
  printf("  build: %8.2f ms   nodes: %7d   maxDepth: %3d   avgLeafDepth: "
         "%5.1f\n",
         buildMs, bs.nodeCount, bs.maxDepth,
         bs.leafCount ? (double)bs.leafDepthSum / bs.leafCount : 0.0);
  printf("  leaves: %7d (empty %d)   leafTris avg: %5.1f  max: %4d   "
         "refDup: %.2fx\n",
         bs.leafCount, bs.emptyLeaves,
         bs.leafCount ? (double)bs.leafTriRefs / bs.leafCount : 0.0,
         bs.maxLeafTris,
         tris.empty() ? 0.0 : (double)bs.leafTriRefs / (double)tris.size());
  printf("  verify: %s (%d/%d mismatches)\n", mismatches ? "FAIL" : "PASS",
         mismatches, nVerify);
  printf("  traverse: %8.2f ms for %zu rays (%6.1f ns/ray, hit %.1f%%)\n",
         travMs, rays.size(), travMs * 1e6 / nr, 100.0 * hits / nr);
  printf("  per-ray: nodes %6.1f  leaves %5.1f  emptySkips %5.2f  triTests "
         "%6.2f  dupSkipped %5.2f\n",
         st.nodesVisited / nr, st.leavesVisited / nr, st.emptyLeafSkips / nr,
         st.triTests / nr, st.duplicatesSkipped / nr);

  std::string csv = "splits_" + name + "_" + stratName(strat) + ".csv";
  printSplitProfile(bs, csv.c_str());
  printf("  split profile written to %s\n\n", csv.c_str());
}

// Stress test: split plane exactly through triangles (coplanar, bbox
// thickness 0). Such triangles are assigned to BOTH children; mailboxing
// must guarantee each is intersect-tested at most once per ray.
static void planarOverlapTest() {
  printf("=== planar-overlap test (split plane exactly through triangles) "
         "===\n");
  std::vector<Triangle> tris = planarScene(7);
  AABB sb;
  for (auto& t : tris) sb.expand(t.bounds());
  std::vector<Ray> rays = makeRays(20000, sb, 99);

  for (SplitStrategy strat : {SplitStrategy::AxisMidpoint, SplitStrategy::SAH}) {
    KdTree tree;
    tree.build(tris, strat);
    TraversalStats st, stRaw;
    long long rawTests = 0, rawDup = 0;
    int mismatches = 0;
    for (const Ray& r : rays) {
      Hit h;
      tree.intersect(r, h, st);  // mailboxed
      Hit hb = bruteForce(tris, r, 1e-6f);
      bool bothMiss = h.triId < 0 && hb.triId < 0;
      bool close = h.triId >= 0 && hb.triId >= 0 &&
                   std::fabs(h.t - hb.t) <= 1e-4f * std::max(1.0f, hb.t);
      if (!bothMiss && !close) mismatches++;
      // Raw traversal without mailbox to expose actual duplication.
      Hit hr;
      std::vector<int> ids;
      tree.intersectRecord(r, hr, stRaw, ids);
      rawTests += (long long)ids.size();
      std::sort(ids.begin(), ids.end());
      long long uniq = (long long)(std::unique(ids.begin(), ids.end()) -
                                   ids.begin());
      rawDup += (long long)ids.size() - uniq;
      // Mailbox invariant: tests performed == distinct triangles encountered.
      if (hr.triId != h.triId && std::fabs(hr.t - h.t) > 1e-6f) mismatches++;
    }
    double nr = (double)rays.size();
    printf("  [%s] verify %s | tests/ray %.2f (mailbox) vs %.2f (raw), "
           "dup/ray: %.2f avoided by mailbox, raw dup/ray %.2f, "
           "emptySkips/ray %.2f, maxDepth %d\n",
           stratName(strat), mismatches ? "FAIL" : "PASS", st.triTests / nr,
           rawTests / nr, st.duplicatesSkipped / nr, rawDup / nr,
           st.emptyLeafSkips / nr, tree.buildStats().maxDepth);
    if (st.triTests != rawTests - rawDup)
      printf("  WARNING: mailbox test count mismatch!\n");
  }
  printf("\n");
}

int main() {
  struct SceneDef {
    std::string name;
    std::vector<Triangle> tris;
  };
  std::vector<SceneDef> scenes;
  scenes.push_back({"uniform", uniformScene(20000, 1)});
  scenes.push_back({"clustered", clusteredScene(20000, 6, 2)});
  scenes.push_back({"pointcloud", pointCloudScene(20000, 3)});
  scenes.push_back({"densemesh", denseMeshScene(128, 96)});

  for (auto& sc : scenes) {
    AABB sb;
    for (auto& t : sc.tris) sb.expand(t.bounds());
    std::vector<Ray> rays = makeRays(100000, sb, 42);
    printf("==== scene %s: %zu triangles ====\n", sc.name.c_str(),
           sc.tris.size());
    runExperiment(sc.name, sc.tris, SplitStrategy::AxisMidpoint, rays);
    runExperiment(sc.name, sc.tris, SplitStrategy::SAH, rays);
  }

  planarOverlapTest();
  return 0;
}
