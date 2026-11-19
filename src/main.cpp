#include "scene.h"
#include <chrono>
#include <cstdio>
#include <fstream>
#include <sys/resource.h>

static double nowMs() {
    return std::chrono::duration<double, std::milli>(
               std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

static long peakRssKb() {
    struct rusage ru;
    getrusage(RUSAGE_SELF, &ru);
    return ru.ru_maxrss;
}

struct FrameStats {
    double avgNodeVisits = 0;
    double avgTriTests = 0;
    double frameMs = 0;
    uint64_t rays = 0;
};

template <typename SceneT>
static FrameStats renderFrame(const SceneT& scene, const std::vector<Ray>& rays) {
    RayStats total;
    double t0 = nowMs();
    for (const auto& r : rays) {
        RayStats one;
        volatile float hit = scene.trace(r, one);
        (void)hit;
        total.nodeVisits += one.nodeVisits;
        total.triTests += one.triTests;
    }
    FrameStats fs;
    fs.frameMs = nowMs() - t0;
    fs.rays = rays.size();
    fs.avgNodeVisits = (double)total.nodeVisits / rays.size();
    fs.avgTriTests = (double)total.triTests / rays.size();
    return fs;
}

int main() {
    const int kInstances = 20000;
    printf("=== Two-level instancing BVH vs flat single-level BVH ===\n");
    printf("instances: %d\n\n", kInstances);

    // 1) unique meshes (bottom level), built once
    TwoLevelScene two;
    two.meshes.push_back({makeIcosphere(4), {}});   // 5120 tris
    two.meshes.push_back({makeTorus(48, 24, 1.0f, 0.4f), {}}); // 2304 tris
    two.meshes.push_back({makeSpikyBlob(6, 7), {}});           // 320 tris
    two.meshes.push_back({makeIcosphere(3), {}});   // 1280 tris
    two.meshes.push_back({makeTorus(32, 16, 1.2f, 0.35f), {}}); // 1024 tris
    two.meshes.push_back({makeSpikyBlob(9, 13), {}});           // 320 tris
    size_t uniqueTris = 0;
    for (auto& m : two.meshes) uniqueTris += m.tris.size();
    printf("unique meshes: %zu, unique triangles: %zu\n", two.meshes.size(), uniqueTris);

    double t0 = nowMs();
    two.uploadGeometry();
    double blasBuildMs = nowMs() - t0;

    // 2) instances: transforms only, no geometry copies
    std::mt19937 rng(42);
    std::uniform_real_distribution<float> pos(-180.0f, 180.0f);
    std::uniform_real_distribution<float> rot(0.0f, 6.2831853f);
    std::uniform_real_distribution<float> scl(0.8f, 2.5f);
    std::uniform_int_distribution<int> meshPick(0, (int)two.meshes.size() - 1);
    std::vector<Mat4> xforms(kInstances);
    two.instances.resize(kInstances);
    for (int i = 0; i < kInstances; ++i) {
        float s = scl(rng);
        xforms[i] = Mat4::compose({pos(rng), pos(rng) * 0.3f, pos(rng)}, rot(rng), {s, s, s});
        two.instances[i].meshId = meshPick(rng);
    }
    t0 = nowMs();
    two.updateInstances(xforms); // sets world AABBs + rebuilds TLAS
    double tlasBuildMs = nowMs() - t0;
    long rssAfterTwo = peakRssKb();

    // 3) flat single-level scene: bake every instance's triangles to world
    t0 = nowMs();
    FlatScene flat;
    flat.build(two.meshes, two.instances);
    double flatBuildMs = nowMs() - t0;
    long rssAfterFlat = peakRssKb();
    printf("flat scene triangles: %zu (geometry duplicated per instance)\n\n", flat.tris.size());

    // 4) camera rays for one frame
    const int W = 192, H = 192;
    std::vector<Ray> rays;
    rays.reserve(W * H);
    Vec3 eye{0, 40, 320};
    for (int y = 0; y < H; ++y)
        for (int x = 0; x < W; ++x) {
            float u = (x + 0.5f) / W - 0.5f;
            float v = (y + 0.5f) / H - 0.5f;
            Vec3 dir = Vec3{u * 1.6f, v * 1.2f - 0.12f, -1.0f}.normalized();
            rays.push_back(Ray::make(eye, dir));
        }

    // 5) correctness: identical hit distances on sample rays
    int mismatches = 0;
    for (int i = 0; i < 2000; ++i) {
        RayStats sa, sb;
        float ta = two.trace(rays[i * 7 % rays.size()], sa);
        float tb = flat.trace(rays[i * 7 % rays.size()], sb);
        bool ha = ta < 1e29f, hb = tb < 1e29f;
        if (ha != hb || (ha && std::fabs(ta - tb) > 1e-3f * std::max(1.0f, ta))) mismatches++;
    }
    printf("correctness: %d/2000 sample rays mismatched\n\n", mismatches);

    // 6) frame timings + traversal stats
    FrameStats fsTwo = renderFrame(two, rays);
    FrameStats fsFlat = renderFrame(flat, rays);

    // 7) animation: move all instances, verify no geometry re-upload for two-level
    for (int i = 0; i < kInstances; ++i) {
        Vec3 t{xforms[i].m[0][3] + 5.0f, xforms[i].m[1][3], xforms[i].m[2][3]};
        xforms[i] = Mat4::compose(t, 0.3f, {xforms[i].m[1][1], xforms[i].m[1][1], xforms[i].m[1][1]});
    }
    uint64_t geoBefore = two.geometryUploads;
    t0 = nowMs();
    two.updateInstances(xforms);
    double twoUpdateMs = nowMs() - t0;
    uint64_t twoGeoDelta = two.geometryUploads - geoBefore;

    uint64_t flatGeoBefore = flat.geometryUploads;
    t0 = nowMs();
    flat.build(two.meshes, two.instances); // flat must re-bake + re-upload everything
    double flatUpdateMs = nowMs() - t0;
    uint64_t flatGeoDelta = flat.geometryUploads - flatGeoBefore;

    // 8) report
    auto mb = [](uint64_t b) { return b / 1048576.0; };
    printf("%-22s %14s %14s\n", "", "two-level", "flat");
    printf("%-22s %14llu %14llu\n", "TLAS nodes", (unsigned long long)two.tlasNodeCount(), (unsigned long long)flat.nodeCount());
    printf("%-22s %14llu %14s\n", "BLAS nodes(shared)", (unsigned long long)two.blasNodeCount(), "-");
    printf("%-22s %14.1f %14.1f\n", "avg node visits", fsTwo.avgNodeVisits, fsFlat.avgNodeVisits);
    printf("%-22s %14.1f %14.1f\n", "avg tri tests", fsTwo.avgTriTests, fsFlat.avgTriTests);
    printf("%-22s %14.2f %14.2f\n", "frame time (ms)", fsTwo.frameMs, fsFlat.frameMs);
    printf("%-22s %14.2f %14.2f\n", "build time (ms)", blasBuildMs + tlasBuildMs, flatBuildMs);
    printf("%-22s %14.2f %14.2f\n", "memory (MB)", mb(two.memoryBytes()), mb(flat.memoryBytes()));
    printf("%-22s %14.2f %14.2f\n", "geo upload (MB)", mb(two.geometryUploads), mb(flatGeoBefore));
    printf("\nanimation update (move %d instances):\n", kInstances);
    printf("%-22s %14.2f %14.2f\n", "update time (ms)", twoUpdateMs, flatUpdateMs);
    printf("%-22s %14.2f %14.2f\n", "geo re-upload (MB)", mb(twoGeoDelta), mb(flatGeoDelta));
    printf("\nprocess peak RSS after two-level build: %.1f MB\n", rssAfterTwo / 1024.0);
    printf("process peak RSS after flat build:      %.1f MB\n", rssAfterFlat / 1024.0);
    printf("memory saving factor: %.1fx\n", (double)flat.memoryBytes() / two.memoryBytes());
    printf("node-visit reduction: %.1fx\n", fsFlat.avgNodeVisits / fsTwo.avgNodeVisits);
    printf("tri-test reduction:   %.1fx\n", fsFlat.avgTriTests / fsTwo.avgTriTests);

    std::ofstream csv("artifacts/results.csv");
    csv << "metric,two_level,flat\n";
    csv << "tlas_nodes," << two.tlasNodeCount() << "," << flat.nodeCount() << "\n";
    csv << "blas_nodes_shared," << two.blasNodeCount() << ",0\n";
    csv << "avg_node_visits," << fsTwo.avgNodeVisits << "," << fsFlat.avgNodeVisits << "\n";
    csv << "avg_tri_tests," << fsTwo.avgTriTests << "," << fsFlat.avgTriTests << "\n";
    csv << "frame_ms," << fsTwo.frameMs << "," << fsFlat.frameMs << "\n";
    csv << "build_ms," << blasBuildMs + tlasBuildMs << "," << flatBuildMs << "\n";
    csv << "memory_bytes," << two.memoryBytes() << "," << flat.memoryBytes() << "\n";
    csv << "geometry_upload_bytes," << two.geometryUploads << "," << flatGeoBefore << "\n";
    csv << "anim_update_ms," << twoUpdateMs << "," << flatUpdateMs << "\n";
    csv << "anim_geo_reupload_bytes," << twoGeoDelta << "," << flatGeoDelta << "\n";
    csv << "peak_rss_bytes," << rssAfterTwo * 1024L << "," << rssAfterFlat * 1024L << "\n";
    csv.close();
    printf("\nwrote artifacts/results.csv\n");

    // 9) single-mesh multi-instance scenario: prove transforms touch only TLAS boxes
    printf("\n=== single-mesh scenario: 1 mesh x %d instances ===\n", kInstances);
    TwoLevelScene s1;
    s1.meshes.push_back({makeIcosphere(3), {}}); // one shared mesh, 1280 tris
    s1.uploadGeometry();
    s1.instances.resize(kInstances);
    std::vector<Mat4> xf(kInstances);
    for (int i = 0; i < kInstances; ++i) {
        float s = scl(rng);
        xf[i] = Mat4::compose({pos(rng), pos(rng) * 0.3f, pos(rng)}, rot(rng), {s, s, s});
        s1.instances[i].meshId = 0;
    }
    s1.updateInstances(xf);
    uint64_t geo1 = s1.geometryUploads;
    // move every instance: only top-level AABBs + TLAS are touched
    for (int i = 0; i < kInstances; ++i)
        xf[i] = Mat4::compose({xf[i].m[0][3] + 10.0f, xf[i].m[1][3], xf[i].m[2][3]},
                              1.0f, {xf[i].m[1][1], xf[i].m[1][1], xf[i].m[1][1]});
    s1.updateInstances(xf);
    printf("geometry uploaded once: %.2f MB (%zu tris, 1 copy)\n",
           mb(geo1), s1.meshes[0].tris.size());
    printf("geometry re-uploaded after moving %d instances: %.2f MB\n", kInstances,
           mb(s1.geometryUploads - geo1));
    FlatScene f1;
    f1.build(s1.meshes, s1.instances);
    printf("memory: two-level %.2f MB vs flat %.2f MB (%.1fx)\n",
           mb(s1.memoryBytes()), mb(f1.memoryBytes()),
           (double)f1.memoryBytes() / s1.memoryBytes());

    std::ofstream csv2("artifacts/single_mesh.csv");
    csv2 << "metric,two_level,flat\n";
    csv2 << "geometry_upload_bytes," << geo1 << "," << f1.geometryUploads << "\n";
    csv2 << "geometry_reupload_after_move_bytes," << (s1.geometryUploads - geo1) << ","
         << f1.tris.size() * sizeof(Tri) << "\n";
    csv2 << "memory_bytes," << s1.memoryBytes() << "," << f1.memoryBytes() << "\n";
    csv2.close();
    printf("wrote artifacts/single_mesh.csv\n");
    return mismatches > 0 ? 1 : 0;
}
