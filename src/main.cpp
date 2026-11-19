#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "ibl/env_map.h"
#include "ibl/io.h"
#include "ibl/render.h"
#include "ibl/sampler.h"

namespace {

using ibl::EnvMap;
using ibl::EnvSample;
using ibl::EnvSampler;
using ibl::MipPolicy;
using ibl::RenderOptions;
using ibl::RenderResult;
using ibl::Renderer;
using ibl::Rng;
using ibl::SamplingMethod;
using ibl::Vec3;

constexpr double kFourPi = 4.0 * ibl::kPi;

struct Options {
  std::string output = "outputs";
  int env_width = 128;
  int env_height = 64;
  int width = 160;
  int height = 160;
  int spp = 16;
  int frames = 12;
  std::size_t direction_samples = 1000000;
  double roughness = 0.32;
  double highlight_margin_deg = 1.5;
  std::uint64_t seed = 20261120;
};

struct RegionDensity {
  std::string name;
  double solid_angle = 0.0;
  double energy_fraction = 0.0;
  std::size_t importance_samples = 0;
  double importance_fraction = 0.0;
  double uniform_expected = 0.0;
  double importance_density = 0.0;
  double uniform_density = 0.0;
  double density_ratio = 0.0;
};

struct DirectionAnalysis {
  int hist_width = 96;
  int hist_height = 48;
  std::vector<std::size_t> uniform_hist;
  std::vector<std::size_t> importance_hist;
  std::vector<double> cell_solid_angle;
  std::size_t total = 0;
  double highlight_solid_angle = 0.0;
  double highlight_solid_angle_fraction = 0.0;
  std::size_t uniform_highlight_samples = 0;
  std::size_t importance_highlight_samples = 0;
  double uniform_highlight_fraction = 0.0;
  double importance_highlight_fraction = 0.0;
  double uniform_density = 0.0;
  double importance_density = 0.0;
  double density_ratio = 0.0;
  std::vector<RegionDensity> regions;
};

struct NoiseAnalysis {
  SamplingMethod method = SamplingMethod::Uniform;
  MipPolicy policy = MipPolicy::LobeFootprint;
  RenderResult first_frame;
  std::vector<Vec3> mean_image;
  std::vector<double> variance;
  std::vector<double> stddev;
  std::vector<double> valid_sum;
  std::vector<double> lod_sum;
  int spp = 0;
  int frame_count = 0;
  int sphere_pixels = 0;
  int highlight_pixels = 0;
  double mean_valid_fraction = 0.0;
  double mean_lod = 0.0;
  double mean_variance = 0.0;
  double mean_std = 0.0;
  double highlight_mean_variance = 0.0;
  double highlight_mean_std = 0.0;
  double highlight_relative_noise = 0.0;
  double p95_std = 0.0;
  double max_std = 0.0;
  double relative_noise = 0.0;
  double rmse_reference = 0.0;
};

struct MipRow {
  MipPolicy policy = MipPolicy::Base;
  double mean_lod = 0.0;
  double mean_variance = 0.0;
  double mean_std = 0.0;
  double relative_noise = 0.0;
  double p95_std = 0.0;
  double rmse_reference = 0.0;
};

std::vector<Vec3> envPixels(const EnvMap& env) {
  std::vector<Vec3> pixels;
  pixels.reserve(static_cast<std::size_t>(env.width() * env.height()));
  for (int row = 0; row < env.height(); ++row) {
    for (int col = 0; col < env.width(); ++col) {
      pixels.push_back(env.texel(row, col));
    }
  }
  return pixels;
}

double regionEnergyFraction(const EnvMap& env, int highlight_index,
                            double margin_deg) {
  double regionEnergy = 0.0;
  for (int row = 0; row < env.height(); ++row) {
    const double omega = env.texelSolidAngle(row);
    for (int col = 0; col < env.width(); ++col) {
      const Vec3 dir = env.directionFromUv((col + 0.5) / env.width(),
                                           (row + 0.5) / env.height());
      if (env.isNearHighlight(dir, highlight_index, margin_deg)) {
        regionEnergy += env.luminanceAt(row, col) * omega;
      }
    }
  }
  return regionEnergy / std::max(env.totalEnergy(), 1e-12);
}

DirectionAnalysis analyzeDirections(const EnvMap& env, const EnvSampler& sampler,
                                    std::size_t sample_count, int hist_width,
                                    int hist_height, double margin_deg,
                                    std::uint64_t seed) {
  DirectionAnalysis result;
  result.hist_width = hist_width;
  result.hist_height = hist_height;
  result.total = sample_count;
  const std::size_t cells =
      static_cast<std::size_t>(hist_width * hist_height);
  result.uniform_hist.assign(cells, 0);
  result.importance_hist.assign(cells, 0);
  result.cell_solid_angle.assign(cells, 0.0);
  const auto& highlights = env.highlights();
  for (std::size_t i = 0; i < highlights.size(); ++i) {
    RegionDensity region;
    region.name = highlights[i].name;
    region.solid_angle =
        env.highlightSolidAngle(static_cast<int>(i), margin_deg);
    region.energy_fraction =
        regionEnergyFraction(env, static_cast<int>(i), margin_deg);
    result.regions.push_back(region);
  }
  for (int row = 0; row < hist_height; ++row) {
    const double dPhi = 2.0 * ibl::kPi / hist_width;
    const double dTheta = ibl::kPi / hist_height;
    const double omega = dPhi * dTheta *
                         std::sin((row + 0.5) / hist_height * ibl::kPi);
    for (int col = 0; col < hist_width; ++col) {
      result.cell_solid_angle[static_cast<std::size_t>(row * hist_width + col)] =
          omega;
    }
  }

  Rng rng(seed);
  for (std::size_t i = 0; i < sample_count; ++i) {
    const Vec3 dir = rng.uniformSphere();
    if (env.isNearHighlight(dir, margin_deg)) {
      ++result.uniform_highlight_samples;
    }
    double u = 0.0;
    double v = 0.0;
    env.uvFromDirection(dir, u, v);
    const int col =
        std::clamp(static_cast<int>(u * hist_width), 0, hist_width - 1);
    const int row =
        std::clamp(static_cast<int>(v * hist_height), 0, hist_height - 1);
    ++result.uniform_hist[static_cast<std::size_t>(row * hist_width + col)];
  }

  Rng importanceRng(seed ^ 0x7f4a7c159e3779b9ULL);
  for (std::size_t i = 0; i < sample_count; ++i) {
    const EnvSample sample =
        sampler.sample(importanceRng.uniform(), importanceRng.uniform());
    if (env.isNearHighlight(sample.direction, margin_deg)) {
      ++result.importance_highlight_samples;
    }
    for (std::size_t regionIndex = 0; regionIndex < highlights.size();
         ++regionIndex) {
      if (env.isNearHighlight(sample.direction, static_cast<int>(regionIndex),
                              margin_deg)) {
        ++result.regions[regionIndex].importance_samples;
      }
    }
    const int col =
        std::clamp(static_cast<int>(sample.u * hist_width), 0, hist_width - 1);
    const int row =
        std::clamp(static_cast<int>(sample.v * hist_height), 0,
                   hist_height - 1);
    ++result.importance_hist[static_cast<std::size_t>(row * hist_width + col)];
  }

  result.highlight_solid_angle = env.highlightSolidAngle(margin_deg);
  result.highlight_solid_angle_fraction =
      result.highlight_solid_angle / kFourPi;
  result.uniform_highlight_fraction =
      static_cast<double>(result.uniform_highlight_samples) / sample_count;
  result.importance_highlight_fraction =
      static_cast<double>(result.importance_highlight_samples) / sample_count;
  result.uniform_density = result.uniform_highlight_samples /
                           std::max(result.highlight_solid_angle, 1e-12);
  result.importance_density = result.importance_highlight_samples /
                              std::max(result.highlight_solid_angle, 1e-12);
  result.density_ratio =
      result.importance_density / std::max(result.uniform_density, 1e-12);

  for (RegionDensity& region : result.regions) {
    region.importance_fraction =
        static_cast<double>(region.importance_samples) / sample_count;
    region.uniform_expected =
        static_cast<double>(sample_count) * region.solid_angle / kFourPi;
    region.importance_density =
        region.importance_samples / std::max(region.solid_angle, 1e-12);
    region.uniform_density =
        static_cast<double>(sample_count) / kFourPi;
    region.density_ratio =
        region.importance_density / std::max(region.uniform_density, 1e-12);
  }
  return result;
}

bool reflectionNearHighlight(const EnvMap& env, const RenderOptions& options,
                             int x, int y, double margin_deg) {
  Vec3 normal;
  if (!Renderer::isSpherePixel(x, y, options.width, options.height,
                               options.sphere_radius, normal)) {
    return false;
  }
  const Vec3 view{0.0, 0.0, 1.0};
  const Vec3 reflection = ibl::reflect(-view, normal);
  return env.isNearHighlight(reflection, margin_deg);
}

double computeRmse(const std::vector<Vec3>& image,
                   const std::vector<Vec3>& reference,
                   const std::vector<std::uint8_t>& mask) {
  double squaredError = 0.0;
  std::size_t count = 0;
  for (std::size_t i = 0; i < image.size(); ++i) {
    if (!mask[i]) {
      continue;
    }
    const Vec3 diff = image[i] - reference[i];
    squaredError += diff.x * diff.x + diff.y * diff.y + diff.z * diff.z;
    count += 3;
  }
  return std::sqrt(squaredError / std::max<std::size_t>(count, 1));
}

NoiseAnalysis runNoiseAnalysis(const EnvMap& env, const Renderer& renderer,
                               const RenderOptions& baseOptions,
                               SamplingMethod method, MipPolicy policy,
                               const RenderResult& reference,
                               double margin_deg, int frame_count,
                               std::uint64_t seed) {
  NoiseAnalysis analysis;
  analysis.method = method;
  analysis.policy = policy;
  analysis.spp = baseOptions.spp;
  analysis.frame_count = frame_count;
  if (frame_count < 2) {
    throw std::invalid_argument("variance analysis needs at least 2 frames");
  }
  RenderOptions options = baseOptions;
  options.mip_policy = policy;
  const std::size_t count =
      static_cast<std::size_t>(options.width * options.height);
  analysis.mean_image.assign(count, Vec3{});
  analysis.variance.assign(count, 0.0);
  analysis.stddev.assign(count, 0.0);
  analysis.valid_sum.assign(count, 0.0);
  analysis.lod_sum.assign(count, 0.0);
  std::vector<double> m2(count, 0.0);
  std::vector<double> mean_luminance(count, 0.0);
  std::vector<std::uint8_t> highlight_mask(count, 0);

  for (int y = 0; y < options.height; ++y) {
    for (int x = 0; x < options.width; ++x) {
      const std::size_t index =
          static_cast<std::size_t>(y * options.width + x);
      highlight_mask[index] =
          reflectionNearHighlight(env, options, x, y, margin_deg) ? 1 : 0;
      if (highlight_mask[index]) {
        ++analysis.highlight_pixels;
      }
    }
  }

  for (int frame = 0; frame < frame_count; ++frame) {
    const std::uint64_t frameSeed =
        seed ^ (0x94d049bb133111ebULL * static_cast<std::uint64_t>(frame + 1)) ^
        (method == SamplingMethod::Importance ? 0xabcdef1234567890ULL : 0ULL) ^
        static_cast<std::uint64_t>(policy) * 0x9e3779b97f4a7c15ULL;
    const RenderResult image = renderer.render(method, options, frameSeed);
    if (frame == 0) {
      analysis.first_frame = image;
    }
    const double frameWeight = 1.0 / static_cast<double>(frame + 1);
    for (std::size_t i = 0; i < count; ++i) {
      if (!image.sphere_mask[i]) {
        continue;
      }
      analysis.mean_image[i] += (image.pixels[i] - analysis.mean_image[i]) *
                                frameWeight;
      const double lum = ibl::luminance(image.pixels[i]);
      const double delta = lum - mean_luminance[i];
      mean_luminance[i] += delta * frameWeight;
      m2[i] += delta * (lum - mean_luminance[i]);
      analysis.valid_sum[i] +=
          static_cast<double>(image.valid_samples[i]);
      analysis.lod_sum[i] += image.mean_lod[i];
    }
  }

  double stdSum = 0.0;
  double varianceSum = 0.0;
  double highlightStdSum = 0.0;
  double highlightVarianceSum = 0.0;
  double meanLumSum = 0.0;
  double highlightMeanLumSum = 0.0;
  double validSum = 0.0;
  double lodSum = 0.0;
  std::vector<double> allStd;
  allStd.reserve(static_cast<std::size_t>(options.width * options.height));
  for (std::size_t i = 0; i < count; ++i) {
    if (!analysis.first_frame.sphere_mask[i]) {
      continue;
    }
    ++analysis.sphere_pixels;
    analysis.variance[i] = m2[i] / static_cast<double>(frame_count - 1);
    analysis.stddev[i] = std::sqrt(std::max(0.0, analysis.variance[i]));
    const double meanLum = ibl::luminance(analysis.mean_image[i]);
    stdSum += analysis.stddev[i];
    varianceSum += analysis.variance[i];
    meanLumSum += meanLum;
    validSum += analysis.valid_sum[i];
    lodSum += analysis.lod_sum[i] / frame_count;
    if (highlight_mask[i]) {
      highlightStdSum += analysis.stddev[i];
      highlightVarianceSum += analysis.variance[i];
      highlightMeanLumSum += meanLum;
    }
    allStd.push_back(analysis.stddev[i]);
  }

  const double pixelCount = std::max(analysis.sphere_pixels, 1);
  analysis.mean_std = stdSum / pixelCount;
  analysis.mean_variance = varianceSum / pixelCount;
  analysis.mean_lod = lodSum / pixelCount;
  analysis.relative_noise = analysis.mean_std / std::max(meanLumSum / pixelCount,
                                                          1e-12);
  analysis.highlight_mean_std =
      highlightStdSum / std::max(analysis.highlight_pixels, 1);
  analysis.highlight_mean_variance =
      highlightVarianceSum / std::max(analysis.highlight_pixels, 1);
  analysis.highlight_relative_noise =
      analysis.highlight_mean_std /
      std::max(highlightMeanLumSum / std::max(analysis.highlight_pixels, 1),
               1e-12);
  analysis.mean_valid_fraction =
      validSum /
      std::max(1.0, static_cast<double>(options.spp * frame_count *
                                        analysis.sphere_pixels));
  analysis.rmse_reference =
      computeRmse(analysis.mean_image, reference.pixels,
                  analysis.first_frame.sphere_mask);
  if (!allStd.empty()) {
    const std::size_t p95Index =
        std::min(allStd.size() - 1,
                 static_cast<std::size_t>(0.95 * (allStd.size() - 1)));
    std::nth_element(allStd.begin(), allStd.begin() + p95Index, allStd.end());
    analysis.p95_std = allStd[p95Index];
    analysis.max_std = *std::max_element(allStd.begin(), allStd.end());
  }

  return analysis;
}

void writeEnvCsv(const std::string& path, const EnvMap& env) {
  std::ofstream out(path);
  out << "row,col,u,v,luminance,r,g,b\n" << std::setprecision(10);
  for (int row = 0; row < env.height(); ++row) {
    for (int col = 0; col < env.width(); ++col) {
      const Vec3 value = env.texel(row, col);
      out << row << ',' << col << ',' << (col + 0.5) / env.width() << ','
          << (row + 0.5) / env.height() << ',' << ibl::luminance(value) << ','
          << value.x << ',' << value.y << ',' << value.z << '\n';
    }
  }
}

void writeDirectionHistogramCsv(const std::string& path,
                                const EnvMap& env,
                                const DirectionAnalysis& analysis,
                                double margin_deg) {
  std::ofstream out(path);
  out << "u,v,count_uniform,count_importance,density_uniform,"
         "density_importance,relative_density,highlight\n"
      << std::setprecision(10);
  const double uniformDensity = analysis.total / kFourPi;
  for (int row = 0; row < analysis.hist_height; ++row) {
    for (int col = 0; col < analysis.hist_width; ++col) {
      const std::size_t index =
          static_cast<std::size_t>(row * analysis.hist_width + col);
      const double u = (col + 0.5) / analysis.hist_width;
      const double v = (row + 0.5) / analysis.hist_height;
      const Vec3 dir = env.directionFromUv(u, v);
      const double omega = analysis.cell_solid_angle[index];
      const double uniformDensityCell =
          analysis.uniform_hist[index] / omega;
      const double importanceDensityCell =
          analysis.importance_hist[index] / omega;
      out << u << ',' << v << ',' << analysis.uniform_hist[index] << ','
          << analysis.importance_hist[index] << ',' << uniformDensityCell << ','
          << importanceDensityCell << ','
          << importanceDensityCell / std::max(uniformDensity, 1e-12) << ','
          << (env.isNearHighlight(dir, margin_deg) ? 1 : 0) << '\n';
    }
  }
}

void writeHighlightDensityCsv(const std::string& path,
                              const EnvMap& env,
                              const DirectionAnalysis& analysis,
                              double margin_deg) {
  std::ofstream out(path);
  out << "region,solid_angle,energy_fraction,importance_samples,"
         "importance_fraction,uniform_expected,density_importance,"
         "density_uniform,density_ratio,oversampled\n"
      << std::setprecision(10);
  for (const RegionDensity& region : analysis.regions) {
    out << region.name << ',' << region.solid_angle << ','
        << region.energy_fraction << ',' << region.importance_samples << ','
        << region.importance_fraction << ',' << region.uniform_expected << ','
        << region.importance_density << ',' << region.uniform_density << ','
        << region.density_ratio << ','
        << (region.density_ratio > 1.0 ? "true" : "false") << '\n';
  }
  const double combinedEnergyFraction =
      std::accumulate(analysis.regions.begin(), analysis.regions.end(), 0.0,
                      [](double sum, const RegionDensity& region) {
                        return sum + region.energy_fraction;
                      });
  out << "combined," << analysis.highlight_solid_angle << ','
      << combinedEnergyFraction << ','
      << analysis.importance_highlight_samples << ','
      << analysis.importance_highlight_fraction << ','
      << analysis.uniform_highlight_fraction * analysis.total << ','
      << analysis.importance_density << ',' << analysis.uniform_density << ','
      << analysis.density_ratio << ','
      << (analysis.density_ratio > 1.0 ? "true" : "false") << '\n';
  (void)env;
  (void)margin_deg;
}

void writeSamplesPerPixelCsv(const std::string& path,
                             const NoiseAnalysis& importance,
                             const NoiseAnalysis& uniform,
                             const EnvMap& env, const RenderOptions& options,
                             int frame_count, double margin_deg) {
  std::ofstream out(path);
  out << "x,y,is_sphere,reflection_highlight,attempted_spp,"
         "importance_valid_spp,importance_valid_fraction,"
         "uniform_valid_spp,uniform_valid_fraction,mean_mip_lod\n"
      << std::setprecision(10);
  const int attempted = options.spp * frame_count;
  for (int y = 0; y < options.height; ++y) {
    for (int x = 0; x < options.width; ++x) {
      const std::size_t index =
          static_cast<std::size_t>(y * options.width + x);
      const bool sphere = importance.first_frame.sphere_mask[index] != 0;
      out << x << ',' << y << ',' << (sphere ? 1 : 0) << ','
          << (reflectionNearHighlight(env, options, x, y, margin_deg) ? 1 : 0)
          << ',' << attempted << ',';
      if (sphere) {
        out << static_cast<int>(std::llround(importance.valid_sum[index]))
            << ',' << importance.valid_sum[index] / attempted << ','
            << static_cast<int>(std::llround(uniform.valid_sum[index])) << ','
            << uniform.valid_sum[index] / attempted << ','
            << importance.lod_sum[index] / frame_count;
      } else {
        out << "0,0,0,0,0";
      }
      out << '\n';
    }
  }
}

void writeNoiseByPixelCsv(const std::string& path, const EnvMap& env,
                          const NoiseAnalysis& uniform,
                          const NoiseAnalysis& importance,
                          const RenderOptions& options, double margin_deg) {
  std::ofstream out(path);
  out << "x,y,is_sphere,reflection_highlight,importance_mean_luminance,"
         "importance_variance,importance_std,uniform_mean_luminance,"
         "uniform_variance,uniform_std\n"
      << std::setprecision(10);
  for (int y = 0; y < options.height; ++y) {
    for (int x = 0; x < options.width; ++x) {
      const std::size_t index =
          static_cast<std::size_t>(y * options.width + x);
      const bool sphere = importance.first_frame.sphere_mask[index] != 0;
      out << x << ',' << y << ',' << (sphere ? 1 : 0) << ','
          << (reflectionNearHighlight(env, options, x, y, margin_deg) ? 1 : 0)
          << ',' << ibl::luminance(importance.mean_image[index]) << ','
          << importance.variance[index] << ',' << importance.stddev[index]
          << ','
          << ibl::luminance(uniform.mean_image[index]) << ','
          << uniform.variance[index] << ',' << uniform.stddev[index] << '\n';
    }
  }
}

void writeMipVarianceCsv(const std::string& path,
                         const std::vector<MipRow>& rows) {
  std::ofstream out(path);
  out << "policy,mean_mip_lod,mean_pixel_variance,mean_pixel_std,"
         "relative_noise,p95_pixel_std,rmse_vs_mip0_reference\n"
      << std::setprecision(10);
  for (const MipRow& row : rows) {
    out << ibl::mipPolicyName(row.policy) << ',' << row.mean_lod << ','
        << row.mean_variance << ',' << row.mean_std << ',' << row.relative_noise
        << ',' << row.p95_std << ',' << row.rmse_reference << '\n';
  }
}

void writeMethodJson(std::ostream& out, const NoiseAnalysis& analysis) {
  out << "{\n"
      << "      \"mean_pixel_variance\": " << analysis.mean_variance << ",\n"
      << "      \"mean_pixel_std\": " << analysis.mean_std << ",\n"
      << "      \"highlight_mean_pixel_variance\": "
      << analysis.highlight_mean_variance << ",\n"
      << "      \"highlight_mean_pixel_std\": "
      << analysis.highlight_mean_std << ",\n"
      << "      \"relative_noise\": " << analysis.relative_noise << ",\n"
      << "      \"highlight_relative_noise\": "
      << analysis.highlight_relative_noise << ",\n"
      << "      \"p95_pixel_std\": " << analysis.p95_std << ",\n"
      << "      \"max_pixel_std\": " << analysis.max_std << ",\n"
      << "      \"rmse_vs_mip0_reference\": " << analysis.rmse_reference
      << ",\n"
      << "      \"mean_valid_spp_fraction\": "
      << analysis.mean_valid_fraction << ",\n"
      << "      \"mean_mip_lod\": " << analysis.mean_lod << ",\n"
      << "      \"configured_spp\": " << analysis.spp << ",\n"
      << "      \"frames\": " << analysis.frame_count << ",\n"
      << "      \"highlight_pixels\": " << analysis.highlight_pixels << '\n'
      << "    }";
}

void writeMetricsJson(const std::string& path, const EnvMap& env,
                      const Options& options, double margin_deg,
                      const DirectionAnalysis& directions,
                      const NoiseAnalysis& uniform,
                      const NoiseAnalysis& importance,
                      const std::vector<MipRow>& mipRows) {
  const double combinedEnergyFraction =
      std::accumulate(directions.regions.begin(), directions.regions.end(), 0.0,
                      [](double sum, const RegionDensity& region) {
                        return sum + region.energy_fraction;
                      });
  const double noiseReduction =
      uniform.mean_std / std::max(importance.mean_std, 1e-12);
  const bool allRegionsOversampled =
      std::all_of(directions.regions.begin(), directions.regions.end(),
                  [](const RegionDensity& region) {
                    return region.density_ratio > 1.0 &&
                           region.importance_samples > 0;
                  });

  std::ofstream out(path);
  out << std::setprecision(10) << std::fixed;
  out << "{\n"
      << "  \"environment\": {\n"
      << "    \"width\": " << env.width() << ",\n"
      << "    \"height\": " << env.height() << ",\n"
      << "    \"mip_levels\": " << env.mipCount() << ",\n"
      << "    \"max_luminance\": " << env.maxLuminance() << ",\n"
      << "    \"mean_luminance\": " << env.meanLuminance() << ",\n"
      << "    \"dynamic_range_99pct\": " << env.dynamicRange() << ",\n"
      << "    \"highlight_solid_angle_fraction\": "
      << directions.highlight_solid_angle_fraction << ",\n"
      << "    \"highlight_energy_fraction\": " << combinedEnergyFraction
      << "\n"
      << "  },\n"
      << "  \"direction_sampling\": {\n"
      << "    \"samples_per_method\": " << directions.total << ",\n"
      << "    \"highlight_margin_deg\": " << margin_deg << ",\n"
      << "    \"uniform_highlight_fraction\": "
      << directions.uniform_highlight_fraction << ",\n"
      << "    \"importance_highlight_fraction\": "
      << directions.importance_highlight_fraction << ",\n"
      << "    \"uniform_density_per_sr\": " << directions.uniform_density
      << ",\n"
      << "    \"importance_density_per_sr\": "
      << directions.importance_density << ",\n"
      << "    \"density_ratio\": " << directions.density_ratio << ",\n"
      << "    \"highlight_oversampled\": "
      << (directions.density_ratio > 1.0 ? "true" : "false") << ",\n"
      << "    \"all_regions_oversampled\": "
      << (allRegionsOversampled ? "true" : "false") << ",\n"
      << "    \"avoid_highlight_undersampling\": "
      << (directions.density_ratio > 1.0 && allRegionsOversampled ? "true"
                                                                  : "false")
      << ",\n"
      << "    \"regions\": [\n";
  for (std::size_t i = 0; i < directions.regions.size(); ++i) {
    const RegionDensity& region = directions.regions[i];
    out << "      {\"name\": \"" << region.name << "\", "
        << "\"solid_angle\": " << region.solid_angle << ", "
        << "\"energy_fraction\": " << region.energy_fraction << ", "
        << "\"importance_samples\": " << region.importance_samples << ", "
        << "\"importance_fraction\": " << region.importance_fraction << ", "
        << "\"uniform_expected_samples\": " << region.uniform_expected << ", "
        << "\"importance_density_per_sr\": " << region.importance_density
        << ", "
        << "\"uniform_density_per_sr\": " << region.uniform_density << ", "
        << "\"density_ratio\": " << region.density_ratio << "}"
        << (i + 1 == directions.regions.size() ? "\n" : ",\n");
  }
  out << "    ]\n"
      << "  },\n"
      << "  \"render\": {\n"
      << "    \"width\": " << options.width << ",\n"
      << "    \"height\": " << options.height << ",\n"
      << "    \"sphere_pixels\": " << importance.sphere_pixels << ",\n"
      << "    \"spp_per_frame\": " << options.spp << ",\n"
      << "    \"frames_for_variance\": " << options.frames << ",\n"
      << "    \"total_attempts_per_pixel\": " << options.spp * options.frames
      << ",\n"
      << "    \"roughness\": " << options.roughness << ",\n"
      << "    \"reference\": \"mip0_direct_texel_quadrature\",\n"
      << "    \"noise_reduction_uniform_to_importance\": " << noiseReduction
      << ",\n"
      << "    \"methods\": {\n"
      << "      \"uniform\": ";
  writeMethodJson(out, uniform);
  out << ",\n      \"importance\": ";
  writeMethodJson(out, importance);
  out << "\n    }\n"
      << "  },\n"
      << "  \"mip_policies\": [\n";
  for (std::size_t i = 0; i < mipRows.size(); ++i) {
    const MipRow& row = mipRows[i];
    out << "    {\"policy\": \"" << ibl::mipPolicyName(row.policy)
        << "\", \"mean_mip_lod\": " << row.mean_lod
        << ", \"mean_pixel_variance\": " << row.mean_variance
        << ", \"mean_pixel_std\": " << row.mean_std
        << ", \"relative_noise\": " << row.relative_noise
        << ", \"p95_pixel_std\": " << row.p95_std
        << ", \"rmse_vs_mip0_reference\": " << row.rmse_reference << "}"
        << (i + 1 == mipRows.size() ? "\n" : ",\n");
  }
  out << "  ]\n"
      << "}\n";
}

Options parseOptions(int argc, char** argv) {
  Options options;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    auto value = [&](const char* name) -> std::string {
      if (i + 1 >= argc) {
        throw std::invalid_argument(std::string("missing value for ") + name);
      }
      return argv[++i];
    };
    if (arg == "--output") {
      options.output = value("--output");
    } else if (arg == "--env-width") {
      options.env_width = std::stoi(value("--env-width"));
    } else if (arg == "--env-height") {
      options.env_height = std::stoi(value("--env-height"));
    } else if (arg == "--width") {
      options.width = std::stoi(value("--width"));
    } else if (arg == "--height") {
      options.height = std::stoi(value("--height"));
    } else if (arg == "--spp") {
      options.spp = std::stoi(value("--spp"));
    } else if (arg == "--frames") {
      options.frames = std::stoi(value("--frames"));
    } else if (arg == "--directions") {
      options.direction_samples = std::stoull(value("--directions"));
    } else if (arg == "--roughness") {
      options.roughness = std::stod(value("--roughness"));
    } else if (arg == "--highlight-margin") {
      options.highlight_margin_deg = std::stod(value("--highlight-margin"));
    } else if (arg == "--seed") {
      options.seed = std::stoull(value("--seed"));
    } else if (arg == "--help" || arg == "-h") {
      std::cout
          << "Usage: ibl_demo [options]\n"
          << "  --output DIR            Output directory (default outputs)\n"
          << "  --env-width N           HDR environment width (128)\n"
          << "  --env-height N          HDR environment height (64)\n"
          << "  --width N               Render width (160)\n"
          << "  --height N              Render height (160)\n"
          << "  --spp N                 Samples per pixel per frame (16)\n"
          << "  --frames N              Independent frames for variance (12)\n"
          << "  --directions N          Directions per sampling method (1e6)\n"
          << "  --roughness R           GGX roughness (0.32)\n"
          << "  --highlight-margin DEG  Highlight neighborhood margin (1.5)\n"
          << "  --seed N                Deterministic seed (20261120)\n";
      std::exit(0);
    } else {
      throw std::invalid_argument("unknown option: " + arg);
    }
  }
  if (options.env_width < 16 || options.env_height < 8 ||
      options.width < 32 || options.height < 32 || options.spp < 1 ||
      options.frames < 2 || options.direction_samples < 1000 ||
      options.roughness <= 0.0 || options.roughness >= 1.0) {
    throw std::invalid_argument("one or more numeric options are out of range");
  }
  return options;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parseOptions(argc, argv);
    ibl::ensureDirectory(options.output);
    std::cout << "Building synthetic HDR environment map "
              << options.env_width << "x" << options.env_height << "...\n";
    const EnvMap env =
        EnvMap::makeSyntheticHdr(options.env_width, options.env_height);
    const EnvSampler sampler(env);
    const Renderer renderer(env);

