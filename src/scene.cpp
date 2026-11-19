#include "types.hpp"

#include <algorithm>
#include <cmath>

namespace vb {

float dot(Vec3 a, Vec3 b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

Vec3 normalize(Vec3 v) {
    const float length = std::sqrt(dot(v, v));
    if (length <= 1.0e-8f) {
        return {0.0f, 0.0f, 1.0f};
    }
    return {v.x / length, v.y / length, v.z / length};
}

namespace {

Material make_material(std::uint32_t index) {
    const float phase = static_cast<float>(index) * 0.61803398875f;
    const float red = 0.15f + 0.75f * (0.5f + 0.5f * std::sin(phase * 6.28318f));
    const float green =
        0.15f + 0.70f * (0.5f + 0.5f * std::sin(phase * 6.28318f + 2.1f));
    const float blue =
        0.15f + 0.65f * (0.5f + 0.5f * std::sin(phase * 6.28318f + 4.2f));
    return {{red, green, blue},
            0.12f + 0.76f * static_cast<float>((index * 37u) % 101u) / 100.0f,
            0.05f + 0.90f * static_cast<float>((index * 53u) % 97u) / 96.0f};
}

Vertex make_vertex(float x, float y, float z, float u, float v, Vec3 normal) {
    return {{x, y, z}, normal, {u, v}};
}

}  // namespace

Scene make_scene(const std::string& name, const std::string& description,
                 const SceneConfig& config) {
    Scene scene;
    scene.name = name;
    scene.description = description;
    scene.width = config.width;
    scene.height = config.height;
    scene.layers = std::max(1, config.layers);

    const int cell_width = std::max(1, config.cell_width);
    const int cell_height = std::max(1, config.cell_height);
    const int columns = (config.width + cell_width - 1) / cell_width;
    const int rows = (config.height + cell_height - 1) / cell_height;
    const std::uint64_t cell_count =
        static_cast<std::uint64_t>(columns) * static_cast<std::uint64_t>(rows);
    const std::uint64_t estimated_triangles =
        cell_count * 2u * static_cast<std::uint64_t>(scene.layers);

    scene.materials.resize(std::max<std::uint32_t>(1, config.materials));
    scene.material_triangle_counts.assign(scene.materials.size(), 0);
    for (std::uint32_t i = 0; i < scene.materials.size(); ++i) {
        scene.materials[i] = make_material(i);
    }

    scene.triangles.reserve(static_cast<std::size_t>(estimated_triangles));
    for (int layer = 0; layer < scene.layers; ++layer) {
        const float depth =
            scene.layers == 1
                ? 0.5f
                : 0.9f - 0.8f * static_cast<float>(layer) /
                             static_cast<float>(scene.layers - 1);
        for (int row = 0; row < rows; ++row) {
            const int y0 = row * cell_height;
            const int y1 = std::min(y0 + cell_height, config.height);
            if (y1 <= y0) {
                continue;
            }
            for (int column = 0; column < columns; ++column) {
                const int x0 = column * cell_width;
                const int x1 = std::min(x0 + cell_width, config.width);
                if (x1 <= x0) {
                    continue;
                }

                const float xa = static_cast<float>(x0);
                const float xb = static_cast<float>(x1);
                const float ya = static_cast<float>(y0);
                const float yb = static_cast<float>(y1);
                const float u0 = xa / static_cast<float>(config.width);
                const float u1 = xb / static_cast<float>(config.width);
                const float v0 = ya / static_cast<float>(config.height);
                const float v1 = yb / static_cast<float>(config.height);

                const float source_x =
                    static_cast<float>(column) * 0.071f +
                    static_cast<float>(layer) * 0.37f;
                const float source_y =
                    static_cast<float>(row) * 0.053f +
                    static_cast<float>(layer) * 0.23f;
                const Vec3 normal = normalize(
                    {0.22f * std::sin(source_x),
                     0.22f * std::cos(source_y), 1.0f});

                const Vertex top_left =
                    make_vertex(xa, ya, depth, u0, v0, normal);
                const Vertex top_right =
                    make_vertex(xb, ya, depth, u1, v0, normal);
                const Vertex bottom_right =
                    make_vertex(xb, yb, depth, u1, v1, normal);
                const Vertex bottom_left =
                    make_vertex(xa, yb, depth, u0, v1, normal);

                const std::uint64_t cell =
                    static_cast<std::uint64_t>(row) * columns + column;
                const std::uint32_t material0 = static_cast<std::uint32_t>(
                    (cell * 13u + static_cast<std::uint64_t>(layer) * 7u) %
                    scene.materials.size());
                const std::uint32_t material1 = static_cast<std::uint32_t>(
                    (cell * 17u + static_cast<std::uint64_t>(layer) * 11u +
                     1u) %
                    scene.materials.size());

                scene.triangles.push_back(
                    {{top_left, top_right, bottom_right}, material0});
                scene.triangles.push_back(
                    {{top_left, bottom_right, bottom_left}, material1});
                ++scene.material_triangle_counts[material0];
                ++scene.material_triangle_counts[material1];
            }
        }
    }
    return scene;
}

}  // namespace vb
