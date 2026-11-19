#include "types.hpp"

#include "pipeline.hpp"

#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace vb {
namespace {

std::uint64_t traffic_bytes(const Traffic& traffic) {
    return traffic.depth_read_bytes + traffic.depth_write_bytes +
           traffic.gbuffer_write_bytes + traffic.gbuffer_read_bytes +
           traffic.visibility_write_bytes + traffic.visibility_read_bytes +
           traffic.triangle_attribute_bytes + traffic.color_write_bytes;
}

template <typename Renderer>
PipelineResult median_result(Renderer&& renderer, int runs) {
    if (runs < 1) {
        runs = 1;
    }
    std::vector<PipelineResult> results;
    results.reserve(static_cast<std::size_t>(runs));
    for (int run = 0; run < runs; ++run) {
        results.push_back(renderer());
    }

    const PipelineResult& reference = results.front();
    for (const PipelineResult& result : results) {
        if (result.image_checksum != reference.image_checksum) {
            throw std::runtime_error(
                "non-deterministic image checksum between benchmark runs");
        }
        if (result.traffic.pixels_shaded !=
                reference.traffic.pixels_shaded ||
            result.traffic.fragments_tested !=
                reference.traffic.fragments_tested ||
            result.traffic.fragments_passed !=
                reference.traffic.fragments_passed) {
            throw std::runtime_error(
                "non-deterministic traversal counts between benchmark runs");
        }
    }

    std::sort(results.begin(), results.end(),
              [](const PipelineResult& lhs, const PipelineResult& rhs) {
                  return lhs.total_ms < rhs.total_ms;
              });
    return results[results.size() / 2];
}

BenchmarkCase make_case(const std::string& name,
                        const std::string& description,
                        const SceneConfig& config,
                        const BenchmarkOptions& options) {
    Scene scene = make_scene(name, description, config);
    BenchmarkCase benchmark;
    benchmark.name = scene.name;
    benchmark.description = scene.description;
    benchmark.width = scene.width;
    benchmark.height = scene.height;
    benchmark.triangle_count = scene.triangles.size();
    benchmark.material_count =
        static_cast<std::uint32_t>(scene.materials.size());
    benchmark.layers = scene.layers;
    benchmark.visibility = median_result(
        [&]() { return run_visibility_pipeline(scene); }, options.runs);
    benchmark.deferred = median_result(
        [&]() { return run_deferred_pipeline(scene); }, options.runs);

    if (benchmark.visibility.image_checksum !=
        benchmark.deferred.image_checksum) {
        throw std::runtime_error("visibility/deferred image checksum mismatch");
    }
    if (traffic_bytes(benchmark.visibility.traffic) >=
        traffic_bytes(benchmark.deferred.traffic)) {
        throw std::runtime_error(
            "visibility buffer did not reduce bandwidth in case " +
            benchmark.name);
    }
    return benchmark;
}

}  // namespace

std::vector<BenchmarkCase> run_benchmarks(const BenchmarkOptions& options) {
    const int width = 1280;
    const int height = 720;
    std::vector<BenchmarkCase> cases;

    SceneConfig small;
    small.width = width;
    small.height = height;
    small.cell_width = 4;
    small.cell_height = 4;
    small.layers = 1;
    small.materials = 8;
    cases.push_back(make_case(
        "small_triangles_8mat",
        "115k roughly 8-pixel triangles, one layer, 8 materials",
        small, options));

    SceneConfig dense_8 = small;
    dense_8.layers = 6;
    dense_8.materials = 8;
    cases.push_back(make_case(
        "dense_small_8mat",
        "691k roughly 8-pixel triangles, six overlapping layers, 8 materials",
        dense_8, options));

    SceneConfig dense_64 = dense_8;
    dense_64.materials = 64;
    cases.push_back(make_case(
        "dense_small_64mat",
        "same dense geometry with 64 materials",
        dense_64, options));

    SceneConfig tiny_dense = dense_64;
    tiny_dense.cell_width = 2;
    tiny_dense.cell_height = 2;
    tiny_dense.layers = 4;
    cases.push_back(make_case(
        "tiny_dense_64mat",
        "1.8M roughly 2-pixel triangles, four layers, 64 materials",
        tiny_dense, options));

    return cases;
}

int run_self_test() {
    SceneConfig config;
    config.width = 160;
    config.height = 90;
    config.cell_width = 4;
    config.cell_height = 4;
    config.layers = 2;
    config.materials = 7;

    const Scene scene = make_scene("self_test", "small deterministic scene",
                                   config);
    const PipelineResult visibility = run_visibility_pipeline(scene);
    const PipelineResult deferred = run_deferred_pipeline(scene);
    const std::uint64_t pixel_count =
        static_cast<std::uint64_t>(config.width) * config.height;

    if (visibility.image_checksum != deferred.image_checksum) {
        throw std::runtime_error(
            "self-test: visibility and deferred images differ");
    }
    if (visibility.traffic.pixels_shaded != pixel_count ||
        deferred.traffic.pixels_shaded != pixel_count) {
        throw std::runtime_error(
            "self-test: scene did not cover every pixel exactly once");
    }
    if (visibility.traffic.fragments_passed !=
        deferred.traffic.fragments_passed) {
        throw std::runtime_error(
            "self-test: pipelines disagree on depth-test results");
    }
    if (visibility.traffic.visibility_buffer_bytes != pixel_count * 8u ||
        deferred.traffic.gbuffer_bytes != pixel_count * 36u) {
        throw std::runtime_error(
            "self-test: render-target occupancy is incorrect");
    }
    if (visibility.traffic.visibility_write_bytes !=
        visibility.traffic.fragments_passed * 4u) {
        throw std::runtime_error(
            "self-test: visibility pass wrote more than triangle IDs");
    }
    if (visibility.traffic.gbuffer_write_bytes != 0 ||
        deferred.traffic.visibility_write_bytes != 0) {
        throw std::runtime_error(
            "self-test: pipeline render targets became cross-contaminated");
    }
    if (traffic_bytes(visibility.traffic) >= traffic_bytes(deferred.traffic)) {
        throw std::runtime_error(
            "self-test: visibility buffer did not reduce traffic");
    }

    SceneConfig many_materials = config;
    many_materials.materials = 47;
    const Scene color_variants =
        make_scene("self_test_materials", "material-count check",
                   many_materials);
    const PipelineResult visibility_variants =
        run_visibility_pipeline(color_variants);
    const PipelineResult deferred_variants =
        run_deferred_pipeline(color_variants);
    if (traffic_bytes(visibility.traffic) !=
            traffic_bytes(visibility_variants.traffic) ||
        traffic_bytes(deferred.traffic) !=
            traffic_bytes(deferred_variants.traffic)) {
        throw std::runtime_error(
            "self-test: material count changed deterministic traffic");
    }
    return 0;
}

}  // namespace vb
