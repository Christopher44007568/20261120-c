#include "metrics.h"

#include <algorithm>
#include <cmath>

double mseRgb(const std::vector<Vec3>& a, const std::vector<Vec3>& b) {
    if (a.size() != b.size() || a.empty()) {
        return 0.0;
    }
    double sum = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i) {
        const Vec3 difference = a[i] - b[i];
        sum += (difference.x * difference.x + difference.y * difference.y +
                difference.z * difference.z) /
               3.0;
    }
    return sum / static_cast<double>(a.size());
}

double mseLuminance(const std::vector<Vec3>& a, const std::vector<Vec3>& b) {
    if (a.size() != b.size() || a.empty()) {
        return 0.0;
    }
    double sum = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i) {
        const double difference = luminance(a[i]) - luminance(b[i]);
        sum += difference * difference;
    }
    return sum / static_cast<double>(a.size());
}

double meanAbsoluteLuminanceError(const std::vector<Vec3>& candidate,
                                  const std::vector<Vec3>& reference) {
    if (candidate.size() != reference.size() || candidate.empty()) {
        return 0.0;
    }
    double sum = 0.0;
    for (std::size_t i = 0; i < candidate.size(); ++i) {
        sum += std::abs(luminance(candidate[i]) - luminance(reference[i]));
    }
    return sum / static_cast<double>(candidate.size());
}

double meanTemporalLuminanceVariance(const std::vector<RenderFrame>& frames) {
    if (frames.empty() || frames.front().color.empty()) {
        return 0.0;
    }
    const std::size_t pixelCount = frames.front().color.size();
    double totalVariance = 0.0;
    for (std::size_t pixel = 0; pixel < pixelCount; ++pixel) {
        double mean = 0.0;
        for (const RenderFrame& frame : frames) {
            mean += luminance(frame.color[pixel]);
        }
        mean /= static_cast<double>(frames.size());
        double variance = 0.0;
        for (const RenderFrame& frame : frames) {
            const double difference = luminance(frame.color[pixel]) - mean;
            variance += difference * difference;
        }
        totalVariance += variance / static_cast<double>(frames.size());
    }
    return totalVariance / static_cast<double>(pixelCount);
}

std::vector<unsigned char> edgeMask(const RenderFrame& guide) {
    const int width = guide.width;
    const int height = guide.height;
    std::vector<unsigned char> mask(guide.color.size(), 0);
    for (int y = 1; y < height - 1; ++y) {
        for (int x = 1; x < width - 1; ++x) {
            const std::size_t pixel = static_cast<std::size_t>(y) * width + x;
            const std::size_t left = pixel - 1;
            const std::size_t right = pixel + 1;
            const std::size_t up = pixel - width;
            const std::size_t down = pixel + width;
            const double gradient =
                std::abs(luminance(guide.color[right]) - luminance(guide.color[left])) +
                std::abs(luminance(guide.color[down]) - luminance(guide.color[up]));
            bool normalDiscontinuity = false;
            bool depthDiscontinuity = false;
            if (guide.objectId[pixel] >= 0) {
                for (std::size_t neighbor : {left, right, up, down}) {
                    if (guide.objectId[neighbor] >= 0) {
                        normalDiscontinuity |=
                            dot(guide.normal[pixel], guide.normal[neighbor]) < 0.9;
                    }
                    const double relativeDepth =
                        std::abs(guide.depth[pixel] - guide.depth[neighbor]) /
                        std::max(1e-4, std::min(guide.depth[pixel], guide.depth[neighbor]));
                    depthDiscontinuity |= relativeDepth > 0.04;
                }
            }
            if (gradient > 0.045 || normalDiscontinuity || depthDiscontinuity) {
                mask[pixel] = 1;
            }
        }
    }
    return mask;
}

std::vector<unsigned char> ghostMask(const RenderFrame& candidate, const RenderFrame& raw,
                                    const RenderFrame& reference) {
    const int width = candidate.width;
    const int height = candidate.height;
    std::vector<unsigned char> mask(candidate.color.size(), 0);
    auto absoluteError = [&](std::size_t index) {
        return std::abs(luminance(candidate.color[index]) -
                        luminance(reference.color[index]));
    };
    auto rawError = [&](std::size_t index) {
        return std::abs(luminance(raw.color[index]) - luminance(reference.color[index]));
    };
    for (int y = 2; y < height - 2; ++y) {
        for (int x = 2; x < width - 2; ++x) {
            const std::size_t pixel = static_cast<std::size_t>(y) * width + x;
            double localRawError = 0.0;
            int localCount = 0;
            for (int dy = -1; dy <= 1; ++dy) {
                for (int dx = -1; dx <= 1; ++dx) {
                    localRawError += rawError(pixel + dy * width + dx);
                    ++localCount;
                }
            }
            localRawError /= localCount;
            const double threshold = std::max(0.055, localRawError + 0.018);
            mask[pixel] = absoluteError(pixel) > threshold ? 1 : 0;
        }
    }
    return mask;
}

double maskRatio(const std::vector<unsigned char>& mask) {
    if (mask.empty()) {
        return 0.0;
    }
    const std::size_t count = std::count(mask.begin(), mask.end(), static_cast<unsigned char>(1));
    return static_cast<double>(count) / static_cast<double>(mask.size());
}

double maskedRatio(const std::vector<unsigned char>& numerator,
                   const std::vector<unsigned char>& denominator) {
    if (numerator.size() != denominator.size() || numerator.empty()) {
        return 0.0;
    }
    std::size_t denominatorCount = 0;
    std::size_t numeratorCount = 0;
    for (std::size_t i = 0; i < numerator.size(); ++i) {
        denominatorCount += denominator[i] ? 1 : 0;
        numeratorCount += (numerator[i] && denominator[i]) ? 1 : 0;
    }
    return denominatorCount == 0 ? 0.0
                                 : static_cast<double>(numeratorCount) /
                                       static_cast<double>(denominatorCount);
}

int firstConvergedFrame(const std::vector<double>& errors, double target, int stableFrames) {
    if (errors.empty() || stableFrames <= 0) {
        return -1;
    }
    for (std::size_t i = 0; i < errors.size(); ++i) {
        if (errors[i] > target) {
            continue;
        }
        bool stable = true;
        for (int j = 0; j < stableFrames && i + static_cast<std::size_t>(j) < errors.size(); ++j) {
            if (errors[i + static_cast<std::size_t>(j)] > target) {
                stable = false;
                break;
            }
        }
        if (stable && i + static_cast<std::size_t>(stableFrames) <= errors.size()) {
            return static_cast<int>(i);
        }
    }
    return -1;
}

