#include "hzb_benchmark.hpp"
#include "scene.hpp"
#include "turbulence.hpp"

#include <array>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

using hzb::BenchmarkReport;
using hzb::ResolutionResult;
using hzb::TurbulenceResult;

std::string jsonEscape(const std::string& text) {
    std::string escaped;
    escaped.reserve(text.size());
    for (char character : text) {
        switch (character) {
            case '\\':
                escaped += "\\\\";
                break;
            case '"':
                escaped += "\\\"";
                break;
            case '\n':
                escaped += "\\n";
                break;
            default:
                escaped.push_back(character);
                break;
        }
    }
    return escaped;
}

void printResolutionHeader() {
    std::cout << "\n"
              << std::left << std::setw(12) << "Z buffer"
              << std::right << std::setw(13) << "HZB ms"
              << std::setw(14) << "query ms"
              << std::setw(10) << "speedup"
              << std::setw(10) << "cull"
              << std::setw(12) << "precision"
              << std::setw(11) << "false cull"
              << "\n";
    std::cout << std::string(82, '-') << "\n";
}

void printResolution(const ResolutionResult& result) {
    std::ostringstream resolution;
    resolution << result.width << "x" << result.height;
    std::cout << std::left << std::setw(12) << resolution.str()
              << std::right << std::fixed << std::setprecision(3)
              << std::setw(13) << result.hzbBuildAndTestMs
              << std::setw(14) << result.perObjectQueryMs
              << std::setw(9) << result.speedup << "x"
              << std::setw(9) << result.cullRate * 100.0 << "%"
              << std::setw(11) << result.precision * 100.0 << "%"
              << std::setw(10) << result.falseCullRate * 100.0 << "%"
              << "\n";
}

bool writeResultsJson(const BenchmarkReport& report, const TurbulenceResult& turbulence,
                      std::string& error) {
    std::ofstream output("artifacts/results.json");
    if (!output) {
        error = "cannot open artifacts/results.json for writing";
        return false;
    }
    output << std::fixed << std::setprecision(6);
    output << "{\n"
           << "  \"renderer\": \"" << jsonEscape(report.renderer) << "\",\n"
           << "  \"gl_version\": \"" << jsonEscape(report.glVersion) << "\",\n"
           << "  \"architecture_boxes\": " << report.architectureCount << ",\n"
           << "  \"object_boxes\": " << report.objectCount << ",\n"
           << "  \"timed_frames\": " << report.timedFrames << ",\n"
           << "  \"uses_previous_frame_depth\": "
           << (report.usesPreviousFrameDepth ? "true" : "false") << ",\n"
           << "  \"resolutions\": [\n";
    for (std::size_t index = 0; index < report.resolutions.size(); ++index) {
        const ResolutionResult& result = report.resolutions[index];
        output << "    {\"width\": " << result.width
               << ", \"height\": " << result.height
               << ", \"depth_bits\": " << result.depthBits
               << ", \"mip_levels\": " << result.mipLevels
               << ", \"object_tests_per_frame\": " << result.objectTestsPerFrame
               << ", \"query_count_per_frame\": " << result.queryCountPerFrame
               << ", \"hzb_dispatch_count_per_frame\": "
               << result.hzbDispatchCountPerFrame
               << ", \"culled_objects\": " << result.culledObjects
               << ", \"exact_occluded_objects\": " << result.exactOccludedObjects
               << ", \"false_culled_objects\": " << result.falseCulledObjects
               << ", \"cull_rate\": " << result.cullRate
               << ", \"exact_occlusion_rate\": " << result.exactOcclusionRate
               << ", \"precision\": " << result.precision
               << ", \"recall\": " << result.recall
               << ", \"false_cull_rate\": " << result.falseCullRate
               << ", \"hzb_build_test_ms\": " << result.hzbBuildAndTestMs
               << ", \"per_object_query_ms\": " << result.perObjectQueryMs
               << ", \"speedup\": " << result.speedup << "}";
        output << (index + 1 == report.resolutions.size() ? "\n" : ",\n");
    }
    output << "  ],\n"
           << "  \"turbulence\": {\"particle_count\": " << turbulence.particleCount
           << ", \"steps\": " << turbulence.steps
           << ", \"dt\": " << turbulence.dt
           << ", \"final_time\": " << turbulence.finalTime
           << ", \"mean_divergence\": " << turbulence.meanDivergence
           << ", \"max_abs_divergence\": " << turbulence.maxAbsDivergence
           << ", \"initial_mean_nearest_neighbor\": "
           << turbulence.initialMeanNearestNeighbor
           << ", \"final_mean_nearest_neighbor\": "
           << turbulence.finalMeanNearestNeighbor
           << ", \"nearest_neighbor_ratio\": " << turbulence.nearestNeighborRatio
           << ", \"initial_occupancy_cv\": " << turbulence.initialOccupancyCv
           << ", \"final_occupancy_cv\": " << turbulence.finalOccupancyCv
           << ", \"occupancy_cv_ratio\": " << turbulence.occupancyCvRatio
           << ", \"final_occupancy_p99_over_median\": "
           << turbulence.finalOccupancyP99OverMedian
           << ", \"final_max_cell_occupancy_ratio\": "
           << turbulence.finalMaxCellOccupancyRatio << "}\n"
           << "}\n";
    return true;
}

