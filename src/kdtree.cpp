#include "kdtree.h"
#include <algorithm>
#include <numeric>

namespace {
constexpr int kMaxDepth = 64;
constexpr int kMinTris = 2;          // always make a leaf at or below this
constexpr float kCostTraverse = 1.0f;
constexpr float kCostIntersect = 1.5f;
}  // namespace

void KdTree::build(const std::vector<Triangle>& tris, SplitStrategy strategy) {
  tris_ = &tris;
  strategy_ = strategy;
  nodes_.clear();
  triIndices_.clear();
  bstats_ = BuildStats();

  sceneBounds_ = AABB();
  triBounds_.resize(tris.size());
  for (size_t i = 0; i < tris.size(); ++i) {
    triBounds_[i] = tris[i].bounds();
    sceneBounds_.expand(triBounds_[i]);
  }
  std::vector<int> idx(tris.size());
  std::iota(idx.begin(), idx.end(), 0);
  mailbox_.assign(tris.size(), -1);
  rayId_ = 0;

  buildRecursive(idx, sceneBounds_, 0);
  bstats_.nodeCount = (int)nodes_.size();
}

int KdTree::makeLeaf(int ni, const std::vector<int>& idx, int depth) {
  Node& n = nodes_[ni];
  n.axis = -1;
  n.start = (int)triIndices_.size();
  n.count = (int)idx.size();
  triIndices_.insert(triIndices_.end(), idx.begin(), idx.end());
  bstats_.leafCount++;
  bstats_.leafDepthSum += depth;
  bstats_.leafTriRefs += n.count;
  bstats_.maxLeafTris = std::max(bstats_.maxLeafTris, n.count);
  if (n.count == 0) bstats_.emptyLeaves++;
  return ni;
}

// SAH over candidate positions taken from clipped triangle bbox endpoints.
// Cost model: CT + CI * (SA_l/SA * N_l + SA_r/SA * N_r).
// A triangle is counted on a side iff its bbox overlaps that side, which
// matches the assignment rule used below (straddlers go to BOTH children).
bool KdTree::findSplitSAH(const std::vector<int>& idx, const AABB& bounds,
                          int& bestAxis, float& bestPos) const {
  float nodeSA = bounds.surfaceArea();
  if (nodeSA <= 0.0f) return false;
  const int n = (int)idx.size();
  float bestCost = kCostIntersect * (float)n;  // cost of not splitting
  bool found = false;

  for (int a = 0; a < 3; ++a) {
    float lo = bounds.mn[a], hi = bounds.mx[a];
    if (hi - lo < 1e-9f) continue;
    std::vector<float> mins, maxs, cand;
    mins.reserve(n);
    maxs.reserve(n);
    cand.reserve(2 * n);
    for (int id : idx) {
      float mn = std::max(triBounds_[id].mn[a], lo);
      float mx = std::min(triBounds_[id].mx[a], hi);
      mins.push_back(mn);
      maxs.push_back(mx);
      if (mn > lo && mn < hi) cand.push_back(mn);
      if (mx > lo && mx < hi) cand.push_back(mx);
    }
    std::sort(mins.begin(), mins.end());
    std::sort(maxs.begin(), maxs.end());
    std::sort(cand.begin(), cand.end());
    cand.erase(std::unique(cand.begin(), cand.end()), cand.end());

    for (float p : cand) {
      // N_l(p) = #{min <= p}, N_r(p) = #{max >= p}: straddlers counted twice.
      int nl = (int)(std::upper_bound(mins.begin(), mins.end(), p) - mins.begin());
      int nr = n - (int)(std::lower_bound(maxs.begin(), maxs.end(), p) - maxs.begin());
      AABB lb = bounds, rb = bounds;
      lb.mx[a] = p;
      rb.mn[a] = p;
      float pl = lb.surfaceArea() / nodeSA;
      float pr = rb.surfaceArea() / nodeSA;
      float cost = kCostTraverse + kCostIntersect * (pl * nl + pr * nr);
      if (cost < bestCost) {
        bestCost = cost;
        bestAxis = a;
        bestPos = p;
        found = true;
      }
    }
  }
  return found;
}

