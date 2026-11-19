#include <algorithm>
#include <cassert>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

#include "material_graph.h"
#include "rasterizer.h"
#include "trail.h"

namespace {

int g_failures = 0;

void check(bool condition, const std::string& label) {
    std::cout << "  [" << (condition ? "PASS" : "FAIL") << "] " << label
              << '\n';
    if (!condition) {
        ++g_failures;
    }
}

bool nearlyEqual(float a, float b, float eps = 1e-4f) {
    return std::abs(a - b) <= eps;
}

void printStats(const DrawStats& s) {
    std::cout << "  particles       : " << s.particleCount << '\n';
    std::cout << "  rendered strips : " << s.renderedStrips << '\n';
    std::cout << "  strip vertices  : " << s.totalVertices << '\n';
    std::cout << "  strip indices   : " << s.totalIndices << '\n';
    std::cout << "  strip triangles : " << s.totalTriangles << '\n';
    std::cout << "  draw batches    : " << s.drawBatchesPerStrip
              << " (per-strip) / " << s.drawBatchesMerged
              << " (merged single batch)\n";
}

std::vector<Vec2> simulate(TrailSystem& system, int frames) {
    const auto& particles = system.particles();
    std::vector<Vec2> next(particles.size());
    for (int frame = 0; frame < frames; ++frame) {
        for (size_t i = 0; i < particles.size(); ++i) {
            Particle p = particles[i];
            next[i] = p.pos + p.vel;
        }
        system.advance(next);
    }
    return next;
}

void testFastMovingContinuity() {
    std::cout << "\n=== Test 1: fast-moving particle trail continuity ===\n";
    TrailConfig cfg;
    cfg.historyLength = 24;
    cfg.headWidth = 8.0f;
    cfg.tailWidth = 1.0f;
    TrailSystem system(cfg);

    int capacity = cfg.historyLength;
    Particle fast(1, {20.0f, 60.0f}, {34.0f, 0.0f}, capacity);
    fast.push(fast.pos);
    system.spawn(fast);
    simulate(system, 23);

    StripMesh mesh = system.buildStrip(0);
    check(mesh.vertices.size() == 48,
          "ring count matches history (2 vertices per history point, "
          "no clamped corner on a straight path)");
    check(mesh.indices.size() == 46 * 3,
          "23 segment quads => 46 triangles from 24 rings");

    bool sharedRing = true;
    for (int i = 0; i < 24; ++i) {
        const Vec2& left = mesh.vertices[2 * i].pos;
        const Vec2& right = mesh.vertices[2 * i + 1].pos;
        if (!nearlyEqual(left.x, right.x, 1e-3f)) {
            sharedRing = false;
        }
    }
    check(sharedRing,
          "each ring's left/right vertices share the path x (quads join on "
          "shared ring edges, no T-junction)");

    // Rasterized coverage must bridge every 34 px jump without holes.
    Framebuffer probe(800, 120);
    std::vector<StripMesh> meshes{mesh};
    int covered = countCoveragePixels(probe, meshes);
    check(covered > 600, "coverage area is substantial (" +
                             std::to_string(covered) + " px)");

    bool rowContinuous = true;
    int runStart = -1;
    int runEnd = -1;
    for (int x = 0; x < probe.width(); ++x) {
        bool hit = false;
        for (int y = 0; y < probe.height(); ++y) {
            if (probe.readPixel(x, y).a > 0.0f) {
                hit = true;
                break;
            }
        }
        if (hit) {
            if (runStart < 0) runStart = x;
            runEnd = x;
        }
    }
    for (int x = runStart; x <= runEnd && rowContinuous; ++x) {
        bool hit = false;
        for (int y = 0; y < probe.height(); ++y) {
            if (probe.readPixel(x, y).a > 0.0f) {
                hit = true;
                break;
            }
        }
        if (!hit) rowContinuous = false;
    }
    check(rowContinuous,
          "no horizontal gap between 34 px/frame steps (watertight strip)");

    const Particle& p = system.particles()[0];
    float step = (p.at(1, capacity).pos.x - p.at(0, capacity).pos.x);
    check(nearlyEqual(step, 34.0f, 1e-3f),
          "sampled speed is 34 px/frame (fast movement confirmed)");
    printStats(system.stats());
}

void testWidthAndAlphaDecay() {
    std::cout << "\n=== Test 2: width and alpha decay along the strip ===\n";
    TrailConfig cfg;
    cfg.historyLength = 8;
    cfg.headWidth = 10.0f;
    cfg.tailWidth = 2.0f;
    cfg.headAlpha = 0.9f;
    cfg.tailAlpha = 0.1f;
    TrailSystem system(cfg);
    Particle p(1, {10.0f, 50.0f}, {8.0f, 0.0f}, cfg.historyLength);
    p.push(p.pos);
    system.spawn(p);
    simulate(system, 7);

    StripMesh mesh = system.buildStrip(0);
    check(mesh.vertices.size() == 16, "8 rings => 16 strip vertices");

    const Vertex& tailL = mesh.vertices[0];
    const Vertex& tailR = mesh.vertices[1];
    const Vertex& headL = mesh.vertices[14];
    const Vertex& headR = mesh.vertices[15];
    float tailW = length(tailL.pos - tailR.pos);
    float headW = length(headL.pos - headR.pos);
    check(nearlyEqual(tailW, 2.0f, 1e-3f),
          "tail ring width equals tailWidth (2.0 px)");
    check(nearlyEqual(headW, 10.0f, 1e-3f),
          "head ring width equals headWidth (10.0 px)");
    check(headW > tailW, "width monotonically grows tail -> head");
    check(nearlyEqual(tailL.color.a, 0.1f, 1e-4f),
          "tail alpha equals tailAlpha (0.1)");
    check(nearlyEqual(headL.color.a, 0.9f, 1e-4f),
          "head alpha equals headAlpha (0.9)");

    bool monotonic = true;
    for (int i = 0; i < 7; ++i) {
        float w0 = length(mesh.vertices[2 * i].pos -
                          mesh.vertices[2 * i + 1].pos);
        float w1 = length(mesh.vertices[2 * (i + 1)].pos -
                          mesh.vertices[2 * (i + 1) + 1].pos);
        if (w1 < w0 - 1e-4f) monotonic = false;
    }
    check(monotonic, "per-ring width is non-decreasing along the trail");
}

void testAlphaBlending() {
    std::cout << "\n=== Test 3: translucent over-blending ===\n";
    Framebuffer fb(4, 4);
    fb.clear({0.1f, 0.2f, 0.3f, 1.0f});

    Color dst = fb.readPixel(0, 0);
    fb.blendPixel(0, 0, {1.0f, 0.0f, 0.0f, 0.5f});
    Color once = fb.readPixel(0, 0);
    float expectR = 1.0f * 0.5f + dst.r * 0.5f;
    float expectG = dst.g * 0.5f;
    check(nearlyEqual(once.r, expectR, 1e-5f) &&
              nearlyEqual(once.g, expectG, 1e-5f) &&
              nearlyEqual(once.a, 1.0f, 1e-5f),
          "single over-blend matches src*a + dst*(1-a)");

    fb.clear({0.0f, 0.0f, 0.0f, 0.0f});
    fb.blendPixel(1, 1, {0.0f, 1.0f, 0.0f, 0.4f});
    Color oneLayer = fb.readPixel(1, 1);
    fb.blendPixel(1, 1, {0.0f, 1.0f, 0.0f, 0.4f});
    Color twoLayer = fb.readPixel(1, 1);
    check(nearlyEqual(oneLayer.a, 0.4f, 1e-5f),
          "one translucent layer keeps alpha 0.4");
    check(nearlyEqual(twoLayer.a, 0.4f + 0.4f * 0.6f, 1e-5f),
          "stacked layers follow a1 + a2*(1-a1) = 0.64");
    check(twoLayer.a > oneLayer.a,
          "overlapping strips deepen coverage instead of replacing it");

    // Two crossing strips rendered through the triangle path.
    Framebuffer scene(64, 64);
    scene.clear({0, 0, 0, 0});
    TrailConfig cfg;
    cfg.historyLength = 4;
    cfg.headAlpha = cfg.tailAlpha = 0.5f;
    TrailSystem system(cfg);
    Particle a(1, {8, 32}, {12, 0}, cfg.historyLength);
    Particle b(2, {32, 8}, {0, 12}, cfg.historyLength);
    a.push(a.pos);
    b.push(b.pos);
    system.spawn(a);
    system.spawn(b);
    simulate(system, 3);
    auto meshes = system.buildAllStrips();
    renderTrails(scene, meshes);
    Color cross = scene.readPixel(32, 32);
    check(cross.a > 0.5f,
          "crossing region alpha (" +
              std::to_string(static_cast<int>(cross.a * 100.0f)) +
              "%) exceeds a single strip's 50%");
}

void testHistoryLengthSweep() {
    std::cout << "\n=== Test 4: history buffer length vs trail shape ===\n";
    const int kFrames = 40;
    int prevVertices = 0;
    float prevLength = 0.0f;
    for (int history : {4, 8, 16, 32}) {
        TrailConfig cfg;
        cfg.historyLength = history;
        cfg.headWidth = 6.0f;
        cfg.tailWidth = 0.5f;
        TrailSystem system(cfg);
        Particle p(1, {40.0f, 90.0f}, {10.0f, 0.0f}, history);
        p.push(p.pos);
        system.spawn(p);
        simulate(system, kFrames);

        StripMesh mesh = system.buildStrip(0);
        DrawStats s = system.stats();
        float minX = mesh.vertices[0].pos.x;
        float maxX = mesh.vertices.back().pos.x;
        float lengthPx = maxX - minX;
        int expectedVertices = 2 * history;

        Framebuffer fb(560, 180);
        fb.clear({0.05f, 0.05f, 0.08f, 1.0f});
        renderTrails(fb, {mesh});
        std::string path =
            "artifacts/trail_h" + std::to_string(history) + ".ppm";
        fb.savePPM(path);

        std::cout << "  H=" << std::setw(2) << history
                  << " | vertices=" << std::setw(3)
                  << s.totalVertices
                  << " (expect " << expectedVertices << ")"
                  << " | batches=" << s.drawBatchesPerStrip
                  << "/" << s.drawBatchesMerged
                  << " | trail length=" << std::setw(6)
                  << std::fixed << std::setprecision(1) << lengthPx
                  << " px | " << path << '\n';

        check(s.totalVertices == expectedVertices,
              "H=" + std::to_string(history) + " vertex count is 2*H");
        if (history > 4) {
            check(s.totalVertices > prevVertices && lengthPx > prevLength,
                  "H=" + std::to_string(history) +
                      " produces a longer, heavier trail");
        }
        prevVertices = s.totalVertices;
        prevLength = lengthPx;
    }
}

void testMultiParticleBatches() {
    std::cout << "\n=== Test 5: vertex totals and draw batches ===\n";
    TrailConfig cfg;
    cfg.historyLength = 10;
    TrailSystem system(cfg);
    for (int i = 0; i < 3; ++i) {
        float fi = static_cast<float>(i);
        Particle p(i + 1, {30.0f, 40.0f + 30.0f * fi},
                   {12.0f + 2.0f * fi, 0.0f}, cfg.historyLength);
        p.push(p.pos);
        system.spawn(p);
    }
    simulate(system, 12);
    DrawStats s = system.stats();
    printStats(s);
    check(s.renderedStrips == 3, "all 3 particles produced a strip");
    check(s.drawBatchesPerStrip == 3, "naive path needs 3 draw batches");
    check(s.drawBatchesMerged == 1, "merged index buffer needs 1 batch");
    check(s.totalVertices == 3 * 2 * 10,
          "steady state vertices = particles * 2 * history length");
}

void testSharpTurnCoverage() {
    std::cout << "\n=== Test 7: sharp-turn miter clamp stays watertight ===\n";
    TrailConfig cfg;
    cfg.historyLength = 6;
    cfg.headWidth = 12.0f;
    cfg.tailWidth = 4.0f;
    cfg.miterLimit = 1.2f;
    TrailSystem system(cfg);
    // Zigzag path with ~90 degree turns forces miter clamping.
    Particle p(1, {60.0f, 60.0f}, {0.0f, 0.0f}, cfg.historyLength);
    p.push(p.pos);
    system.spawn(p);
    std::vector<Vec2> path = {
        {120.0f, 60.0f},  {120.0f, 120.0f}, {180.0f, 120.0f},
        {180.0f, 180.0f}, {240.0f, 180.0f},
    };
    for (const Vec2& point : path) {
        system.advance({point});
    }
    StripMesh mesh = system.buildStrip(0);
    check(mesh.vertices.size() > 12,
          "corner fan center vertices were emitted for clamped miters");

    Framebuffer probe(320, 260);
    int covered = countCoveragePixels(probe, {mesh});

    // For each corner, the eight pixels around the exact bend point must be
    // covered: a missing wedge would leave one of them transparent.
    std::vector<Vec2> corners = {
        {120.0f, 60.0f}, {120.0f, 120.0f}, {180.0f, 120.0f},
        {180.0f, 180.0f},
    };
    bool watertight = true;
    for (const Vec2& corner : corners) {
        int cx = static_cast<int>(corner.x);
        int cy = static_cast<int>(corner.y);
        for (int dy = -1; dy <= 1 && watertight; ++dy) {
            for (int dx = -1; dx <= 1; ++dx) {
                if (probe.readPixel(cx + dx, cy + dy).a <= 0.0f) {
                    watertight = false;
                    break;
                }
            }
        }
    }
    check(watertight, "no wedge gap at clamped-miter corners");
    std::cout << "  coverage=" << covered
              << " px, vertices=" << mesh.vertices.size()
              << " (12 ring verts + corner fans)\n";
}

void testMaterialGraph() {
    std::cout << "\n=== Test 6: dead-node pruning and topological sort ===\n";
    MaterialGraph graph;
    int uv = graph.addNode(NodeKind::Input, "UV");
    int time = graph.addNode(NodeKind::Input, "Time");
    int tex = graph.addNode(NodeKind::Texture, "NoiseTex");
    int mul = graph.addNode(NodeKind::Math, "Multiply");
    int add = graph.addNode(NodeKind::Math, "Add");
    int out = graph.addNode(NodeKind::Output, "Surface");
    int orphanConst = graph.addNode(NodeKind::Constant, "OrphanConst");
    int orphanMath = graph.addNode(NodeKind::Math, "OrphanMath");

    graph.addEdge(uv, tex);
    graph.addEdge(tex, mul);
    graph.addEdge(time, mul);
    graph.addEdge(mul, add);
    graph.addEdge(add, out);
    graph.addEdge(orphanConst, orphanMath);

    PruneResult pruned = graph.pruneDeadNodes();
    check(pruned.removedNodes ==
              (std::vector<int>{orphanConst, orphanMath}),
          "pruning removes the two unreachable nodes");
    check(pruned.keptNodes.size() == 6, "six live nodes remain");
    check(graph.edges().size() == 5,
          "edges touching dead nodes are removed with them");

    TopoResult topo = graph.topologicalSort();
    check(topo.ok, "acyclic graph sorts successfully");
    check(topo.order.back() == out, "Output node is last in topo order");
    auto pos = [&](int id) {
        return std::find(topo.order.begin(), topo.order.end(), id) -
               topo.order.begin();
    };
    bool orderValid = pos(uv) < pos(tex) && pos(tex) < pos(mul) &&
                      pos(time) < pos(mul) && pos(mul) < pos(add) &&
                      pos(add) < pos(out);
    check(orderValid, "every edge src precedes dst in topo order");

    MaterialGraph cyclic;
    int c0 = cyclic.addNode(NodeKind::Math, "A");
    int c1 = cyclic.addNode(NodeKind::Math, "B");
    int c2 = cyclic.addNode(NodeKind::Math, "C");
    int cOut = cyclic.addNode(NodeKind::Output, "Out");
    cyclic.addEdge(c0, c1);
    cyclic.addEdge(c1, c2);
    cyclic.addEdge(c2, c0);
    cyclic.addEdge(c0, cOut);
    TopoResult cycle = cyclic.topologicalSort();
    check(!cycle.ok, "cycle is detected instead of sorted");
    // Every node here has indegree >= 1, so Kahn's queue starts empty:
    // the cycle plus its downstream Output all remain unscheduled.
    std::vector<int> expectedCycle{c0, c1, c2, cOut};
    std::sort(cycle.cycleNodes.begin(), cycle.cycleNodes.end());
    check(cycle.cycleNodes == expectedCycle,
          "all four unschedulable nodes (cycle + downstream Output) are "
          "reported");

    PruneResult cyclicPruned = cyclic.pruneDeadNodes();
    check(cyclicPruned.removedNodes.empty(),
          "cycle nodes still reach Output, so none are pruned");
    TopoResult stillCyclic = cyclic.topologicalSort();
    check(!stillCyclic.ok, "pruning does not break a live cycle");
}

}  // namespace

