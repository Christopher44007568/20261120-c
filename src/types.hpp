#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace vb {

struct Vec2 {
    float x = 0.0f;
    float y = 0.0f;
};

struct Vec3 {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;
};

inline Vec3 operator+(Vec3 a, Vec3 b) {
    return {a.x + b.x, a.y + b.y, a.z + b.z};
}

inline Vec3 operator-(Vec3 a, Vec3 b) {
    return {a.x - b.x, a.y - b.y, a.z - b.z};
}

inline Vec3 operator*(Vec3 v, float s) {
    return {v.x * s, v.y * s, v.z * s};
}

inline Vec3 mix(Vec3 a, Vec3 b, float t) {
    return a + (b - a) * t;
}

float dot(Vec3 a, Vec3 b);
Vec3 normalize(Vec3 v);

struct Vertex {
    Vec3 position;
    Vec3 normal;
    Vec2 uv;
};

struct Triangle {
    Vertex vertices[3];
    std::uint32_t material = 0;
};

struct Material {
    Vec3 albedo;
    float roughness = 0.5f;
    float metallic = 0.0f;
};

struct Scene {
    std::string name;
    std::string description;
    int width = 0;
    int height = 0;
    int layers = 1;
    std::vector<Triangle> triangles;
    std::vector<Material> materials;
    std::vector<std::uint32_t> material_triangle_counts;
};

struct SceneConfig {
    int width = 1280;
    int height = 720;
    int cell_width = 4;
    int cell_height = 4;
    int layers = 1;
    std::uint32_t materials = 8;
};

Scene make_scene(const std::string& name, const std::string& description,
                 const SceneConfig& config);

struct Traffic {
    std::uint64_t depth_read_bytes = 0;
    std::uint64_t depth_write_bytes = 0;
    std::uint64_t gbuffer_write_bytes = 0;
    std::uint64_t gbuffer_read_bytes = 0;
    std::uint64_t visibility_write_bytes = 0;
    std::uint64_t visibility_read_bytes = 0;
    std::uint64_t triangle_attribute_bytes = 0;
    std::uint64_t color_write_bytes = 0;
    std::uint64_t fragments_tested = 0;
    std::uint64_t fragments_passed = 0;
    std::uint64_t pixels_shaded = 0;
    std::uint64_t visible_triangles = 0;
    std::uint64_t triangle_attribute_fetches = 0;
    std::uint64_t visibility_buffer_bytes = 0;
    std::uint64_t gbuffer_bytes = 0;
};

struct PipelineResult {
    std::string name;
    Traffic traffic;
    double pass1_ms = 0.0;
    double pass2_ms = 0.0;
    double total_ms = 0.0;
    double shading_ns_per_pixel = 0.0;
    std::uint64_t image_checksum = 0;
};

struct BenchmarkOptions {
    int runs = 3;
};

struct BenchmarkCase {
    std::string name;
    std::string description;
    int width = 0;
    int height = 0;
    std::uint64_t triangle_count = 0;
    std::uint32_t material_count = 0;
    int layers = 1;
    PipelineResult visibility;
    PipelineResult deferred;
};

std::vector<BenchmarkCase> run_benchmarks(const BenchmarkOptions& options);
int run_self_test();

}  // namespace vb
