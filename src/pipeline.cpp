#include "pipeline.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

namespace vb {
namespace {

constexpr std::uint32_t kInvalidTriangle =
    std::numeric_limits<std::uint32_t>::max();
constexpr std::uint64_t kDepthBytes = sizeof(float);
constexpr std::uint64_t kTriangleIdBytes = sizeof(std::uint32_t);
constexpr std::uint64_t kVisibilityRecordBytes =
    kDepthBytes + kTriangleIdBytes;
constexpr std::uint64_t kGBufferBytes = 32;
constexpr std::uint64_t kColorBytes = sizeof(std::uint32_t);
constexpr int kResolveTileWidth = 16;
constexpr int kResolveTileHeight = 16;

struct GBuffer {
    Vec3 normal;
    Vec3 albedo;
    std::uint32_t material = 0;
    std::uint32_t params = 0;
};

static_assert(sizeof(GBuffer) == kGBufferBytes,
              "G-buffer layout must remain 32 bytes per pixel");

double elapsed_ms(std::chrono::steady_clock::time_point start) {
    const auto end = std::chrono::steady_clock::now();
    return std::chrono::duration<double, std::milli>(end - start).count();
}

float edge_function(const Vec3& a, const Vec3& b, float px, float py) {
    return (b.x - a.x) * (py - a.y) - (b.y - a.y) * (px - a.x);
}

bool is_top_left(const Vec3& a, const Vec3& b) {
    const float dx = b.x - a.x;
    const float dy = b.y - a.y;
    return dy < 0.0f || (dy == 0.0f && dx > 0.0f);
}

std::uint32_t pack_params(float roughness, float metallic) {
    const auto r = static_cast<std::uint32_t>(
        std::lround(std::clamp(roughness, 0.0f, 1.0f) * 255.0f));
    const auto m = static_cast<std::uint32_t>(
        std::lround(std::clamp(metallic, 0.0f, 1.0f) * 255.0f));
    return (m << 8u) | r;
}

void unpack_params(std::uint32_t params, float& roughness, float& metallic) {
    roughness = static_cast<float>(params & 0xffu) / 255.0f;
    metallic = static_cast<float>((params >> 8u) & 0xffu) / 255.0f;
}

std::uint32_t shade(Vec3 normal, Vec3 albedo, float roughness,
                    float metallic, float px, float py) {
    normal = normalize(normal);
    const Vec3 light = normalize({0.35f, 0.45f, 0.75f});
    const Vec3 view = {0.0f, 0.0f, 1.0f};
    const float ndotl = std::max(dot(normal, light), 0.0f);
    const Vec3 halfway = normalize(light + view);
    const float ndoth = std::max(dot(normal, halfway), 0.0f);
    const float shininess = 8.0f + (1.0f - roughness) * 120.0f;
    const float specular =
        std::pow(ndoth, shininess) * (0.08f + 0.92f * metallic);
    const float checker =
        (static_cast<int>(std::floor(px * 0.25f)) +
         static_cast<int>(std::floor(py * 0.25f))) &
        1;
    const float texture_variation = checker ? 0.92f : 1.0f;
    const float ambient = 0.17f;
    const float diffuse = 0.83f * ndotl;
    const auto to_byte = [](float value) {
        return static_cast<std::uint32_t>(
            std::lround(std::clamp(value, 0.0f, 1.0f) * 255.0f));
    };
    const std::uint32_t r =
        to_byte(albedo.x * texture_variation * (ambient + diffuse) + specular);
    const std::uint32_t g =
        to_byte(albedo.y * texture_variation * (ambient + diffuse) + specular);
    const std::uint32_t b =
        to_byte(albedo.z * texture_variation * (ambient + diffuse) + specular);
    return r | (g << 8u) | (b << 16u) | (0xffu << 24u);
}

std::uint64_t hash_pixel(std::uint64_t hash, std::size_t pixel_index,
                         std::uint32_t pixel) {
    std::uint64_t value =
        (static_cast<std::uint64_t>(pixel_index) << 32u) | pixel;
    value += 0x9e3779b97f4a7c15ull;
    value = (value ^ (value >> 30u)) * 0xbf58476d1ce4e5b9ull;
    value = (value ^ (value >> 27u)) * 0x94d049bb133111ebull;
    value ^= value >> 31u;
    return hash ^ value;
}

struct Barycentric {
    float w0 = 0.0f;
    float w1 = 0.0f;
    float w2 = 0.0f;
};

bool interpolate(const Triangle& triangle, float px, float py,
                 Barycentric& bary, Vec3& normal, Vec3& albedo) {
    const Vec3& a = triangle.vertices[0].position;
    const Vec3& b = triangle.vertices[1].position;
    const Vec3& c = triangle.vertices[2].position;
    const float area = edge_function(a, b, c.x, c.y);
    if (std::abs(area) <= 1.0e-8f) {
        return false;
    }
    bary.w0 = edge_function(b, c, px, py) / area;
    bary.w1 = edge_function(c, a, px, py) / area;
    bary.w2 = 1.0f - bary.w0 - bary.w1;
    normal = normalize(triangle.vertices[0].normal * bary.w0 +
                       triangle.vertices[1].normal * bary.w1 +
                       triangle.vertices[2].normal * bary.w2);
    albedo = {1.0f, 1.0f, 1.0f};
    return true;
}

template <typename FragmentWriter>
void rasterize(const Scene& scene, std::vector<float>& depth, Traffic& traffic,
               FragmentWriter&& write_fragment) {
    const std::size_t pixel_count =
        static_cast<std::size_t>(scene.width) * scene.height;
    depth.assign(pixel_count, std::numeric_limits<float>::infinity());

    for (std::uint32_t triangle_index = 0;
         triangle_index < scene.triangles.size(); ++triangle_index) {
        const Triangle& triangle = scene.triangles[triangle_index];
        const Vec3& a = triangle.vertices[0].position;
        const Vec3& b = triangle.vertices[1].position;
        const Vec3& c = triangle.vertices[2].position;
        const float area = edge_function(a, b, c.x, c.y);
        if (std::abs(area) <= 1.0e-8f) {
            continue;
        }

        const int min_x = std::max(
            0, static_cast<int>(std::floor(std::min({a.x, b.x, c.x}))));
        const int max_x = std::min(
            scene.width - 1,
            static_cast<int>(std::ceil(std::max({a.x, b.x, c.x}))));
        const int min_y = std::max(
            0, static_cast<int>(std::floor(std::min({a.y, b.y, c.y}))));
        const int max_y = std::min(
            scene.height - 1,
            static_cast<int>(std::ceil(std::max({a.y, b.y, c.y}))));

        for (int y = min_y; y <= max_y; ++y) {
            const float py = static_cast<float>(y) + 0.5f;
            for (int x = min_x; x <= max_x; ++x) {
                const float px = static_cast<float>(x) + 0.5f;
                const float e0 = edge_function(b, c, px, py);
                const float e1 = edge_function(c, a, px, py);
                const float e2 = edge_function(a, b, px, py);
                if (e0 < 0.0f || e1 < 0.0f || e2 < 0.0f) {
                    continue;
                }
                if ((e0 == 0.0f && !is_top_left(b, c)) ||
                    (e1 == 0.0f && !is_top_left(c, a)) ||
                    (e2 == 0.0f && !is_top_left(a, b))) {
                    continue;
                }

                ++traffic.fragments_tested;
                traffic.depth_read_bytes += kDepthBytes;
                const Barycentric bary{e0 / area, e1 / area, e2 / area};
                const float z = a.z * bary.w0 + b.z * bary.w1 +
                                c.z * bary.w2;
                const std::size_t pixel =
                    static_cast<std::size_t>(y) * scene.width + x;
                if (!(z < depth[pixel])) {
                    continue;
                }

                depth[pixel] = z;
                ++traffic.fragments_passed;
                traffic.depth_write_bytes += kDepthBytes;
                write_fragment(pixel, triangle_index, triangle, px, py, bary);
            }
        }
    }
}

}  // namespace

PipelineResult run_visibility_pipeline(const Scene& scene) {
    PipelineResult result;
    result.name = "Visibility Buffer";
    const std::size_t pixel_count =
        static_cast<std::size_t>(scene.width) * scene.height;
    std::vector<std::uint32_t> visibility(pixel_count, kInvalidTriangle);
    std::vector<float> depth;
    auto& traffic = result.traffic;

    const auto pass1_start = std::chrono::steady_clock::now();
    rasterize(scene, depth, traffic,
              [&](std::size_t pixel, std::uint32_t triangle_index,
                  const Triangle&, float, float, const Barycentric&) {
                  visibility[pixel] = triangle_index;
                  traffic.visibility_write_bytes += kTriangleIdBytes;
              });
    result.pass1_ms = elapsed_ms(pass1_start);

    std::vector<std::uint8_t> seen(scene.triangles.size(), 0);
    std::vector<std::uint32_t> tile_triangles;
    tile_triangles.reserve(kResolveTileWidth * kResolveTileHeight);
    std::uint64_t image_hash = 1469598103934665603ull;

    const auto pass2_start = std::chrono::steady_clock::now();
    for (int tile_y = 0; tile_y < scene.height;
         tile_y += kResolveTileHeight) {
        const int tile_y_end =
            std::min(tile_y + kResolveTileHeight, scene.height);
        for (int tile_x = 0; tile_x < scene.width;
             tile_x += kResolveTileWidth) {
            const int tile_x_end =
                std::min(tile_x + kResolveTileWidth, scene.width);
            tile_triangles.clear();
            for (int y = tile_y; y < tile_y_end; ++y) {
                for (int x = tile_x; x < tile_x_end; ++x) {
                    const std::size_t pixel =
                        static_cast<std::size_t>(y) * scene.width + x;
                    const std::uint32_t triangle_index = visibility[pixel];
                    if (triangle_index == kInvalidTriangle) {
                        continue;
                    }
                    traffic.visibility_read_bytes +=
                        kVisibilityRecordBytes;
                    if (std::find(tile_triangles.begin(), tile_triangles.end(),
                                  triangle_index) == tile_triangles.end()) {
                        tile_triangles.push_back(triangle_index);
                        traffic.triangle_attribute_bytes += sizeof(Triangle);
                        ++traffic.triangle_attribute_fetches;
                        if (seen[triangle_index] == 0) {
                            seen[triangle_index] = 1;
                            ++traffic.visible_triangles;
                        }
                    }
                }
            }

            for (int y = tile_y; y < tile_y_end; ++y) {
                const float py = static_cast<float>(y) + 0.5f;
                for (int x = tile_x; x < tile_x_end; ++x) {
                    const std::size_t pixel =
                        static_cast<std::size_t>(y) * scene.width + x;
                    const std::uint32_t triangle_index = visibility[pixel];
                    if (triangle_index == kInvalidTriangle) {
                        continue;
                    }
                    const float px = static_cast<float>(x) + 0.5f;
                    const Triangle& triangle =
                        scene.triangles[triangle_index];
                    Barycentric bary;
                    Vec3 normal;
                    Vec3 unused_albedo;
                    interpolate(triangle, px, py, bary, normal,
                                unused_albedo);
                    const Material& material =
                        scene.materials[triangle.material];
                    const std::uint32_t params =
                        pack_params(material.roughness, material.metallic);
                    float roughness = 0.0f;
                    float metallic = 0.0f;
                    unpack_params(params, roughness, metallic);
                    const std::uint32_t color =
                        shade(normal, material.albedo, roughness, metallic,
                              px, py);
                    image_hash =
                        hash_pixel(image_hash, pixel, color);
                    ++traffic.pixels_shaded;
                    traffic.color_write_bytes += kColorBytes;
                }
            }
        }
    }
    result.pass2_ms = elapsed_ms(pass2_start);
    result.total_ms = result.pass1_ms + result.pass2_ms;
    if (traffic.pixels_shaded > 0) {
        result.shading_ns_per_pixel =
            result.pass2_ms * 1.0e6 /
            static_cast<double>(traffic.pixels_shaded);
    }
    traffic.visibility_buffer_bytes =
        static_cast<std::uint64_t>(pixel_count) * kVisibilityRecordBytes;
    result.image_checksum = image_hash;
    return result;
}

PipelineResult run_deferred_pipeline(const Scene& scene) {
    PipelineResult result;
    result.name = "Deferred";
    const std::size_t pixel_count =
        static_cast<std::size_t>(scene.width) * scene.height;
    std::vector<float> depth;
    std::vector<GBuffer> gbuffer(pixel_count);
    auto& traffic = result.traffic;

    const auto pass1_start = std::chrono::steady_clock::now();
    rasterize(scene, depth, traffic,
              [&](std::size_t pixel, std::uint32_t,
                  const Triangle& triangle, float px, float py,
                  Barycentric bary) {
                  GBuffer& target = gbuffer[pixel];
                  Vec3 albedo;
                  interpolate(triangle, px, py, bary, target.normal, albedo);
                  const Material& material =
                      scene.materials[triangle.material];
                  target.albedo = material.albedo;
                  target.material = triangle.material;
                  target.params =
                      pack_params(material.roughness, material.metallic);
                  traffic.gbuffer_write_bytes += kGBufferBytes;
              });
    result.pass1_ms = elapsed_ms(pass1_start);

    std::uint64_t image_hash = 1469598103934665603ull;
    const auto pass2_start = std::chrono::steady_clock::now();
    for (int y = 0; y < scene.height; ++y) {
        const float py = static_cast<float>(y) + 0.5f;
        for (int x = 0; x < scene.width; ++x) {
            const std::size_t pixel =
                static_cast<std::size_t>(y) * scene.width + x;
            if (!std::isfinite(depth[pixel])) {
                continue;
            }
            const float px = static_cast<float>(x) + 0.5f;
            const GBuffer& source = gbuffer[pixel];
            traffic.depth_read_bytes += kDepthBytes;
            traffic.gbuffer_read_bytes += kGBufferBytes;
            float roughness = 0.0f;
            float metallic = 0.0f;
            unpack_params(source.params, roughness, metallic);
            const std::uint32_t color =
                shade(source.normal, source.albedo, roughness, metallic, px,
                      py);
            image_hash = hash_pixel(image_hash, pixel, color);
            ++traffic.pixels_shaded;
            traffic.color_write_bytes += kColorBytes;
        }
    }
    result.pass2_ms = elapsed_ms(pass2_start);
    result.total_ms = result.pass1_ms + result.pass2_ms;
    if (traffic.pixels_shaded > 0) {
        result.shading_ns_per_pixel =
            result.pass2_ms * 1.0e6 /
            static_cast<double>(traffic.pixels_shaded);
    }
    traffic.gbuffer_bytes = static_cast<std::uint64_t>(pixel_count) *
                            (kGBufferBytes + kDepthBytes);
    result.image_checksum = image_hash;
    return result;
}

}  // namespace vb