int main() {
    testFastMovingContinuity();
    testWidthAndAlphaDecay();
    testAlphaBlending();
    testHistoryLengthSweep();
    testMultiParticleBatches();
    testSharpTurnCoverage();
    testMaterialGraph();

    std::cout << "\n=== Demo render: 3 translucent particle trails ===\n";
    {
        TrailConfig cfg;
        cfg.historyLength = 20;
        cfg.headWidth = 7.0f;
        cfg.tailWidth = 0.8f;
        cfg.headAlpha = 0.9f;
        cfg.tailAlpha = 0.05f;
        TrailSystem system(cfg);
        for (int i = 0; i < 3; ++i) {
            float fi = static_cast<float>(i);
            Particle p(i + 1, {40.0f, 80.0f + fi * 70.0f},
                       {14.0f, 6.0f - fi * 5.0f}, cfg.historyLength);
            p.push(p.pos);
            system.spawn(p);
        }
        simulate(system, 30);
        Framebuffer fb(640, 360);
        fb.clear({0.04f, 0.05f, 0.09f, 1.0f});
        renderTrails(fb, system.buildAllStrips());
        fb.savePPM("artifacts/demo_trails.ppm");
        DrawStats s = system.stats();
        printStats(s);
        std::cout << "  wrote artifacts/demo_trails.ppm\n";
    }

    std::cout << "\n" << (g_failures == 0 ? "ALL TESTS PASSED"
                                          : "SOME TESTS FAILED")
              << '\n';
    return g_failures == 0 ? 0 : 1;
}