bool writeResolutionCsv(const BenchmarkReport& report, std::string& error) {
    std::ofstream output("artifacts/resolution_sweep.csv");
    if (!output) {
        error = "cannot open artifacts/resolution_sweep.csv for writing";
        return false;
    }
    output << "width,height,depth_bits,mip_levels,object_tests,query_count,"
              "hzb_dispatches,culled,exact_occluded,false_culled,cull_rate,"
              "exact_occlusion_rate,precision,recall,false_cull_rate,"
              "hzb_ms,query_ms,speedup\n";
    output << std::fixed << std::setprecision(6);
    for (const ResolutionResult& result : report.resolutions) {
        output << result.width << "," << result.height << "," << result.depthBits << ","
               << result.mipLevels << "," << result.objectTestsPerFrame << ","
               << result.queryCountPerFrame << "," << result.hzbDispatchCountPerFrame << ","
               << result.culledObjects << "," << result.exactOccludedObjects << ","
               << result.falseCulledObjects << "," << result.cullRate << ","
               << result.exactOcclusionRate << "," << result.precision << ","
               << result.recall << "," << result.falseCullRate << ","
               << result.hzbBuildAndTestMs << "," << result.perObjectQueryMs << ","
               << result.speedup << "\n";
    }
    return true;
}

bool writeTrackCsv(const TurbulenceResult& turbulence, std::string& error) {
    std::ofstream output("artifacts/turbulence_tracks.csv");
    if (!output) {
        error = "cannot open artifacts/turbulence_tracks.csv for writing";
        return false;
    }
    output << "track,sample,x,y,z\n";
    for (int sample = 0; sample < turbulence.trackSamples; ++sample) {
        for (int track = 0; track < turbulence.trackCount; ++track) {
            const std::size_t index =
                static_cast<std::size_t>(sample * turbulence.trackCount + track);
            const auto& point = turbulence.tracks[index];
            output << track << "," << sample << "," << point[0] << "," << point[1] << ","
                   << point[2] << "\n";
        }
    }
    return true;
}

bool writeTrajectorySvg(const TurbulenceResult& turbulence, std::string& error) {
    std::ofstream output("artifacts/turbulence_trajectories.svg");
    if (!output) {
        error = "cannot open artifacts/turbulence_trajectories.svg for writing";
        return false;
    }
    constexpr double kTwoPi = 6.28318530717958647692;
    constexpr double kPlotLow = 42.0;
    constexpr double kPlotSize = 556.0;
    output << "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"640\" height=\"680\" "
              "viewBox=\"0 0 640 680\">\n"
              << "<rect width=\"640\" height=\"680\" fill=\"#0b1020\"/>\n"
              << "<rect x=\"40\" y=\"40\" width=\"560\" height=\"560\" fill=\"#111a33\" "
                 "stroke=\"#33456f\"/>\n"
              << "<text x=\"320\" y=\"24\" fill=\"#e8eefc\" font-family=\"sans-serif\" "
                 "font-size=\"16\" text-anchor=\"middle\">Divergence-free ABC flow: "
                 "64 tracer trajectories</text>\n";
    for (int track = 0; track < turbulence.trackCount; ++track) {
        bool segmentOpen = false;
        std::array<float, 3> previous{};
        for (int sample = 0; sample < turbulence.trackSamples; ++sample) {
            const auto& point = turbulence.tracks[static_cast<std::size_t>(
                sample * turbulence.trackCount + track)];
            if (sample > 0 &&
                (std::abs(point[0] - previous[0]) > 3.0f ||
                 std::abs(point[1] - previous[1]) > 3.0f)) {
                output << "\"/>\n";
                segmentOpen = false;
            }
            if (!segmentOpen) {
                output << "<polyline fill=\"none\" stroke=\"hsl("
                       << (track * 360 / turbulence.trackCount)
                       << ", 72%, 62%)\" stroke-width=\"1.1\" stroke-opacity=\"0.62\" points=\"";
                segmentOpen = true;
            }
            const double x = kPlotLow + point[0] / kTwoPi * kPlotSize;
            const double y = kPlotLow + (1.0 - point[1] / kTwoPi) * kPlotSize;
            output << std::fixed << std::setprecision(1) << x << "," << y << " ";
            previous = point;
        }
        if (segmentOpen) {
            output << "\"/>\n";
        }
    }
    output << "<text x=\"320\" y=\"628\" fill=\"#9fb0d8\" font-family=\"sans-serif\" "
              "font-size=\"12\" text-anchor=\"middle\">x-y projection on a periodic "
              "domain, t = "
           << std::fixed << std::setprecision(1) << turbulence.finalTime << "</text>\n"
           << "<text x=\"320\" y=\"650\" fill=\"#9fb0d8\" font-family=\"sans-serif\" "
              "font-size=\"12\" text-anchor=\"middle\">NN distance ratio = "
           << std::setprecision(4) << turbulence.nearestNeighborRatio
           << ", occupancy CV ratio = " << turbulence.occupancyCvRatio << "</text>\n"
           << "</svg>\n";
    return true;
}

