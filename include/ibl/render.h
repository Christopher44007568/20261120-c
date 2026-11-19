#pragma once

#include <cstdint>
#include <vector>

#include "ibl/env_map.h"
#include "ibl/sampler.h"

namespace ibl {

enum class SamplingMethod {
  Uniform = 0,
  Importance = 1,
};

const char* samplingMethodName(SamplingMethod method);

struct RenderOptions {
  int width = 160;
  int height = 160;
  double sphere_radius = 0.86;
  double roughness = 0.32;
  int spp = 16;
  MipPolicy mip_policy = MipPolicy::LobeFootprint;
};

struct RenderResult {
  int width = 0;
  int height = 0;
  std::vector<Vec3> pixels;
  std::vector<int> valid_samples;
  std::vector<double> mean_lod;
  std::vector<std::uint8_t> sphere_mask;
};

class Renderer {
 public:
  explicit Renderer(const EnvMap& env);

  RenderResult render(SamplingMethod method, const RenderOptions& options,
                      std::uint64_t seed) const;
  RenderResult reference(const RenderOptions& options) const;

  static Vec3 brdf(const Vec3& normal, const Vec3& view, const Vec3& light,
                   double roughness);
  static bool isSpherePixel(int x, int y, int width, int height,
                            double radius, Vec3& normal);

 private:
  Vec3 shadePixel(SamplingMethod method, const RenderOptions& options,
                  const Vec3& normal, Rng& rng, int& valid_samples,
                  double& lod_sum) const;
  Vec3 environmentBackground(double x, double y) const;

  const EnvMap* env_ = nullptr;
  std::vector<EnvSampler> samplers_;
  std::vector<Vec3> texel_directions_;
  std::vector<double> texel_solid_angles_;
};

}  // namespace ibl
