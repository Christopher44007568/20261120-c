#include "ibl/render.h"

#include <algorithm>
#include <cmath>

namespace ibl {
namespace {

Vec3 tangentToWorld(const Vec3& local, const Vec3& normal) {
  const Vec3 up =
      std::abs(normal.y) < 0.999 ? Vec3{0.0, 1.0, 0.0} : Vec3{1.0, 0.0, 0.0};
  const Vec3 tangent = normalize(cross(up, normal));
  const Vec3 bitangent = cross(normal, tangent);
  return normalize(tangent * local.x + bitangent * local.y + normal * local.z);
}

double distributionGgx(double ndoth, double roughness) {
  const double a = std::max(roughness * roughness, 1e-5);
  const double a2 = a * a;
  const double d = ndoth * ndoth * (a2 - 1.0) + 1.0;
  return a2 / std::max(kPi * d * d, 1e-12);
}

double geometrySchlick(double ndotv, double roughness) {
  const double a = roughness * roughness;
  const double k = a * 0.5;
  return ndotv / std::max(ndotv * (1.0 - k) + k, 1e-8);
}

Vec3 fresnelSchlick(double vdoth, const Vec3& f0) {
  const double f = std::pow(std::clamp(1.0 - vdoth, 0.0, 1.0), 5.0);
  return f0 + (Vec3{1.0, 1.0, 1.0} - f0) * f;
}

}  // namespace

const char* samplingMethodName(SamplingMethod method) {
  return method == SamplingMethod::Uniform ? "uniform" : "importance";
}

Renderer::Renderer(const EnvMap& env) : env_(&env) {
  samplers_.reserve(static_cast<std::size_t>(env.mipCount()));
  for (int level = 0; level < env.mipCount(); ++level) {
    samplers_.emplace_back(env, level);
  }
  texel_directions_.reserve(static_cast<std::size_t>(env.width() * env.height()));
  texel_solid_angles_.reserve(
      static_cast<std::size_t>(env.width() * env.height()));
  for (int row = 0; row < env.height(); ++row) {
    for (int col = 0; col < env.width(); ++col) {
      texel_directions_.push_back(
          env.directionFromUv((col + 0.5) / env.width(),
                              (row + 0.5) / env.height()));
      texel_solid_angles_.push_back(env.texelSolidAngle(row));
    }
  }
}

Vec3 Renderer::brdf(const Vec3& normal, const Vec3& view, const Vec3& light,
                    double roughness) {
  const double ndotl = dot(normal, light);
  const double ndotv = std::max(dot(normal, view), 1e-5);
  if (ndotl <= 0.0 || ndotv <= 0.0) {
    return {};
  }
  const Vec3 half = normalize(view + light);
  const double ndoth = std::max(dot(normal, half), 0.0);
  const double vdoth = std::max(dot(view, half), 0.0);
  const Vec3 f0{0.90, 0.82, 0.64};
  const double d = distributionGgx(ndoth, roughness);
  const double g = geometrySchlick(ndotv, roughness) *
                   geometrySchlick(ndotl, roughness);
  const Vec3 f = fresnelSchlick(vdoth, f0);
  return f * (d * g / std::max(4.0 * ndotv * ndotl, 1e-8));
}

bool Renderer::isSpherePixel(int x, int y, int width, int height,
                             double radius, Vec3& normal) {
  const double px = (x + 0.5) / width * 2.0 - 1.0;
  const double py = 1.0 - (y + 0.5) / height * 2.0;
  const double r2 = px * px + py * py;
  if (r2 > radius * radius) {
    return false;
  }
  const double z = std::sqrt(std::max(0.0, 1.0 - r2 / (radius * radius)));
  normal = normalize(Vec3{px / radius, py / radius, z});
  return true;
}

Vec3 Renderer::environmentBackground(double x, double y) const {
  const Vec3 dir = normalize(Vec3{x * 0.75, y * 0.75, 1.0});
  return env_->sampleMip(dir, static_cast<double>(env_->mipCount() - 1));
}

Vec3 Renderer::shadePixel(SamplingMethod method, const RenderOptions& options,
                          const Vec3& normal, Rng& rng, int& valid_samples,
                          double& lod_sum) const {
  const Vec3 view{0.0, 0.0, 1.0};
  const Vec3 reflection = ibl::reflect(-view, normal);
  const double requestedLod =
      selectMipLod(options.mip_policy, *env_, options.roughness, reflection);
  const int mipLevel =
      std::clamp(static_cast<int>(std::lround(requestedLod)), 0,
                 env_->mipCount() - 1);
  const EnvSampler& mipSampler =
      samplers_[static_cast<std::size_t>(mipLevel)];
  Vec3 sum;
  for (int sampleIndex = 0; sampleIndex < options.spp; ++sampleIndex) {
    Vec3 light;
    double pdf = 0.0;
    if (method == SamplingMethod::Uniform) {
      light = tangentToWorld(rng.uniformHemisphere(), normal);
      pdf = 1.0 / (2.0 * kPi);
    } else {
      const EnvSample sample =
          mipSampler.sample(rng.uniform(), rng.uniform());
      light = sample.direction;
      pdf = sample.pdf;
    }
    const double ndotl = dot(normal, light);
    if (ndotl <= 0.0 || pdf <= 0.0) {
      continue;
    }
    ++valid_samples;
    lod_sum += mipLevel;
    const Vec3 radiance = env_->sampleMip(light, mipLevel);
    const Vec3 f = brdf(normal, view, light, options.roughness);
    sum += radiance * f * (ndotl / pdf);
  }
  return sum / static_cast<double>(std::max(options.spp, 1));
}

RenderResult Renderer::render(SamplingMethod method,
                              const RenderOptions& options,
                              std::uint64_t seed) const {
  RenderResult result;
  result.width = options.width;
  result.height = options.height;
  const std::size_t count =
      static_cast<std::size_t>(options.width * options.height);
  result.pixels.assign(count, Vec3{});
  result.valid_samples.assign(count, 0);
  result.mean_lod.assign(count, 0.0);
  result.sphere_mask.assign(count, 0);

  for (int y = 0; y < options.height; ++y) {
    for (int x = 0; x < options.width; ++x) {
      const std::size_t index = static_cast<std::size_t>(y * options.width + x);
      Vec3 normal;
      if (!isSpherePixel(x, y, options.width, options.height,
                         options.sphere_radius, normal)) {
        const double px = (x + 0.5) / options.width * 2.0 - 1.0;
        const double py = 1.0 - (y + 0.5) / options.height * 2.0;
        result.pixels[index] = environmentBackground(px, py) * 0.35;
        continue;
      }
      result.sphere_mask[index] = 1;
      const std::uint64_t pixelSeed =
          seed ^ (0x9e3779b97f4a7c15ULL * (index + 1));
      Rng rng(pixelSeed);
      int valid = 0;
      double lodSum = 0.0;
      result.pixels[index] =
          shadePixel(method, options, normal, rng, valid, lodSum);
      result.valid_samples[index] = valid;
      result.mean_lod[index] =
          valid > 0 ? lodSum / static_cast<double>(valid) : 0.0;
    }
  }
  return result;
}

RenderResult Renderer::reference(const RenderOptions& options) const {
  RenderResult result;
  result.width = options.width;
  result.height = options.height;
  const std::size_t count =
      static_cast<std::size_t>(options.width * options.height);
  result.pixels.assign(count, Vec3{});
  result.valid_samples.assign(count, 0);
  result.mean_lod.assign(count, 0.0);
  result.sphere_mask.assign(count, 0);
  const int texelCount = env_->width() * env_->height();

  for (int y = 0; y < options.height; ++y) {
    for (int x = 0; x < options.width; ++x) {
      const std::size_t index = static_cast<std::size_t>(y * options.width + x);
      Vec3 normal;
      if (!isSpherePixel(x, y, options.width, options.height,
                         options.sphere_radius, normal)) {
        const double px = (x + 0.5) / options.width * 2.0 - 1.0;
        const double py = 1.0 - (y + 0.5) / options.height * 2.0;
        result.pixels[index] = environmentBackground(px, py) * 0.35;
        continue;
      }
      result.sphere_mask[index] = 1;
      const Vec3 view{0.0, 0.0, 1.0};
      Vec3 sum;
      for (int t = 0; t < texelCount; ++t) {
        const Vec3 light = texel_directions_[static_cast<std::size_t>(t)];
        const double ndotl = dot(normal, light);
        if (ndotl <= 0.0) {
          continue;
        }
        const Vec3 f = brdf(normal, view, light, options.roughness);
        const int row = t / env_->width();
        const int col = t % env_->width();
        sum += env_->texel(row, col) * f *
               (ndotl * texel_solid_angles_[static_cast<std::size_t>(t)]);
      }
      result.pixels[index] = sum;
    }
  }
  return result;
}

}  // namespace ibl
