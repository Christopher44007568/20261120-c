#include "material_graph.h"

#include <algorithm>
#include <queue>
#include <unordered_set>

int MaterialGraph::addNode(NodeKind kind, const std::string& name) {
    int id = static_cast<int>(nodes_.size());
    nodes_.push_back({id, kind, name});
    indexById_[id] = nodes_.size() - 1;
    return id;
}

void MaterialGraph::addEdge(int src, int dst) {
    if (indexById_.count(src) == 0 || indexById_.count(dst) == 0 ||
        src == dst) {
        return;
    }
    for (const Edge& e : edges_) {
        if (e.src == src && e.dst == dst) {
            return;
        }
    }
    edges_.push_back({src, dst});
}

PruneResult MaterialGraph::pruneDeadNodes() {
    std::vector<std::vector<int>> reverseAdj(nodes_.size());
    for (const Edge& e : edges_) {
        reverseAdj[indexById_[e.dst]].push_back(e.src);
    }

    std::vector<bool> live(nodes_.size(), false);
    std::queue<int> work;
    for (const Node& node : nodes_) {
        if (node.kind == NodeKind::Output) {
            live[static_cast<size_t>(node.id)] = true;
            work.push(node.id);
        }
    }
    while (!work.empty()) {
        int id = work.front();
        work.pop();
        for (int src : reverseAdj[indexById_[id]]) {
            if (!live[static_cast<size_t>(src)]) {
                live[static_cast<size_t>(src)] = true;
                work.push(src);
            }
        }
    }

    PruneResult result;
    for (const Node& node : nodes_) {
        if (live[static_cast<size_t>(node.id)]) {
            result.keptNodes.push_back(node.id);
        } else {
            result.removedNodes.push_back(node.id);
        }
    }

    edges_.erase(std::remove_if(edges_.begin(), edges_.end(),
                                [&](const Edge& e) {
                                    return !live[static_cast<size_t>(e.src)] ||
                                           !live[static_cast<size_t>(e.dst)];
                                }),
                 edges_.end());

    std::vector<Node> kept;
    std::unordered_map<int, size_t> newIndex;
    kept.reserve(result.keptNodes.size());
    for (int id : result.keptNodes) {
        newIndex[id] = kept.size();
        kept.push_back(nodes_[indexById_[id]]);
    }
    nodes_ = std::move(kept);
    indexById_ = std::move(newIndex);
    return result;
}

TopoResult MaterialGraph::topologicalSort() const {
    std::vector<int> indegree(nodes_.size(), 0);
    std::vector<std::vector<int>> adj(nodes_.size());
    for (const Edge& e : edges_) {
        size_t from = indexById_.at(e.src);
        size_t to = indexById_.at(e.dst);
        adj[from].push_back(static_cast<int>(to));
        ++indegree[to];
    }

    std::queue<int> work;
    for (size_t i = 0; i < indegree.size(); ++i) {
        if (indegree[i] == 0) {
            work.push(static_cast<int>(i));
        }
    }

    TopoResult result;
    while (!work.empty()) {
        int idx = work.front();
        work.pop();
        result.order.push_back(nodes_[static_cast<size_t>(idx)].id);
        for (int next : adj[static_cast<size_t>(idx)]) {
            if (--indegree[static_cast<size_t>(next)] == 0) {
                work.push(next);
            }
        }
    }

    result.ok = result.order.size() == nodes_.size();
    if (!result.ok) {
        std::unordered_set<int> placed(result.order.begin(), result.order.end());
        for (const Node& node : nodes_) {
            if (placed.count(node.id) == 0) {
                result.cycleNodes.push_back(node.id);
            }
        }
        result.order.clear();
    }
    return result;
}