    ibl::writePpm(options.output + "/env_map.ppm", env.width(), env.height(),
                  envPixels(env), 1.2);
    ibl::writeLinearF32(options.output + "/env_map_linear.f32", env.width(),
                        env.height(), envPixels(env));
    writeEnvCsv(options.output + "/env_map.csv", env);
    std::cout << "HDR max luminance=" << env.maxLuminance()
              << ", dynamic range=" << env.dynamicRange()
              << ", mips=" << env.mipCount() << "\n";

    std::cout << "Sampling " << options.direction_samples
              << " directions per method...\n";
    const DirectionAnalysis directions = analyzeDirections(
        env, sampler, options.direction_samples, 96, 48,
        options.highlight_margin_deg, options.seed);
    writeDirectionHistogramCsv(options.output + "/direction_histogram.csv", env,
                               directions, options.highlight_margin_deg);
    writeHighlightDensityCsv(options.output + "/highlight_density.csv", env,
                             directions, options.highlight_margin_deg);

    RenderOptions renderOptions;
    renderOptions.width = options.width;
    renderOptions.height = options.height;
    renderOptions.spp = options.spp;
    renderOptions.roughness = options.roughness;
    renderOptions.mip_policy = MipPolicy::LobeFootprint;

    std::cout << "Computing mip0 direct quadrature reference...\n";
    const RenderResult reference = renderer.reference(renderOptions);
    std::cout << "Rendering uniform and importance sampling...\n";
    const NoiseAnalysis uniform =
        runNoiseAnalysis(env, renderer, renderOptions,
                         SamplingMethod::Uniform, MipPolicy::LobeFootprint,
                         reference, options.highlight_margin_deg,
                         options.frames, options.seed);
    const NoiseAnalysis importance =
        runNoiseAnalysis(env, renderer, renderOptions,
                         SamplingMethod::Importance, MipPolicy::LobeFootprint,
                         reference, options.highlight_margin_deg,
                         options.frames, options.seed);

