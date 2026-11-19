#include "denoiser.h"
#include "metrics.h"
#include "renderer.h"
#include "scene.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct Options {
    int width = 160;
    int height = 120;
    int staticFrames = 40;
    int movingFrames = 16;
    int samplesPerPixel = 2;
    int referenceSamples = 256;
    double convergenceMse = -1.0;
    std::string outputDirectory = "artifacts";
};

Options parseOptions(int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const std::string argument = argv[i];
        auto requireValue = [&](const char* name) -> std::string {
            if (i + 1 >= argc) {
                throw std::runtime_error(std::string("missing value for ") + name);
            }
            return argv[++i];
        };
        if (argument == "--width") {
            options.width = std::stoi(requireValue("--width"));
        } else if (argument == "--height") {
            options.height = std::stoi(requireValue("--height"));
        } else if (argument == "--static-frames") {
            options.staticFrames = std::stoi(requireValue("--static-frames"));
        } else if (argument == "--moving-frames") {
            options.movingFrames = std::stoi(requireValue("--moving-frames"));
        } else if (argument == "--spp") {
            options.samplesPerPixel = std::stoi(requireValue("--spp"));
        } else if (argument == "--ref-spp") {
            options.referenceSamples = std::stoi(requireValue("--ref-spp"));
        } else if (argument == "--convergence-mse") {
            options.convergenceMse = std::stod(requireValue("--convergence-mse"));
        } else if (argument == "--output") {
            options.outputDirectory = requireValue("--output");
        } else if (argument == "--quick") {
            options.width = 128;
            options.height = 96;
            options.staticFrames = 24;
            options.movingFrames = 12;
            options.referenceSamples = 96;
        } else if (argument == "--help") {
            std::cout << "Usage: pt_denoise [--width N] [--height N] [--static-frames N]\n"
                         "                  [--moving-frames N] [--spp N] [--ref-spp N]\n"
                         "                  [--convergence-mse X] [--output DIR] [--quick]\n";
            std::exit(0);
        } else {
            throw std::runtime_error("unknown argument: " + argument);
        }
    }
    return options;
}

std::uint64_t countMask(const std::vector<unsigned char>& mask) {
    return static_cast<std::uint64_t>(
        std::count(mask.begin(), mask.end(), static_cast<unsigned char>(1)));
}

std::vector<unsigned char> dilateMask(const std::vector<unsigned char>& mask, int width,
                                      int height, int radius) {
    std::vector<unsigned char> result(mask.size(), 0);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            if (!mask[static_cast<std::size_t>(y) * width + x]) {
                continue;
            }
            for (int dy = -radius; dy <= radius; ++dy) {
                for (int dx = -radius; dx <= radius; ++dx) {
                    const int targetX = x + dx;
                    const int targetY = y + dy;
                    if (targetX >= 0 && targetY >= 0 && targetX < width && targetY < height) {
                        result[static_cast<std::size_t>(targetY) * width + targetX] = 1;
                    }
                }
            }
        }
    }
    return result;
}

double overlapFraction(const std::vector<unsigned char>& mask,
                       const std::vector<unsigned char>& region) {
    const std::uint64_t maskCount = countMask(mask);
    if (maskCount == 0) {
        return 0.0;
    }
    std::uint64_t overlap = 0;
    for (std::size_t i = 0; i < mask.size(); ++i) {
        overlap += (mask[i] && region[i]) ? 1 : 0;
    }
    return static_cast<double>(overlap) / static_cast<double>(maskCount);
}

std::vector<Vec3> maskImage(const std::vector<unsigned char>& mask) {
    std::vector<Vec3> image(mask.size());
    for (std::size_t i = 0; i < mask.size(); ++i) {
        image[i] = mask[i] ? Vec3(1.0, 0.12, 0.04) : Vec3(0.02, 0.02, 0.02);
    }
    return image;
}

void printProgress(const char* label, int current, int total) {
    if (current == total || current % 8 == 0) {
        std::cout << label << " " << current << "/" << total << '\n';
    }
}

struct FrameMetrics {
    std::vector<RenderFrame> rawFrames;
    std::vector<RenderFrame> denoisedFrames;
    std::vector<double> rawMse;
    std::vector<double> denoisedMse;
    std::vector<double> mismatchRatio;
    DenoiseStats finalStats;
};

