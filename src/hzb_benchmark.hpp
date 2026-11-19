#pragma once

#include "scene.hpp"

#include <cstddef>
#include <string>
#include <vector>

namespace hzb {

struct ResolutionResult {
    int width = 0;
    int height = 0;
    int depthBits = 24;
    int mipLevels = 0;
    std::size_t objectTestsPerFrame = 0;
    std::size_t queryCountPerFrame = 0;
    std::size_t hzbDispatchCountPerFrame = 0;
    std::size_t culledObjects = 0;
    std::size_t exactOccludedObjects = 0;
    std::size_t falseCulledObjects = 0;
    double cullRate = 0.0;
    double exactOcclusionRate = 0.0;
    double precision = 1.0;
    double recall = 0.0;
    double falseCullRate = 0.0;
    double hzbBuildAndTestMs = 0.0;
    double perObjectQueryMs = 0.0;
    double speedup = 0.0;
};

struct BenchmarkReport {
    std::string renderer;
    std::string glVersion;
    std::size_t architectureCount = 0;
    std::size_t objectCount = 0;
    int timedFrames = 0;
    bool usesPreviousFrameDepth = true;
    std::vector<ResolutionResult> resolutions;
};

BenchmarkReport runHZBBenchmark(const Scene& scene, int timedFrames, std::string& error);

}  // namespace hzb
