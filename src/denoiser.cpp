#include "denoiser.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace {

bool inBounds(int x, int y, int width, int height) {
    return x >= 0 && y >= 0 && x < width && y < height;
}

Vec3 filterSpatial(const RenderFrame& frame, int centerX, int centerY,
                   const DenoiseParams& params) {
    const int width = frame.width;
    const int height = frame.height;
    const std::size_t center = static_cast<std::size_t>(centerY) * width + centerX;
    const Vec3 centerNormal = frame.normal[center];
    const double centerDepth = frame.depth[center];
    const double centerLuma = luminance(frame.color[center]);
    const int centerId = frame.objectId[center];
    Vec3 sum;
    double weightSum = 0.0;
    for (int dy = -params.spatialRadius; dy <= params.spatialRadius; ++dy) {
        for (int dx = -params.spatialRadius; dx <= params.spatialRadius; ++dx) {
            const int x = centerX + dx;
            const int y = centerY + dy;
            if (!inBounds(x, y, width, height)) {
                continue;
            }
            const std::size_t index = static_cast<std::size_t>(y) * width + x;
            const double spatial = std::exp(-(dx * dx + dy * dy) /
                                            (2.0 * params.sigmaSpatial * params.sigmaSpatial));
            double weight = spatial;
            if (centerId >= 0 && frame.objectId[index] >= 0) {
                const double normalDot = std::clamp(dot(centerNormal, frame.normal[index]), -1.0, 1.0);
                const double normalWeight =
                    std::exp((normalDot - 1.0) / std::max(params.sigmaNormal, 1e-6));
                const double relativeDepth =
                    std::abs(frame.depth[index] - centerDepth) /
                    std::max(1e-4, std::min(frame.depth[index], centerDepth));
                weight *= normalWeight * std::exp(-relativeDepth / params.sigmaDepth);
            } else if (centerId != frame.objectId[index]) {
                weight *= 0.03;
            }
            const double colorDifference = std::abs(luminance(frame.color[index]) - centerLuma);
            weight *= std::exp(-colorDifference / std::max(params.sigmaColor, 1e-6));
            sum += frame.color[index] * weight;
            weightSum += weight;
        }
    }
    return sum / std::max(weightSum, 1e-12);
}

}  // namespace

void DenoiseState::reset() {
    hasHistory = false;
    width = 0;
    height = 0;
    color.clear();
    normal.clear();
    worldPosition.clear();
    depth.clear();
    objectId.clear();
    historyLength.clear();
}

