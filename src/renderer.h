#pragma once

#include "scene.h"

#include <cstdint>
#include <string>
#include <vector>

struct RenderFrame {
    int width = 0;
    int height = 0;
    std::vector<Vec3> color;
    std::vector<Vec3> normal;
    std::vector<Vec3> worldPosition;
    std::vector<double> depth;
    std::vector<int> objectId;
    Camera camera;
    int samplesPerPixel = 0;
    int frameIndex = 0;
};

RenderFrame renderFrame(const Scene& scene, const Camera& camera, int width, int height,
                        int samplesPerPixel, int frameIndex, std::uint64_t seed);

void writePpm(const std::string& path, const RenderFrame& frame);
void writePpm(const std::string& path, int width, int height, const std::vector<Vec3>& pixels);
void writePpm(const std::string& path, int width, int height, const std::vector<double>& values);