FrameMetrics runStaticSequence(const Scene& scene, const Camera& camera, const Options& options) {
    FrameMetrics result;
    DenoiseState state;
    DenoiseParams params;
    for (int frameIndex = 0; frameIndex < options.staticFrames; ++frameIndex) {
        const RenderFrame raw =
            renderFrame(scene, camera, options.width, options.height,
                        options.samplesPerPixel, frameIndex, 1000 + frameIndex);
        DenoiseStats stats;
        const RenderFrame denoised = denoiseFrame(raw, state, params, &stats);
        result.rawFrames.push_back(raw);
        result.denoisedFrames.push_back(denoised);
        result.finalStats = stats;
        if (!result.rawFrames.empty() && result.rawFrames.size() > 1) {
            result.mismatchRatio.push_back(maskRatio(stats.historyMismatch));
        } else {
            result.mismatchRatio.push_back(0.0);
        }
        printProgress("static", frameIndex + 1, options.staticFrames);
    }
    return result;
}

struct MovingResult {
    RenderFrame rawFinal;
    RenderFrame denoisedFinal;
    RenderFrame naiveFinal;
    RenderFrame referenceFinal;
    DenoiseStats guardedFinalStats;
    std::vector<double> mismatchRatio;
    std::vector<double> geometricMismatchRatio;
    std::vector<double> photometricMismatchRatio;
};

MovingResult runMovingSequence(const Scene& scene, const Camera& baseCamera,
                               const Options& options) {
    MovingResult result;
    DenoiseState guardedState;
    DenoiseState naiveState;
    DenoiseParams guardedParams;
    DenoiseParams naiveParams;
    naiveParams.guardHistory = false;
    for (int frameIndex = 0; frameIndex < options.movingFrames; ++frameIndex) {
        Camera camera = baseCamera;
        camera.position.x += 0.075 * frameIndex;
        camera.update();
        const RenderFrame raw =
            renderFrame(scene, camera, options.width, options.height,
                        options.samplesPerPixel, frameIndex, 5000 + frameIndex);
        DenoiseStats stats;
        result.denoisedFinal = denoiseFrame(raw, guardedState, guardedParams, &stats);
        result.naiveFinal = denoiseFrame(raw, naiveState, naiveParams, nullptr);
        result.rawFinal = raw;
        result.guardedFinalStats = stats;
        if (frameIndex > 0) {
            result.mismatchRatio.push_back(maskRatio(stats.historyMismatch));
            result.geometricMismatchRatio.push_back(maskRatio(stats.geometricMismatch));
            result.photometricMismatchRatio.push_back(maskRatio(stats.photometricMismatch));
        }
        printProgress("moving", frameIndex + 1, options.movingFrames);
    }
    result.referenceFinal =
        renderFrame(scene, result.rawFinal.camera, options.width, options.height,
                    options.referenceSamples, options.movingFrames, 9000);
    return result;
}

double mean(const std::vector<double>& values) {
    if (values.empty()) {
        return 0.0;
    }
    return std::accumulate(values.begin(), values.end(), 0.0) /
           static_cast<double>(values.size());
}

double percentile(std::vector<double> values, double fraction) {
    if (values.empty()) {
        return 0.0;
    }
    std::sort(values.begin(), values.end());
    const double position = fraction * static_cast<double>(values.size() - 1);
    const std::size_t lower = static_cast<std::size_t>(std::floor(position));
    const std::size_t upper = static_cast<std::size_t>(std::ceil(position));
    const double blend = position - static_cast<double>(lower);
    return values[lower] * (1.0 - blend) + values[upper] * blend;
}

