#pragma once

#include "math.hpp"

#include <cstddef>
#include <vector>

namespace hzb {

struct Scene {
    Camera camera;
    std::vector<Aabb> architecture;
    std::vector<Aabb> objects;
    std::vector<float> vertices;
    std::size_t architectureVertexCount = 0;

    std::size_t objectVertexOffset(std::size_t objectIndex) const {
        return architectureVertexCount + objectIndex * 36;
    }
};

Scene makeDenseIndoorScene();

}  // namespace hzb