    std::vector<MipRow> mipRows;
    for (MipPolicy policy :
         {MipPolicy::Base, MipPolicy::Roughness, MipPolicy::LobeFootprint}) {
      const NoiseAnalysis analysis =
          policy == MipPolicy::LobeFootprint
              ? importance
              : runNoiseAnalysis(env, renderer, renderOptions,
                                 SamplingMethod::Importance, policy, reference,
                                 options.highlight_margin_deg, options.frames,
                                 options.seed);
      MipRow row;
      row.policy = policy;
      row.mean_lod = analysis.mean_lod;
      row.mean_variance = analysis.mean_variance;
      row.mean_std = analysis.mean_std;
      row.relative_noise = analysis.relative_noise;
      row.p95_std = analysis.p95_std;
      row.rmse_reference = analysis.rmse_reference;
      mipRows.push_back(row);
    }

    ibl::writePpm(options.output + "/render_uniform.ppm",
                  renderOptions.width, renderOptions.height,
                  uniform.first_frame.pixels, 0.18);
    ibl::writePpm(options.output + "/render_importance.ppm",
                  renderOptions.width, renderOptions.height,
                  importance.first_frame.pixels, 0.18);
    ibl::writePpm(options.output + "/render_reference.ppm",
                  renderOptions.width, renderOptions.height, reference.pixels,
                  0.18);
    ibl::writeLinearF32(options.output + "/render_uniform.f32",
                        renderOptions.width, renderOptions.height,
                        uniform.first_frame.pixels);
    ibl::writeLinearF32(options.output + "/render_importance.f32",
                        renderOptions.width, renderOptions.height,
                        importance.first_frame.pixels);
    ibl::writeLinearF32(options.output + "/render_reference.f32",
                        renderOptions.width, renderOptions.height,
                        reference.pixels);
    writeSamplesPerPixelCsv(options.output + "/samples_per_pixel.csv",
                            importance, uniform, env, renderOptions,
                            options.frames, options.highlight_margin_deg);
    writeNoiseByPixelCsv(options.output + "/noise_by_pixel.csv", env, uniform,
                         importance, renderOptions,
                         options.highlight_margin_deg);
    writeMipVarianceCsv(options.output + "/mip_policy_variance.csv", mipRows);
    writeMetricsJson(options.output + "/metrics.json", env, options,
                     options.highlight_margin_deg, directions, uniform,
                     importance, mipRows);

    std::cout << std::fixed << std::setprecision(4);
    std::cout << "Highlight density ratio (importance/uniform)="
              << directions.density_ratio << "x, sample fraction="
              << directions.importance_highlight_fraction
              << ", solid-angle fraction="
              << directions.highlight_solid_angle_fraction << "\n";
    std::cout << "Noise std: uniform=" << uniform.mean_std
              << ", importance=" << importance.mean_std
              << ", reduction=" << uniform.mean_std /
                                       std::max(importance.mean_std, 1e-12)
              << "x\n";
    std::cout << "Mip variance: ";
    for (const MipRow& row : mipRows) {
      std::cout << ibl::mipPolicyName(row.policy) << "=" << row.mean_std
                << " ";
    }
    std::cout << "\nWrote results to " << options.output << "/\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "error: " << error.what() << '\n';
    return 1;
  }
}