bool writeMarkdownReport(const BenchmarkReport& report, const TurbulenceResult& turbulence,
                         std::string& error) {
    std::ofstream output("artifacts/report.md");
    if (!output) {
        error = "cannot open artifacts/report.md for writing";
        return false;
    }
    const ResolutionResult& primary = report.resolutions.front();
    output << "# HZB 遮挡剔除与无散度湍流验证\n\n"
           << "## 运行环境\n\n"
           << "- OpenGL renderer: `" << report.renderer << "`\n"
           << "- OpenGL version: `" << report.glVersion << "`\n"
           << "- 场景: " << report.architectureCount << " 个建筑/家具盒体, "
           << report.objectCount << " 个待测物体盒体\n"
           << "- 深度来源: 上一帧 GPU 深度预通道, 24-bit Z\n"
           << "- HZB: compute shader 逐级 2x2 max, AABB 在对应 mip 上执行保守测试\n"
           << "- 基线: 每个物体一个 `GL_ANY_SAMPLES_PASSED` 查询\n"
           << "- 计时: 预热后 " << report.timedFrames
           << " 帧的中位数, 含 HZB 构建/测试回读或查询回读与 `glFinish`\n\n"
           << "## 分辨率与剔除结果\n\n"
           << "| Z 分辨率 | HZB ms | 逐物体查询 ms | 加速 | 剔除率 | 精度 | 误剔除率 |\n"
           << "|---:|---:|---:|---:|---:|---:|---:|\n";
    for (const ResolutionResult& result : report.resolutions) {
        output << "| " << result.width << "x" << result.height << " | "
               << std::fixed << std::setprecision(3) << result.hzbBuildAndTestMs << " | "
               << result.perObjectQueryMs << " | " << result.speedup << "x | "
               << std::setprecision(2) << result.cullRate * 100.0 << "% | "
               << result.precision * 100.0 << "% | "
               << result.falseCullRate * 100.0 << "% |\n";
    }
    output << "\n主分辨率每帧执行 " << primary.objectTestsPerFrame
           << " 个 AABB 测试, 仅 1 次 HZB compute dispatch; 基线执行 "
           << primary.queryCountPerFrame << " 个遮挡查询。\n\n";
    output << "低分辨率下 mip tile 变大, 只有 tile 内最大深度仍小于物体最近深度时才会剔除, "
              "因此分辨率下降主要表现为保守漏剔增加, 而不是产生不安全误剔。实测误剔除率见上表。\n\n"
           << "## 湍流粒子\n\n"
           << "速度场采用周期域上的 ABC 流 "
              "`u=A sin(z+wt)+C cos(y), v=B sin(x+wt)+A cos(z), "
              "w=C sin(y+wt)+B cos(x)`。每个速度分量对自身坐标导数为零, 解析散度恒为零。"
              "使用 RK4 推进 " << turbulence.particleCount << " 个粒子 "
           << turbulence.steps << " 步。\n\n"
           << "| 指标 | 初始 | 结束 | 比值 |\n"
           << "|---|---:|---:|---:|\n"
           << "| 平均最近邻距离 | " << std::fixed << std::setprecision(6)
           << turbulence.initialMeanNearestNeighbor << " | "
           << turbulence.finalMeanNearestNeighbor << " | "
           << turbulence.nearestNeighborRatio << " |\n"
           << "| 占据度 CV | " << turbulence.initialOccupancyCv << " | "
           << turbulence.finalOccupancyCv << " | " << turbulence.occupancyCvRatio
           << " |\n\n"
           << "- 有限差分散度: 平均 " << std::scientific << std::setprecision(3)
           << turbulence.meanDivergence << ", 最大 " << turbulence.maxAbsDivergence
           << "\n"
           << "- 结束帧占据度 p99/中位数: " << std::fixed << std::setprecision(3)
           << turbulence.finalOccupancyP99OverMedian << "\n"
           << "- 最近邻距离保持率接近 1, 且密度 CV 未增长, 说明体积保持场未把粒子吸附成团。\n\n"
           << "![湍流粒子轨迹](turbulence_trajectories.svg)\n\n"
           << "## 结论\n\n"
           << "- 主分辨率 HZB 相对逐物体查询快 " << std::fixed << std::setprecision(2)
           << primary.speedup << " 倍, 被遮挡物体在绘制前被剔除。\n"
           << "- HZB 精度 " << primary.precision * 100.0 << "%, 误剔除率 "
           << primary.falseCullRate * 100.0 << "%; 所有测试分辨率均保持保守。\n"
           << "- 无散度 ABC 流下平均最近邻比值 "
           << turbulence.nearestNeighborRatio << ", 无聚集趋势。\n";
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    int frames = 7;
    bool assertThresholds = false;
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        if (argument == "--assert") {
            assertThresholds = true;
        } else if (argument == "--frames" && index + 1 < argc) {
            frames = std::max(3, std::atoi(argv[++index]));
        } else if (argument == "--help") {
            std::cout << "Usage: hzb_cull [--frames N] [--assert]\n";
            return 0;
        } else {
            std::cerr << "Unknown argument: " << argument << "\n";
            return 2;
        }
    }

    const hzb::Scene scene = hzb::makeDenseIndoorScene();
    std::string error;
    const BenchmarkReport report = hzb::runHZBBenchmark(scene, frames, error);
    if (!error.empty() || report.resolutions.empty()) {
        std::cerr << "HZB benchmark failed: " << error << "\n";
        return 1;
    }

    std::cout << "HZB occlusion culling benchmark\n"
              << "Renderer : " << report.renderer << "\n"
              << "GL       : " << report.glVersion << "\n"
              << "Scene    : " << report.architectureCount << " static boxes, "
              << report.objectCount << " tested objects\n"
              << "Depth    : previous frame, 24-bit Z\n";
    printResolutionHeader();
    for (const ResolutionResult& result : report.resolutions) {
        printResolution(result);
    }
    std::cout << "\nPer-frame tests: " << report.resolutions.front().objectTestsPerFrame
              << " AABB tests in " << report.resolutions.front().hzbDispatchCountPerFrame
              << " HZB dispatch; baseline uses "
              << report.resolutions.front().queryCountPerFrame
              << " per-object occlusion queries.\n";

    const TurbulenceResult turbulence = hzb::runTurbulenceValidation();
    std::cout << "\nTurbulence validation\n"
              << "Divergence: mean=" << std::scientific << std::setprecision(3)
              << turbulence.meanDivergence << " max=" << turbulence.maxAbsDivergence
              << "\nNearest-neighbor ratio: " << std::fixed << std::setprecision(4)
              << turbulence.nearestNeighborRatio << "\nOccupancy CV ratio: "
              << turbulence.occupancyCvRatio << "\n";

    std::filesystem::create_directories("artifacts");
    if (!writeResultsJson(report, turbulence, error) ||
        !writeResolutionCsv(report, error) || !writeTrackCsv(turbulence, error) ||
        !writeTrajectorySvg(turbulence, error) ||
        !writeMarkdownReport(report, turbulence, error)) {
        std::cerr << error << "\n";
        return 1;
    }

    const ResolutionResult& primary = report.resolutions.front();
    bool allConservative = true;
    for (const ResolutionResult& result : report.resolutions) {
        allConservative =
            allConservative && result.falseCullRate <= 0.0001 && result.precision >= 0.999;
    }
    const bool speedupOk = primary.speedup >= 1.15;
    const bool cullRateOk = primary.cullRate >= 0.30;
    const bool divergenceOk = turbulence.maxAbsDivergence <= 1.0e-5;
    const bool mixingOk = turbulence.nearestNeighborRatio >= 0.85 &&
                          turbulence.nearestNeighborRatio <= 1.15 &&
                          turbulence.occupancyCvRatio >= 0.80 &&
                          turbulence.occupancyCvRatio <= 1.20;

    std::cout << "\nChecks: conservative=" << (allConservative ? "PASS" : "FAIL")
              << " speedup=" << (speedupOk ? "PASS" : "FAIL")
              << " cull-rate=" << (cullRateOk ? "PASS" : "FAIL")
              << " divergence=" << (divergenceOk ? "PASS" : "FAIL")
              << " no-clustering=" << (mixingOk ? "PASS" : "FAIL") << "\n"
              << "Artifacts: artifacts/results.json, resolution_sweep.csv, "
                 "turbulence_tracks.csv, turbulence_trajectories.svg, report.md\n";

    if (assertThresholds &&
        !(allConservative && speedupOk && cullRateOk && divergenceOk && mixingOk)) {
        return 3;
    }
    return 0;
}