std::vector<Vec3> motionImage(const std::vector<float>& motionPixels) {
    std::vector<Vec3> image(motionPixels.size());
    for (std::size_t i = 0; i < motionPixels.size(); ++i) {
        const double value = std::clamp(motionPixels[i] / 5.0, 0.0, 1.0);
        image[i] = Vec3(value, value, value);
    }
    return image;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const Options options = parseOptions(argc, argv);
        const std::filesystem::path outputRoot(options.outputDirectory);
        const std::filesystem::path imageRoot = outputRoot / "images";
        std::filesystem::create_directories(imageRoot);

        const auto started = std::chrono::steady_clock::now();
        Scene scene;
        Camera staticCamera;
        staticCamera.update();

        std::cout << "Rendering static-camera sequence and reference...\n";
        const FrameMetrics staticRun =
            runStaticSequence(scene, staticCamera, options);
        const RenderFrame staticReference =
            renderFrame(scene, staticCamera, options.width, options.height,
                        options.referenceSamples, options.staticFrames, 7000);

        std::vector<double> staticRawMseSequence;
        std::vector<double> staticDenoisedMseSequence;
        staticRawMseSequence.reserve(staticRun.rawFrames.size());
        staticDenoisedMseSequence.reserve(staticRun.denoisedFrames.size());
        for (std::size_t i = 0; i < staticRun.rawFrames.size(); ++i) {
            staticRawMseSequence.push_back(
                mseRgb(staticRun.rawFrames[i].color, staticReference.color));
            staticDenoisedMseSequence.push_back(
                mseRgb(staticRun.denoisedFrames[i].color, staticReference.color));
        }

        const RenderFrame& staticRawFinal = staticRun.rawFrames.back();
        const RenderFrame& staticDenoisedFinal = staticRun.denoisedFrames.back();
        const std::vector<unsigned char> staticEdges = edgeMask(staticReference);
        const std::vector<unsigned char> staticGhosts =
            ghostMask(staticDenoisedFinal, staticRawFinal, staticReference);
        const double staticTemporalVarianceRaw =
            meanTemporalLuminanceVariance(staticRun.rawFrames);
        const double staticTemporalVarianceDenoised =
            meanTemporalLuminanceVariance(staticRun.denoisedFrames);
        const double staticRawMse = mseRgb(staticRawFinal.color, staticReference.color);
        const double staticDenoisedMse =
            mseRgb(staticDenoisedFinal.color, staticReference.color);
        const double staticRawLumaVariance =
            mseLuminance(staticRawFinal.color, staticReference.color);
        const double staticDenoisedLumaVariance =
            mseLuminance(staticDenoisedFinal.color, staticReference.color);
        const double convergenceTarget =
            options.convergenceMse > 0.0
                ? options.convergenceMse
                : std::max(1e-8, staticDenoisedMse * 1.15);
        const int convergenceIndex =
            firstConvergedFrame(staticDenoisedMseSequence, convergenceTarget, 4);
        const int convergenceFrame = convergenceIndex >= 0 ? convergenceIndex + 1 : -1;
        const double staticEdgeGhostRatio = maskedRatio(staticGhosts, staticEdges);

        writePpm((imageRoot / "static_raw.ppm").string(), staticRawFinal);
        writePpm((imageRoot / "static_denoised.ppm").string(), staticDenoisedFinal);
        writePpm((imageRoot / "static_reference.ppm").string(), staticReference);
        writePpm((imageRoot / "static_frame_000_raw.ppm").string(), staticRun.rawFrames.front());
        writePpm((imageRoot / "static_frame_000_denoised.ppm").string(),
                 staticRun.denoisedFrames.front());
        writePpm((imageRoot / "static_edge_mask.ppm").string(), options.width,
                 options.height, maskImage(staticEdges));
        writePpm((imageRoot / "static_ghost_mask.ppm").string(), options.width,
                 options.height, maskImage(staticGhosts));

        std::ofstream staticCsv(outputRoot / "static_convergence.csv");
        staticCsv << "frame,raw_mse,denoised_mse,history_mismatch_ratio\n";
        staticCsv << std::setprecision(10);
        for (std::size_t i = 0; i < staticRawMseSequence.size(); ++i) {
            staticCsv << i + 1 << ',' << staticRawMseSequence[i] << ','
                      << staticDenoisedMseSequence[i]
                      << ',' << staticRun.mismatchRatio[i] << '\n';
        }

        std::cout << "Rendering moving-camera sequence and reference...\n";
        const MovingResult movingRun =
            runMovingSequence(scene, staticCamera, options);
        const std::vector<unsigned char> movingEdges = edgeMask(movingRun.referenceFinal);
        const std::vector<unsigned char> movingGhostsGuarded =
            ghostMask(movingRun.denoisedFinal, movingRun.rawFinal, movingRun.referenceFinal);
        const std::vector<unsigned char> movingGhostsNaive =
            ghostMask(movingRun.naiveFinal, movingRun.rawFinal, movingRun.referenceFinal);
        std::vector<double> motionPixels;
        motionPixels.reserve(movingRun.guardedFinalStats.screenMotionPixels.size());
        for (float speed : movingRun.guardedFinalStats.screenMotionPixels) {
            motionPixels.push_back(speed);
        }
        const double motionP50 = percentile(motionPixels, 0.50);
        const double motionP75 = percentile(motionPixels, 0.75);
        const double motionP90 = percentile(motionPixels, 0.90);
        const double motionP95 = percentile(motionPixels, 0.95);
        std::vector<unsigned char> fastScreenMotion(motionPixels.size(), 0);
        for (std::size_t i = 0; i < motionPixels.size(); ++i) {
            fastScreenMotion[i] =
                motionPixels[i] >= std::max(0.75, motionP50) ? 1 : 0;
        }
        const double motionContrastThreshold =
            std::max(0.04, 0.20 * (motionP75 - motionP50));
        for (int y = 0; y < options.height; ++y) {
            for (int x = 0; x < options.width; ++x) {
                double localMinimum = 1e30;
                double localMaximum = -1e30;
                for (int dy = -1; dy <= 1; ++dy) {
                    for (int dx = -1; dx <= 1; ++dx) {
                        const int sampleX = x + dx;
                        const int sampleY = y + dy;
                        if (sampleX < 0 || sampleY < 0 || sampleX >= options.width ||
                            sampleY >= options.height) {
                            continue;
                        }
                        const double speed = motionPixels[
                            static_cast<std::size_t>(sampleY) * options.width + sampleX];
                        localMinimum = std::min(localMinimum, speed);
                        localMaximum = std::max(localMaximum, speed);
                    }
                }
                if (localMaximum - localMinimum >= motionContrastThreshold) {
                    fastScreenMotion[static_cast<std::size_t>(y) * options.width + x] = 1;
                }
                if (x < 3 || y < 3 || x >= options.width - 3 || y >= options.height - 3) {
                    fastScreenMotion[static_cast<std::size_t>(y) * options.width + x] = 1;
                }
            }
        }
        const std::vector<unsigned char> fastMotion =
            dilateMask(fastScreenMotion, options.width, options.height, 1);
        const std::vector<unsigned char> mismatchFinal =
            movingRun.guardedFinalStats.historyMismatch;

        const double movingRawMse =
            mseRgb(movingRun.rawFinal.color, movingRun.referenceFinal.color);
        const double movingDenoisedMse =
            mseRgb(movingRun.denoisedFinal.color, movingRun.referenceFinal.color);
        const double movingNaiveMse =
            mseRgb(movingRun.naiveFinal.color, movingRun.referenceFinal.color);
        const double movingGhostRatioAfter = maskRatio(movingGhostsGuarded);
        const double movingGhostRatioBefore = maskRatio(movingGhostsNaive);
        const double movingMismatchMean = mean(movingRun.mismatchRatio);
        const double movingMismatchFinal = maskRatio(mismatchFinal);
        const double movingGeometricMismatchMean = mean(movingRun.geometricMismatchRatio);
        const double movingPhotometricMismatchMean = mean(movingRun.photometricMismatchRatio);
        const double movingFastPixelRatio = maskRatio(fastMotion);
        const double movingMismatchFastFraction =
            overlapFraction(mismatchFinal, fastMotion);
        const double movingNaiveGhostFastFraction =
            overlapFraction(movingGhostsNaive, fastMotion);
        const double movingGuardedGhostFastFraction =
            overlapFraction(movingGhostsGuarded, fastMotion);
        std::uint64_t movingNaiveGhostOutsideFast = 0;
        std::uint64_t movingGuardedGhostOutsideFast = 0;
        for (std::size_t i = 0; i < fastMotion.size(); ++i) {
            movingNaiveGhostOutsideFast +=
                (movingGhostsNaive[i] && !fastMotion[i]) ? 1 : 0;
            movingGuardedGhostOutsideFast +=
                (movingGhostsGuarded[i] && !fastMotion[i]) ? 1 : 0;
        }
        const double movingEdgeGhostRatio =
            maskedRatio(movingGhostsGuarded, movingEdges);
        const double movingNaiveEdgeGhostRatio =
            maskedRatio(movingGhostsNaive, movingEdges);
        std::vector<double> naiveGhostMotion;
        std::vector<double> guardedGhostMotion;
        for (std::size_t i = 0; i < fastMotion.size(); ++i) {
            const double speed = movingRun.guardedFinalStats.screenMotionPixels[i];
            if (movingGhostsNaive[i]) {
                naiveGhostMotion.push_back(speed);
            }
            if (movingGhostsGuarded[i]) {
                guardedGhostMotion.push_back(speed);
            }
        }
        const double naiveGhostMotionMin = naiveGhostMotion.empty()
                                               ? 0.0
                                               : *std::min_element(naiveGhostMotion.begin(),
                                                                   naiveGhostMotion.end());
        const double naiveGhostMotionMedian = percentile(naiveGhostMotion, 0.50);
        const double guardedGhostMotionMin = guardedGhostMotion.empty()
                                                 ? 0.0
                                                 : *std::min_element(guardedGhostMotion.begin(),
                                                                     guardedGhostMotion.end());
        writePpm((imageRoot / "moving_raw.ppm").string(), movingRun.rawFinal);
        writePpm((imageRoot / "moving_denoised.ppm").string(), movingRun.denoisedFinal);
        writePpm((imageRoot / "moving_naive_temporal.ppm").string(), movingRun.naiveFinal);
        writePpm((imageRoot / "moving_reference.ppm").string(), movingRun.referenceFinal);
        writePpm((imageRoot / "moving_mismatch_mask.ppm").string(), options.width,
                 options.height, maskImage(mismatchFinal));
        writePpm((imageRoot / "moving_fast_motion_mask.ppm").string(), options.width,
                 options.height, maskImage(fastMotion));
        writePpm((imageRoot / "moving_screen_motion.ppm").string(), options.width,
                 options.height,
                 motionImage(movingRun.guardedFinalStats.screenMotionPixels));
        writePpm((imageRoot / "moving_ghost_mask_before.ppm").string(), options.width,
                 options.height, maskImage(movingGhostsNaive));
        writePpm((imageRoot / "moving_ghost_mask_after.ppm").string(), options.width,
                 options.height, maskImage(movingGhostsGuarded));
        std::ofstream ghostCsv(outputRoot / "moving_ghost_pixels.csv");
        ghostCsv << "x,y,screen_motion_pixels,ghost_before_guard,ghost_after_guard,"
                    "fast_motion\n";
        ghostCsv << std::setprecision(8);
        for (int y = 0; y < options.height; ++y) {
            for (int x = 0; x < options.width; ++x) {
                const std::size_t pixel =
                    static_cast<std::size_t>(y) * options.width + x;
                if (!movingGhostsNaive[pixel] && !movingGhostsGuarded[pixel]) {
                    continue;
                }
                ghostCsv << x << ',' << y << ','
                         << movingRun.guardedFinalStats.screenMotionPixels[pixel] << ','
                         << static_cast<int>(movingGhostsNaive[pixel]) << ','
                         << static_cast<int>(movingGhostsGuarded[pixel]) << ','
                         << static_cast<int>(fastMotion[pixel]) << '\n';
            }
        }

        std::ofstream movingCsv(outputRoot / "moving_history.csv");
        movingCsv << "frame,history_mismatch_ratio,geometric_mismatch_ratio,"
                     "photometric_mismatch_ratio\n";
        movingCsv << std::setprecision(10);
        for (std::size_t i = 0; i < movingRun.mismatchRatio.size(); ++i) {
            movingCsv << i + 2 << ',' << movingRun.mismatchRatio[i] << ','
                      << movingRun.geometricMismatchRatio[i] << ','
                      << movingRun.photometricMismatchRatio[i] << '\n';
        }

        const auto elapsed = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - started);
        std::ofstream json(outputRoot / "metrics.json");
        json << std::fixed << std::setprecision(8);
        json << "{\n";
        json << "  \"config\": {\"width\": " << options.width
             << ", \"height\": " << options.height
             << ", \"low_spp\": " << options.samplesPerPixel
             << ", \"reference_spp\": " << options.referenceSamples
             << ", \"static_frames\": " << options.staticFrames
             << ", \"moving_frames\": " << options.movingFrames << "},\n";
        json << "  \"static\": {\n";
        json << "    \"mse_before\": " << staticRawMse << ",\n";
        json << "    \"mse_after\": " << staticDenoisedMse << ",\n";
        json << "    \"noise_variance_before\": " << staticTemporalVarianceRaw << ",\n";
        json << "    \"noise_variance_after\": " << staticTemporalVarianceDenoised << ",\n";
        json << "    \"residual_luma_variance_before\": " << staticRawLumaVariance << ",\n";
        json << "    \"residual_luma_variance_after\": " << staticDenoisedLumaVariance << ",\n";
        json << "    \"convergence_target_mse\": " << convergenceTarget << ",\n";
        json << "    \"frames_to_convergence\": " << convergenceFrame << ",\n";
        json << "    \"edge_pixel_ratio\": " << maskRatio(staticEdges) << ",\n";
        json << "    \"edge_pixel_count\": " << countMask(staticEdges) << ",\n";
        json << "    \"edge_ghost_ratio\": " << staticEdgeGhostRatio << ",\n";
        json << "    \"static_ghost_pixel_count\": " << countMask(staticGhosts) << ",\n";
        json << "    \"final_history_mismatch_ratio\": "
             << maskRatio(staticRun.finalStats.historyMismatch) << "\n";
        json << "  },\n";
        json << "  \"moving\": {\n";
        json << "    \"mse_before\": " << movingRawMse << ",\n";
        json << "    \"mse_after\": " << movingDenoisedMse << ",\n";
        json << "    \"mse_naive_temporal\": " << movingNaiveMse << ",\n";
        json << "    \"ghost_ratio_before_guard\": " << movingGhostRatioBefore << ",\n";
        json << "    \"ghost_ratio_after_guard\": " << movingGhostRatioAfter << ",\n";
        json << "    \"ghost_pixel_count_before_guard\": " << countMask(movingGhostsNaive)
             << ",\n";
        json << "    \"ghost_pixel_count_after_guard\": " << countMask(movingGhostsGuarded)
             << ",\n";
        json << "    \"history_mismatch_ratio_mean\": " << movingMismatchMean << ",\n";
        json << "    \"history_mismatch_ratio_final\": " << movingMismatchFinal << ",\n";
        json << "    \"history_mismatch_pixel_count_final\": " << countMask(mismatchFinal)
             << ",\n";
        json << "    \"geometric_mismatch_ratio_mean\": " << movingGeometricMismatchMean << ",\n";
        json << "    \"photometric_mismatch_ratio_mean\": " << movingPhotometricMismatchMean
             << ",\n";
        json << "    \"fast_motion_pixel_ratio\": " << movingFastPixelRatio << ",\n";
        json << "    \"screen_motion_p50_pixels\": " << motionP50 << ",\n";
        json << "    \"screen_motion_p75_pixels\": " << motionP75 << ",\n";
        json << "    \"screen_motion_p90_pixels\": " << motionP90 << ",\n";
        json << "    \"screen_motion_p95_pixels\": " << motionP95 << ",\n";
        json << "    \"motion_contrast_threshold_pixels\": " << motionContrastThreshold
             << ",\n";
        json << "    \"naive_ghost_motion_pixels_min\": " << naiveGhostMotionMin << ",\n";
        json << "    \"naive_ghost_motion_pixels_median\": " << naiveGhostMotionMedian
             << ",\n";
        json << "    \"guarded_ghost_motion_pixels_min\": " << guardedGhostMotionMin
             << ",\n";
        json << "    \"history_mismatch_fraction_in_fast_motion\": "
             << movingMismatchFastFraction << ",\n";
        json << "    \"naive_ghost_fraction_in_fast_motion\": "
             << movingNaiveGhostFastFraction << ",\n";
        json << "    \"guarded_ghost_fraction_in_fast_motion\": "
             << movingGuardedGhostFastFraction << ",\n";
        json << "    \"naive_ghost_pixels_outside_fast_motion\": "
             << movingNaiveGhostOutsideFast << ",\n";
        json << "    \"guarded_ghost_pixels_outside_fast_motion\": "
             << movingGuardedGhostOutsideFast << ",\n";
        json << "    \"edge_ghost_ratio_before_guard\": " << movingNaiveEdgeGhostRatio
             << ",\n";
        json << "    \"edge_ghost_ratio_after_guard\": " << movingEdgeGhostRatio << "\n";
        json << "  },\n";
        json << "  \"runtime_seconds\": " << elapsed.count() << "\n";
        json << "}\n";

        std::cout << std::fixed << std::setprecision(6);
        std::cout << "Static: raw MSE=" << staticRawMse
                  << ", denoised MSE=" << staticDenoisedMse
                  << ", temporal variance " << staticTemporalVarianceRaw << " -> "
                  << staticTemporalVarianceDenoised << '\n';
        std::cout << "Static: convergence frame=" << convergenceFrame
                  << " (1-based), edge ghost ratio=" << staticEdgeGhostRatio << '\n';
        std::cout << "Moving: history mismatch mean=" << movingMismatchMean
                  << ", ghost ratio " << movingGhostRatioBefore << " -> "
                  << movingGhostRatioAfter << '\n';
        std::cout << "Moving: naive ghosts outside fast motion="
                  << movingNaiveGhostOutsideFast
                  << ", after-guard outside fast motion="
                  << movingGuardedGhostOutsideFast << '\n';
        std::cout << "Wrote " << (outputRoot / "metrics.json") << " in "
                  << elapsed.count() << " s\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 1;
    }
}

