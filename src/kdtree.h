#pragma once
#include "geometry.h"
#include <vector>

enum class SplitStrategy { AxisMidpoint, SAH };

struct BuildStats {
  int maxDepth = 0;
  int nodeCount = 0;
  int leafCount = 0;
  int emptyLeaves = 0;
  long long leafTriRefs = 0;   // triangle references summed over leaves
  int maxLeafTris = 0;
  long long leafDepthSum = 0;  // for average leaf depth
  struct SplitInfo {
    int depth;
    int axis;
    float normPos;  // split position normalized to scene bounds [0,1]
  };
  std::vector<SplitInfo> splits;
};

struct TraversalStats {
  long long nodesVisited = 0;
  long long leavesVisited = 0;
  long long emptyLeafSkips = 0;   // leaves reached that contain no triangles
  long long triTests = 0;         // actual ray-triangle intersection tests
  long long duplicatesSkipped = 0;  // tests avoided by mailboxing
  void reset() { *this = TraversalStats(); }
};

class KdTree {
public:
  void build(const std::vector<Triangle>& tris, SplitStrategy strategy);
  // Closest-hit query. Mailboxing guarantees each triangle is tested at most
  // once per ray even when it is referenced by multiple leaves.
  bool intersect(const Ray& ray, Hit& hit, TraversalStats& st);
  // Debug query WITHOUT mailboxing: records every tested triangle id so the
  // caller can measure how much duplication the overlap rule introduces.
  bool intersectRecord(const Ray& ray, Hit& hit, TraversalStats& st,
                       std::vector<int>& testedIds);
  const BuildStats& buildStats() const { return bstats_; }
  const AABB& sceneBounds() const { return sceneBounds_; }

private:
  struct Node {
    float split = 0.0f;
    int axis = -1;  // -1 => leaf
    int left = 0, right = 0;  // child node indices (interior nodes)
    int start = 0, count = 0;  // range into triIndices_ (leaf nodes)
  };

  int buildRecursive(std::vector<int>& idx, const AABB& bounds, int depth);
  int makeLeaf(int ni, const std::vector<int>& idx, int depth);
  bool findSplitSAH(const std::vector<int>& idx, const AABB& bounds,
                    int& axis, float& pos) const;
  void traverse(int ni, const Ray& ray, float tmin, float tmax, Hit& hit,
                TraversalStats& st, std::vector<int>* record) const;

  const std::vector<Triangle>* tris_ = nullptr;
  std::vector<AABB> triBounds_;
  std::vector<Node> nodes_;
  std::vector<int> triIndices_;
  AABB sceneBounds_;
  SplitStrategy strategy_ = SplitStrategy::SAH;
  BuildStats bstats_;
  // Mailbox state: last ray id that tested each triangle.
  mutable std::vector<int> mailbox_;
  int rayId_ = 0;
  float rayTMin_ = 1e-6f;
};
