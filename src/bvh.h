#pragma once
#include "math3d.h"
#include <vector>
#include <numeric>

struct BVHNode {
    AABB box;
    int left = -1;   // internal: child indices
    int right = -1;
    int start = 0;   // leaf: first primitive index
    int count = 0;   // >0 means leaf
};

struct RayStats {
    uint64_t nodeVisits = 0;
    uint64_t triTests = 0;
    void reset() { nodeVisits = 0; triTests = 0; }
};

// Generic median-split BVH built over an array of primitive bounds.
// Prims are reordered in-place; nodes are stored in a flat vector.
class BVH {
public:
    std::vector<BVHNode> nodes;
    std::vector<int> order; // primitive indices, reordered for leaves

    template <typename Prim>
    void build(const std::vector<Prim>& prims) {
        nodes.clear();
        order.resize(prims.size());
        std::iota(order.begin(), order.end(), 0);
        std::vector<AABB> boxes(prims.size());
        std::vector<Vec3> cents(prims.size());
        for (size_t i = 0; i < prims.size(); ++i) {
            boxes[i] = prims[i].bounds();
            cents[i] = boxes[i].centroid();
        }
        if (!prims.empty()) buildRec(boxes, cents, 0, (int)prims.size());
    }

    uint64_t nodeCount() const { return nodes.size(); }
    uint64_t memoryBytes() const { return nodes.size() * sizeof(BVHNode); }

private:
    int buildRec(const std::vector<AABB>& boxes, const std::vector<Vec3>& cents,
                 int begin, int end) {
        BVHNode node;
        for (int i = begin; i < end; ++i) node.box.expand(boxes[order[i]]);
        int idx = (int)nodes.size();
        nodes.push_back(node);
        int n = end - begin;
        if (n <= 4) {
            nodes[idx].start = begin;
            nodes[idx].count = n;
            return idx;
        }
        AABB cb;
        for (int i = begin; i < end; ++i) cb.expand(cents[order[i]]);
        int axis = 0;
        Vec3 ext = cb.hi - cb.lo;
        if (ext.y > ext.x && ext.y >= ext.z) axis = 1;
        else if (ext.z > ext.x && ext.z >= ext.y) axis = 2;
        int mid = begin + n / 2;
        std::nth_element(order.begin() + begin, order.begin() + mid, order.begin() + end,
                         [&](int a, int b) { return cents[a][axis] < cents[b][axis]; });
        int left = buildRec(boxes, cents, begin, mid);
        int right = buildRec(boxes, cents, mid, end);
        nodes[idx].left = left;
        nodes[idx].right = right;
        nodes[idx].count = 0;
        return idx;
    }
};
