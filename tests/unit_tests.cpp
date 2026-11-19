#include "denoiser.h"
#include "metrics.h"
#include "rng.h"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

namespace {

void expect(bool condition, const std::string& message) {
    if (!condition) {
        std::cerr << "FAILED: " << message << '\n';
        std::exit(1);
    }
}

RenderFrame makeFrame(int width, int height, int index, bool invertNormal = false) {
    RenderFrame frame;
    frame.width = width;
    frame.height = height;
    frame.samplesPerPixel = 2;
    frame.frameIndex = index;
    frame.camera.position = {0.0, 0.0, 0.0};
    frame.camera.target = {0.0, 0.0, -1.0};
    frame.camera.up = {0.0, 1.0, 0.0};
    frame.camera.update();
    const std::size_t pixelCount = static_cast<std::size_t>(width) * height;
    frame.color.assign(pixelCount, {});
    frame.normal.assign(pixelCount, Vec3(0.0, 0.0, invertNormal ? -1.0 : 1.0));
    frame.worldPosition.assign(pixelCount, {});
    frame.depth.assign(pixelCount, 3.0);
    frame.objectId.assign(pixelCount, 7);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const std::size_t pixel = static_cast<std::size_t>(y) * width + x;
            const Vec3 base = x < width / 2 ? Vec3(0.62, 0.30, 0.18)
                                             : Vec3(0.03, 0.10, 0.04);
            Rng rng(hashSeed(1234, pixel, static_cast<std::uint64_t>(index)));
            const Vec3 noise((rng.next() - 0.5) * 0.12, (rng.next() - 0.5) * 0.12,
                             (rng.next() - 0.5) * 0.12);
            frame.color[pixel] = base + noise;
            frame.worldPosition[pixel] = Vec3((x - width * 0.5) * 0.02,
                                               (y - height * 0.5) * 0.02, -3.0);
        }
    }
    return frame;
}

double meanLuminance(const std::vector<Vec3>& pixels, int width, int beginX, int endX) {
    double sum = 0.0;
    std::size_t count = 0;
    for (std::size_t pixel = 0; pixel < pixels.size(); ++pixel) {
        const int x = static_cast<int>(pixel % static_cast<std::size_t>(width));
        if (x >= beginX && x < endX) {
            sum += luminance(pixels[pixel]);
            ++count;
        }
    }
    return sum / static_cast<double>(count);
}

void testCameraRoundTrip() {
    Camera camera;
    camera.update();
    const int width = 32;
    const int height = 20;
    const int pixelX = 7;
    const int pixelY = 5;
    const Ray ray = camera.primaryRay(pixelX, pixelY, width, height);
    const Vec3 world = camera.position + ray.direction * 4.0;
    double projectedX = 0.0;
    double projectedY = 0.0;
    double depth = 0.0;
    double viewX = 0.0;
    double viewY = 0.0;
    expect(camera.project(world, width, height, projectedX, projectedY, depth, viewX, viewY),
           "camera projection should succeed");
    expect(std::abs(projectedX - pixelX) < 1e-9 && std::abs(projectedY - pixelY) < 1e-9,
           "camera projection should round-trip a primary-ray point");
    expect(std::abs(depth - 4.0 * dot(ray.direction, camera.forward)) < 1e-9,
           "camera should report positive view depth");
}

void testDenoiserPreservesEdgeAndReducesVariance() {
    const int width = 24;
    const int height = 8;
    std::vector<RenderFrame> raw;
    std::vector<RenderFrame> filtered;
    DenoiseState state;
    DenoiseParams params;
    for (int frameIndex = 0; frameIndex < 12; ++frameIndex) {
        raw.push_back(makeFrame(width, height, frameIndex));
        filtered.push_back(denoiseFrame(raw.back(), state, params));
    }
    const double rawVariance = meanTemporalLuminanceVariance(raw);
    const double filteredVariance = meanTemporalLuminanceVariance(filtered);
    expect(filteredVariance < rawVariance * 0.25,
           "temporal filtering should substantially reduce static noise variance");
    const double left = meanLuminance(filtered.back().color, width, 2, width / 2 - 2);
    const double right = meanLuminance(filtered.back().color, width, width / 2 + 2, width - 2);
    expect(left - right > 0.15, "bilateral filtering should retain the vertical color edge");
}

void testMismatchedNormalDropsHistory() {
    const int width = 12;
    const int height = 6;
    DenoiseState state;
    DenoiseParams params;
    const RenderFrame first = makeFrame(width, height, 1);
    const RenderFrame second = makeFrame(width, height, 2, true);
    denoiseFrame(first, state, params);
    DenoiseStats stats;
    const RenderFrame filtered = denoiseFrame(second, state, params, &stats);
    expect(stats.historyWeight[0] == 0.0f, "normal mismatch should remove history weight");
    expect(stats.historyMismatch[0] == 1, "normal mismatch should be reported");
    expect(std::abs(luminance(filtered.color[0]) -
                    luminance(makeFrame(width, height, 2, true).color[0])) < 0.35,
           "mismatched history must not dominate the current frame");
}

void testConvergenceSearch() {
    const std::vector<double> errors{1.0, 0.5, 0.1, 0.08, 0.07, 0.06};
    expect(firstConvergedFrame(errors, 0.11, 3) == 2,
           "convergence should return the first stable low-error frame");
    expect(firstConvergedFrame({0.2, 0.2, 0.2}, 0.1, 2) == -1,
           "convergence should return -1 when the target is never reached");
}

}  // namespace

int main() {
    testCameraRoundTrip();
    testDenoiserPreservesEdgeAndReducesVariance();
    testMismatchedNormalDropsHistory();
    testConvergenceSearch();
    std::cout << "all unit tests passed\n";
    return 0;
}

