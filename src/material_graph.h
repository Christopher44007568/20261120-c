#pragma once

#include <string>
#include <unordered_map>
#include <vector>

enum class NodeKind {
    Input,
    Constant,
    Math,
    Texture,
    Output,
};

struct Node {
    int id = -1;
    NodeKind kind = NodeKind::Math;
    std::string name;
};

// Edge src -> dst: output of src feeds an input of dst.
struct Edge {
    int src = -1;
    int dst = -1;
};

struct PruneResult {
    std::vector<int> keptNodes;
    std::vector<int> removedNodes;
};

struct TopoResult {
    bool ok = false;
    std::vector<int> order;
    std::vector<int> cycleNodes;
};

class MaterialGraph {
public:
    int addNode(NodeKind kind, const std::string& name);
    void addEdge(int src, int dst);

    const std::vector<Node>& nodes() const { return nodes_; }
    const std::vector<Edge>& edges() const { return edges_; }

    // Removes every node that cannot reach an Output node, then removes
    // edges referencing deleted nodes.
    PruneResult pruneDeadNodes();

    // Kahn topological sort; on failure returns the nodes still queued.
    TopoResult topologicalSort() const;

private:
    std::vector<Node> nodes_;
    std::vector<Edge> edges_;
    std::unordered_map<int, size_t> indexById_;
};
