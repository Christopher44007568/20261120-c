#pragma once

#include <string>
#include <vector>

#include "ibl/vec3.h"

namespace ibl {

struct Highlight {
  std::string name;
  Vec3 direction;
  double sigma_deg = 1.0;
  double radius_deg = 2.0;
  double peak_luminance = 1.0;
  Vec3 color{1.0, 1.0, 1.0};
};

struct MipLevel {
  int width = 0;
  int height = 0;
  std::vector<Vec3> pixels;
};

class EnvMap {
 public:
  EnvMap() = default;
  EnvMap(int width, int height, std::vector<Vec3> pixels,
         std::vector<Highlight> highlights);

  static EnvMap makeSyntheticHdr(int width = 128, int height = 64);

  int width() const { return width_; }
  int height() const { return height_; }
  int mipCount() const { return static_cast<int>(mips_.size()); }
  const std::vector<Highlight>& highlights() const { return highlights_; }
  const MipLevel& mip(int level) const;

  Vec3 texel(int row, int col) const;
  Vec3 sampleBase(double u, double v) const;
  Vec3 sampleMip(const Vec3& direction, double lod) const;
  Vec3 bilinear(const MipLevel& level, double u, double v) const;

  Vec3 directionFromUv(double u, double v) const;
  void uvFromDirection(const Vec3& direction, double& u, double& v) const;

  double luminanceAt(int row, int col) const;
  double texelSolidAngle(int row) const;
  double mipTexelSolidAngle(int level, int row) const;
  double meanLuminance() const;
  double totalEnergy() const;
  double maxLuminance() const;
  double dynamicRange() const;

  bool isNearHighlight(const Vec3& direction, double margin_deg = 0.0) const;
  bool isNearHighlight(const Vec3& direction, int highlight_index,
                       double margin_deg = 0.0) const;
  double highlightSolidAngle(int highlight_index,
                             double margin_deg = 0.0) const;
  double highlightSolidAngle(double margin_deg = 0.0) const;

 private:
  void buildMips();

  int width_ = 0;
  int height_ = 0;
  std::vector<Vec3> pixels_;
  std::vector<Highlight> highlights_;
  std::vector<MipLevel> mips_;
};

double angularDistanceDegrees(const Vec3& a, const Vec3& b);

}  // namespace ibl
