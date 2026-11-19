#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "ibl/env_map.h"

namespace ibl {

class Rng {
 public:
  explicit Rng(std::uint64_t seed) : state_(seed ? seed : 1) {}
  std::uint64_t next();
  double uniform();
  Vec3 uniformSphere();
  Vec3 uniformHemisphere();
  double uniformRange(double lo, double hi) {
    return lo + (hi - lo) * uniform();
  }

 private:
  std::uint64_t state_;
};

struct EnvSample {
  Vec3 direction;
  double pdf = 0.0;
  double u = 0.0;
  double v = 0.0;
  int row = 0;
  int col = 0;
};

class EnvSampler {
 public:
  explicit EnvSampler(const EnvMap& env, int mip_level = 0);

  EnvSample sample(double u1, double u2) const;
  double pdfForTexel(int row, int col) const;
  double pdf(const Vec3& direction) const;
  double totalEnergy() const { return totalEnergy_; }
  const EnvMap& env() const { return *env_; }
  int mipLevel() const { return mipLevel_; }

 private:
  const EnvMap* env_ = nullptr;
  int mipLevel_ = 0;
  double totalEnergy_ = 0.0;
  std::vector<double> rowCdf_;
  std::vector<double> rowMass_;
  std::vector<double> colCdf_;
};

enum class MipPolicy {
  Base = 0,
  Roughness = 1,
  LobeFootprint = 2,
};

const char* mipPolicyName(MipPolicy policy);
double selectMipLod(MipPolicy policy, const EnvMap& env, double roughness,
                    const Vec3& direction);

}  // namespace ibl