RenderFrame denoiseFrame(const RenderFrame& input, DenoiseState& state, const DenoiseParams& params,
                         DenoiseStats* stats) {
    if (input.width <= 0 || input.height <= 0) {
        throw std::invalid_argument("cannot denoise an empty frame");
    }
    const int width = input.width;
    const int height = input.height;
    const std::size_t pixelCount = static_cast<std::size_t>(width) * height;
    if (state.hasHistory && (state.width != width || state.height != height)) {
        state.reset();
    }

    RenderFrame output = input;
    output.color.assign(pixelCount, {});
    if (stats != nullptr) {
        stats->historyMismatch.assign(pixelCount, 0);
        stats->geometricMismatch.assign(pixelCount, 0);
        stats->photometricMismatch.assign(pixelCount, 0);
        stats->fastMotion.assign(pixelCount, 0);
        stats->historyWeight.assign(pixelCount, 0.0f);
        stats->screenMotionPixels.assign(pixelCount, 0.0f);
    }

    std::vector<Vec3> spatial(pixelCount);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const std::size_t pixel = static_cast<std::size_t>(y) * width + x;
            spatial[pixel] = filterSpatial(input, x, y, params);
        }
    }

    std::vector<float> nextLength(pixelCount, 1.0f);
    std::vector<Vec3> resolved(pixelCount);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const std::size_t pixel = static_cast<std::size_t>(y) * width + x;
            const Vec3 current = spatial[pixel];
            double historyWeight = 0.0;
            double effectiveLength = 1.0;
            bool geometricMismatch = true;
            bool photometricMismatch = false;
            double speedPixels = 0.0;
            double projectedX = static_cast<double>(x);
            double projectedY = static_cast<double>(y);

            if (state.hasHistory && input.objectId[pixel] >= 0) {
                double viewDepth = 0.0;
                double viewX = 0.0;
                double viewY = 0.0;
                const bool projects = state.previousCamera.project(
                    input.worldPosition[pixel], width, height, projectedX, projectedY,
                    viewDepth, viewX, viewY);
                if (projects) {
                    speedPixels = std::hypot(projectedX - x, projectedY - y);
                    const int historyX = static_cast<int>(std::lround(projectedX));
                    const int historyY = static_cast<int>(std::lround(projectedY));
                    if (inBounds(historyX, historyY, width, height)) {
                        const std::size_t historyPixel =
                            static_cast<std::size_t>(historyY) * width + historyX;
                        const double previousDepth = state.depth[historyPixel];
                        const double relativeDepthError =
                            std::abs(previousDepth - viewDepth) /
                            std::max(1e-4, std::min(previousDepth, viewDepth));
                        const bool sameSurface =
                            state.objectId[historyPixel] == input.objectId[pixel] &&
                            dot(state.normal[historyPixel], input.normal[pixel]) > 0.84 &&
                            relativeDepthError < 0.045;
                        if (sameSurface) {
                            geometricMismatch = false;
                            const double oldLength = state.historyLength[historyPixel];
                            const double confidence =
                                params.maxHistoryWeight * oldLength / (oldLength + 1.0);
                            const Vec3 historyColor = state.color[historyPixel];
                            const double colorDifference =
                                std::abs(luminance(historyColor) - luminance(current));
                            const double gate =
                                std::exp(-(colorDifference * colorDifference) /
                                         (params.colorGate * params.colorGate));
                            photometricMismatch = colorDifference > params.colorGate;
                            historyWeight = params.guardHistory ? confidence * gate : confidence;
                            effectiveLength = 1.0 + oldLength * historyWeight;
                            if (!params.guardHistory) {
                                photometricMismatch = false;
                            }
                        }
                    }
                }
            }

            if (!params.guardHistory && state.hasHistory) {
                const int historyX = std::clamp(static_cast<int>(std::lround(projectedX)), 0, width - 1);
                const int historyY = std::clamp(static_cast<int>(std::lround(projectedY)), 0, height - 1);
                const std::size_t historyPixel =
                    static_cast<std::size_t>(historyY) * width + historyX;
                const double oldLength = state.historyLength[historyPixel];
                historyWeight = params.maxHistoryWeight * oldLength / (oldLength + 1.0);
                effectiveLength = 1.0 + oldLength * historyWeight;
                geometricMismatch = false;
                photometricMismatch = false;
                const Vec3 historyColor = state.color[historyPixel];
                resolved[pixel] = current * (1.0 - historyWeight) + historyColor * historyWeight;
            } else if (historyWeight > 0.0) {
                const int historyX = static_cast<int>(std::lround(projectedX));
                const int historyY = static_cast<int>(std::lround(projectedY));
                const std::size_t historyPixel =
                    static_cast<std::size_t>(historyY) * width + historyX;
                const Vec3 historyColor = state.color[historyPixel];
                resolved[pixel] = current * (1.0 - historyWeight) + historyColor * historyWeight;
            } else {
                resolved[pixel] = current;
            }

            nextLength[pixel] = static_cast<float>(std::clamp(effectiveLength, 1.0, 65.0));
            output.color[pixel] = resolved[pixel];

            if (stats != nullptr) {
                const bool validSurface = input.objectId[pixel] >= 0;
                const bool mismatch = validSurface && (geometricMismatch || photometricMismatch);
                stats->historyMismatch[pixel] = mismatch ? 1 : 0;
                stats->geometricMismatch[pixel] =
                    (validSurface && geometricMismatch) ? 1 : 0;
                stats->photometricMismatch[pixel] =
                    (validSurface && photometricMismatch) ? 1 : 0;
                stats->fastMotion[pixel] = speedPixels >= params.fastMotionPixels ? 1 : 0;
                stats->historyWeight[pixel] = static_cast<float>(historyWeight);
                stats->screenMotionPixels[pixel] = static_cast<float>(speedPixels);
            }
        }
    }

    state.hasHistory = true;
    state.width = width;
    state.height = height;
    state.previousCamera = input.camera;
    state.color = output.color;
    state.normal = input.normal;
    state.worldPosition = input.worldPosition;
    state.depth = input.depth;
    state.objectId = input.objectId;
    state.historyLength = nextLength;
    return output;
}