int KdTree::buildRecursive(std::vector<int>& idx, const AABB& bounds, int depth) {
  int ni = (int)nodes_.size();
  nodes_.push_back(Node{});
  bstats_.maxDepth = std::max(bstats_.maxDepth, depth);
  const int n = (int)idx.size();

  if (n <= kMinTris || depth >= kMaxDepth) return makeLeaf(ni, idx, depth);

  int axis = -1;
  float pos = 0.0f;
  bool ok = false;
  if (strategy_ == SplitStrategy::SAH) {
    ok = findSplitSAH(idx, bounds, axis, pos);
  } else {
    // Classic per-axis split: cycle axes, split at the cell midpoint.
    axis = depth % 3;
    pos = (bounds.mn[axis] + bounds.mx[axis]) * 0.5f;
    ok = pos > bounds.mn[axis] && pos < bounds.mx[axis];
  }
  if (!ok) return makeLeaf(ni, idx, depth);

  // Overlap assignment: a triangle whose bbox straddles (or lies exactly on)
  // the split plane is referenced by BOTH children. Duplicate intersection
  // tests at traversal time are eliminated by mailboxing.
  std::vector<int> li, ri;
  li.reserve(n);
  ri.reserve(n);
  for (int id : idx) {
    if (triBounds_[id].mn[axis] <= pos) li.push_back(id);
    if (triBounds_[id].mx[axis] >= pos) ri.push_back(id);
  }
  // No-progress guard (e.g. every triangle straddles the plane).
  if ((int)li.size() == n && (int)ri.size() == n) return makeLeaf(ni, idx, depth);

  AABB lb = bounds, rb = bounds;
  lb.mx[axis] = pos;
  rb.mn[axis] = pos;
  nodes_[ni].axis = axis;
  nodes_[ni].split = pos;
  float extent = sceneBounds_.mx[axis] - sceneBounds_.mn[axis];
  float norm = extent > 0 ? (pos - sceneBounds_.mn[axis]) / extent : 0.5f;
  bstats_.splits.push_back({depth, axis, norm});
  nodes_[ni].left = buildRecursive(li, lb, depth + 1);
  nodes_[ni].right = buildRecursive(ri, rb, depth + 1);
  return ni;
}

void KdTree::traverse(int ni, const Ray& ray, float tmin, float tmax, Hit& hit,
                      TraversalStats& st, std::vector<int>* record) const {
  if (tmin > hit.t) return;  // whole node interval beyond current best hit
  const Node& node = nodes_[ni];
  st.nodesVisited++;

  if (node.axis < 0) {
    st.leavesVisited++;
    if (node.count == 0) {
      st.emptyLeafSkips++;
      return;
    }
    for (int i = node.start; i < node.start + node.count; ++i) {
      int id = triIndices_[i];
      if (record) {
        record->push_back(id);  // debug path: no mailbox, count everything
      } else {
        if (mailbox_[id] == rayId_) {
          st.duplicatesSkipped++;
          continue;
        }
        mailbox_[id] = rayId_;
      }
      st.triTests++;
      float t;
      // NOTE: triangles are tested against the full ray range [rayTMin_,
      // hit.t], not the node's t-interval. A straddling triangle may be hit
      // outside this node's slab; the t-interval is only used to prune nodes.
      if (intersectTriangle(ray, (*tris_)[id], t) && t >= rayTMin_ &&
          t < hit.t) {
        hit.t = t;
        hit.triId = id;
      }
    }
    return;
  }

  int a = node.axis;
  if (ray.d[a] == 0.0f) {  // ray parallel to split plane
    int only = (ray.o[a] < node.split) ? node.left : node.right;
    traverse(only, ray, tmin, tmax, hit, st, record);
    return;
  }
  float tsplit = (node.split - ray.o[a]) * ray.invd[a];
  int nearN = node.left, farN = node.right;
  if (ray.sign[a]) std::swap(nearN, farN);
  if (tsplit >= tmax) {
    traverse(nearN, ray, tmin, tmax, hit, st, record);
  } else if (tsplit <= tmin) {
    traverse(farN, ray, tmin, tmax, hit, st, record);
  } else {
    traverse(nearN, ray, tmin, tsplit, hit, st, record);
    traverse(farN, ray, tsplit, tmax, hit, st, record);
  }
}

bool KdTree::intersect(const Ray& ray, Hit& hit, TraversalStats& st) {
  if (++rayId_ <= 0) {  // wrap-around: reset mailbox
    std::fill(mailbox_.begin(), mailbox_.end(), -1);
    rayId_ = 1;
  }
  hit = Hit();
  traverse(0, ray, rayTMin_, FLT_MAX, hit, st, nullptr);
  return hit.triId >= 0;
}

bool KdTree::intersectRecord(const Ray& ray, Hit& hit, TraversalStats& st,
                             std::vector<int>& testedIds) {
  testedIds.clear();
  hit = Hit();
  traverse(0, ray, rayTMin_, FLT_MAX, hit, st, &testedIds);
  return hit.triId >= 0;
}
