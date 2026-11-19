#include "ibl/sampler.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace ibl {
namespace {

int findInterval(const std::vector<double>& cdf, double target) {
  const auto it = std::lower_bound(cdf.begin(), cdf.end(), target);
  int index = static_cast<int>(it - cdf.begin());
  return std::clamp(index, 0, static_cast<int>(cdf.size()) - 1);
}

int findInterval(const double* cdf, int count, double target) {
  const auto* begin = cdf;
  const auto* end = cdf + count;
  const auto* it = std::lower_bound(begin, end, target);
  int index = static_cast<int>(it - begin);
  return std::clamp(index, 0, count - 1);
}

}  // namespace

std::uint64_t Rng::next() {
  std::uint64_t z = (state_ += 0x9e3779b97f4a7c15ULL);
  z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
  z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
  return z ^ (z >> 31);
}

double Rng::uniform() {
  return static_cast<double>(next() >> 11) * 0x1.0p-53;
}

Vec3 Rng::uniformSphere() {
  const double z = 1.0 - 2.0 * uniform();
  const double phi = 2.0 * kPi * uniform();
  const double r = std::sqrt(std::max(0.0, 1.0 - z * z));
  return {r * std::cos(phi), z, r * std::sin(phi)};
}

Vec3 Rng::uniformHemisphere() {
  const double z = uniform();
  const double phi = 2.0 * kPi * uniform();
  const double r = std::sqrt(std::max(0.0, 1.0 - z * z));
  return {r * std::cos(phi), r * std::sin(phi), z};
}

EnvSampler::EnvSampler(const EnvMap& env, int mip_level)
    : env_(&env), mipLevel_(std::clamp(mip_level, 0, env.mipCount() - 1)) {
  const MipLevel& level = env.mip(mipLevel_);
  const int h = level.height;
  const int w = level.width;
  rowMass_.assign(static_cast<std::size_t>(h), 0.0);
  rowCdf_.assign(static_cast<std::size_t>(h), 0.0);
  colCdf_.assign(static_cast<std::size_t>(h * w), 0.0);

  for (int row = 0; row < h; ++row) {
    const double omega = env.mipTexelSolidAngle(mipLevel_, row);
    double cumulative = 0.0;
    for (int col = 0; col < w; ++col) {
      const double weight = std::max(
          0.0, luminance(level.pixels[static_cast<std::size_t>(row * w + col)]) *
                   omega);
      cumulative += weight;
      colCdf_[static_cast<std::size_t>(row * w + col)] = cumulative;
    }
    rowMass_[static_cast<std::size_t>(row)] = cumulative;
    totalEnergy_ += cumulative;
  }
  if (totalEnergy_ <= 0.0) {
    totalEnergy_ = 1.0;
  }

  double cumulative = 0.0;
  for (int row = 0; row < h; ++row) {
    cumulative += rowMass_[static_cast<std::size_t>(row)];
    rowCdf_[static_cast<std::size_t>(row)] = cumulative;
  }
  for (double& entry : rowCdf_) {
    entry /= totalEnergy_;
  }
  rowCdf_.back() = 1.0;

  for (int row = 0; row < h; ++row) {
    const double mass = std::max(rowMass_[static_cast<std::size_t>(row)],
                                 1e-300);
    for (int col = 0; col < w; ++col) {
      colCdf_[static_cast<std::size_t>(row * w + col)] /= mass;
    }
    colCdf_[static_cast<std::size_t>(row * w + w - 1)] = 1.0;
  }
}

EnvSample EnvSampler::sample(double u1, double u2) const {
  const MipLevel& level = env_->mip(mipLevel_);
  const int w = level.width;
  const int h = level.height;
  const int row = findInterval(rowCdf_, u1);
  const int rowBase = row * w;

  const int col =
      findInterval(colCdf_.data() + rowBase, w, std::clamp(u2, 0.0, 1.0));

  EnvSample result;
  result.row = row;
  result.col = col;
  result.u = (col + 0.5) / w;
  result.v = (row + 0.5) / h;
  result.direction = env_->directionFromUv(result.u, result.v);
  result.pdf = pdfForTexel(row, col);
  return result;
}

double EnvSampler::pdfForTexel(int row, int col) const {
  const MipLevel& level = env_->mip(mipLevel_);
  return luminance(level.pixels[static_cast<std::size_t>(
                       row * level.width + col)]) /
         totalEnergy_;
}

double EnvSampler::pdf(const Vec3& direction) const {
  double u = 0.0;
  double v = 0.0;
  env_->uvFromDirection(direction, u, v);
  const MipLevel& level = env_->mip(mipLevel_);
  const int col =
      std::clamp(static_cast<int>(u * level.width), 0, level.width - 1);
  const int row =
      std::clamp(static_cast<int>(v * level.height), 0, level.height - 1);
  return pdfForTexel(row, col);
}

const char* mipPolicyName(MipPolicy policy) {
  switch (policy) {
    case MipPolicy::Base:
      return "mip0";
    case MipPolicy::Roughness:
      return "roughness";
    case MipPolicy::LobeFootprint:
      return "lobe_footprint";
  }
  return "unknown";
}

double selectMipLod(MipPolicy policy, const EnvMap& env, double roughness,
                    const Vec3& direction) {
  const double maxLod = static_cast<double>(env.mipCount() - 1);
  if (policy == MipPolicy::Base) {
    return 0.0;
  }
  if (policy == MipPolicy::Roughness) {
    return std::clamp(roughness * maxLod, 0.0, maxLod);
  }

  double u = 0.0;
  double v = 0.0;
  env.uvFromDirection(direction, u, v);
  const int row = std::clamp(static_cast<int>(v * env.height()), 0,
                             env.height() - 1);
  const double texelOmega = std::max(env.texelSolidAngle(row), 1e-12);
  const double alpha = std::max(roughness * roughness, 1e-4);
  const double lobeOmega = kPi * alpha * alpha;
  const double lod = 0.5 * std::log2(std::max(lobeOmega / texelOmega, 1e-12));
  return std::clamp(lod, 0.0, maxLod);
}

}  // namespace ibl
