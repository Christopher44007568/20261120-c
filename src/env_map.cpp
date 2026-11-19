#include "ibl/env_map.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace ibl {
namespace {

double smoothNoise(double x, double y) {
  const double n = std::sin(12.9898 * x + 78.233 * y) * 43758.5453;
  return n - std::floor(n);
}

Vec3 addHighlight(const Vec3& base, const Vec3& direction,
                  const Highlight& light) {
  const double angle = angularDistanceDegrees(direction, light.direction);
  const double sigma = std::max(light.sigma_deg, 1e-6) * kPi / 180.0;
  const double theta = angle * kPi / 180.0;
  const double core = std::exp(-0.5 * (theta * theta) / (sigma * sigma));
  const double halo =
      0.035 * std::exp(-0.5 * (theta * theta) / (9.0 * sigma * sigma));
  return base + light.color * (light.peak_luminance * (core + halo));
}

}  // namespace

double angularDistanceDegrees(const Vec3& a, const Vec3& b) {
  return std::acos(std::clamp(dot(normalize(a), normalize(b)), -1.0, 1.0)) *
         180.0 / kPi;
}

EnvMap::EnvMap(int width, int height, std::vector<Vec3> pixels,
               std::vector<Highlight> highlights)
    : width_(width),
      height_(height),
      pixels_(std::move(pixels)),
      highlights_(std::move(highlights)) {
  if (width_ <= 0 || height_ <= 0 ||
      pixels_.size() != static_cast<std::size_t>(width_ * height_)) {
    throw std::invalid_argument("invalid environment map dimensions");
  }
  buildMips();
}

EnvMap EnvMap::makeSyntheticHdr(int width, int height) {
  std::vector<Highlight> lights;
  lights.push_back({"key_sun", normalize(Vec3{-0.55, 0.58, 0.60}), 1.8, 3.6,
                    12000.0, {1.0, 0.82, 0.52}});
  lights.push_back({"rim_light", normalize(Vec3{0.78, 0.30, -0.55}), 1.1, 2.2,
                    26000.0, {0.58, 0.75, 1.0}});
  lights.push_back({"softbox", normalize(Vec3{0.25, 0.72, 0.65}), 5.0, 10.0,
                    1100.0, {1.0, 0.95, 0.88}});

  std::vector<Vec3> pixels(static_cast<std::size_t>(width * height));
  for (int row = 0; row < height; ++row) {
    const double v = (row + 0.5) / height;
    const double theta = v * kPi;
    for (int col = 0; col < width; ++col) {
      const double u = (col + 0.5) / width;
      const double phi = (u - 0.5) * 2.0 * kPi;
      const Vec3 dir{std::sin(theta) * std::cos(phi), std::cos(theta),
                     std::sin(theta) * std::sin(phi)};

      Vec3 color;
      if (dir.y >= 0.0) {
        const double horizon = std::pow(1.0 - dir.y, 5.0);
        color = Vec3{0.055, 0.085, 0.16} * (1.0 - 0.55 * dir.y) +
                Vec3{0.78, 0.48, 0.24} * (0.22 * horizon);
      } else {
        const double depth = std::clamp(-dir.y, 0.0, 1.0);
        color = Vec3{0.035, 0.045, 0.055} * (1.0 - 0.55 * depth);
      }

      const double cloud = 0.55 * smoothNoise(u * 31.0, v * 17.0) +
                           0.45 * smoothNoise(u * 73.0, v * 41.0);
      color += Vec3{0.10, 0.13, 0.20} *
               (dir.y > 0.0 ? cloud * dir.y * dir.y : 0.0);
      for (const Highlight& light : lights) {
        color = addHighlight(color, dir, light);
      }
      pixels[static_cast<std::size_t>(row * width + col)] = color;
    }
  }
  return EnvMap(width, height, std::move(pixels), std::move(lights));
}

void EnvMap::buildMips() {
  mips_.clear();
  mips_.push_back({width_, height_, pixels_});
  while (mips_.back().width > 8 && mips_.back().height > 4) {
    const MipLevel& src = mips_.back();
    MipLevel dst;
    dst.width = std::max(1, src.width / 2);
    dst.height = std::max(1, src.height / 2);
    dst.pixels.assign(static_cast<std::size_t>(dst.width * dst.height),
                      Vec3{});
    for (int row = 0; row < dst.height; ++row) {
      for (int col = 0; col < dst.width; ++col) {
        Vec3 sum;
        double weightSum = 0.0;
        for (int dy = 0; dy < 2; ++dy) {
          for (int dx = 0; dx < 2; ++dx) {
            const int srcRow = std::min(row * 2 + dy, src.height - 1);
            const int srcCol = (col * 2 + dx) % src.width;
            const double weight =
                std::max(1e-8, std::sin((srcRow + 0.5) / src.height * kPi));
            sum += src.pixels[static_cast<std::size_t>(srcRow * src.width +
                                                       srcCol)] *
                   weight;
            weightSum += weight;
          }
        }
        dst.pixels[static_cast<std::size_t>(row * dst.width + col)] =
            sum / weightSum;
      }
    }
    mips_.push_back(std::move(dst));
  }
}

const MipLevel& EnvMap::mip(int level) const {
  const int clamped = std::clamp(level, 0, mipCount() - 1);
  return mips_[static_cast<std::size_t>(clamped)];
}

Vec3 EnvMap::texel(int row, int col) const {
  row = std::clamp(row, 0, height_ - 1);
  col = ((col % width_) + width_) % width_;
  return pixels_[static_cast<std::size_t>(row * width_ + col)];
}

Vec3 EnvMap::directionFromUv(double u, double v) const {
  u -= std::floor(u);
  v = std::clamp(v, 0.0, 1.0);
  const double phi = (u - 0.5) * 2.0 * kPi;
  const double theta = v * kPi;
  return {std::sin(theta) * std::cos(phi), std::cos(theta),
          std::sin(theta) * std::sin(phi)};
}

void EnvMap::uvFromDirection(const Vec3& direction, double& u,
                             double& v) const {
  const Vec3 d = normalize(direction);
  u = std::atan2(d.z, d.x) / (2.0 * kPi) + 0.5;
  u -= std::floor(u);
  v = std::acos(std::clamp(d.y, -1.0, 1.0)) / kPi;
}

Vec3 EnvMap::bilinear(const MipLevel& level, double u, double v) const {
  u -= std::floor(u);
  const double x = u * level.width - 0.5;
  const double y = std::clamp(v * level.height - 0.5, 0.0,
                              level.height - 1.0);
  const int x0 = static_cast<int>(std::floor(x));
  const int y0 = static_cast<int>(std::floor(y));
  const double fx = x - x0;
  const double fy = y - y0;
  auto fetch = [&](int xx, int yy) {
    xx = ((xx % level.width) + level.width) % level.width;
    yy = std::clamp(yy, 0, level.height - 1);
    return level.pixels[static_cast<std::size_t>(yy * level.width + xx)];
  };
  const Vec3 a = fetch(x0, y0) * (1.0 - fx) + fetch(x0 + 1, y0) * fx;
  const Vec3 b =
      fetch(x0, y0 + 1) * (1.0 - fx) + fetch(x0 + 1, y0 + 1) * fx;
  return a * (1.0 - fy) + b * fy;
}

Vec3 EnvMap::sampleBase(double u, double v) const {
  return bilinear(mips_.front(), u, v);
}

Vec3 EnvMap::sampleMip(const Vec3& direction, double lod) const {
  double u = 0.0;
  double v = 0.0;
  uvFromDirection(direction, u, v);
  lod = std::clamp(lod, 0.0, static_cast<double>(mipCount() - 1));
  const int lo = static_cast<int>(std::floor(lod));
  const int hi = std::min(lo + 1, mipCount() - 1);
  const double f = lod - lo;
  return bilinear(mip(lo), u, v) * (1.0 - f) + bilinear(mip(hi), u, v) * f;
}

double EnvMap::luminanceAt(int row, int col) const {
  return luminance(texel(row, col));
}

double EnvMap::texelSolidAngle(int row) const {
  const double dPhi = 2.0 * kPi / width_;
  const double dTheta = kPi / height_;
  return dPhi * dTheta * std::sin((row + 0.5) / height_ * kPi);
}

double EnvMap::mipTexelSolidAngle(int level, int row) const {
  const MipLevel& selected = mip(level);
  const double dPhi = 2.0 * kPi / selected.width;
  const double dTheta = kPi / selected.height;
  return dPhi * dTheta *
         std::sin((row + 0.5) / selected.height * kPi);
}

double EnvMap::totalEnergy() const {
  double sum = 0.0;
  for (int row = 0; row < height_; ++row) {
    const double omega = texelSolidAngle(row);
    for (int col = 0; col < width_; ++col) {
      sum += luminanceAt(row, col) * omega;
    }
  }
  return sum;
}

double EnvMap::meanLuminance() const {
  return totalEnergy() / (4.0 * kPi);
}

double EnvMap::maxLuminance() const {
  double maximum = 0.0;
  for (const Vec3& pixel : pixels_) {
    maximum = std::max(maximum, luminance(pixel));
  }
  return maximum;
}

double EnvMap::dynamicRange() const {
  std::vector<double> values;
  values.reserve(pixels_.size());
  for (const Vec3& pixel : pixels_) {
    values.push_back(luminance(pixel));
  }
  std::sort(values.begin(), values.end());
  const double p01 = values[std::max<std::size_t>(
      1, values.size() / 100) - 1];
  return maxLuminance() / std::max(p01, 1e-9);
}

bool EnvMap::isNearHighlight(const Vec3& direction, double margin_deg) const {
  for (std::size_t i = 0; i < highlights_.size(); ++i) {
    if (isNearHighlight(direction, static_cast<int>(i), margin_deg)) {
      return true;
    }
  }
  return false;
}

bool EnvMap::isNearHighlight(const Vec3& direction, int highlight_index,
                             double margin_deg) const {
  if (highlight_index < 0 ||
      highlight_index >= static_cast<int>(highlights_.size())) {
    return false;
  }
  const Highlight& light = highlights_[static_cast<std::size_t>(highlight_index)];
  return angularDistanceDegrees(direction, light.direction) <=
         light.radius_deg + margin_deg;
}

double EnvMap::highlightSolidAngle(double margin_deg) const {
  double total = 0.0;
  for (int row = 0; row < height_; ++row) {
    const double omega = texelSolidAngle(row);
    for (int col = 0; col < width_; ++col) {
      if (isNearHighlight(directionFromUv((col + 0.5) / width_,
                                          (row + 0.5) / height_),
                          margin_deg)) {
        total += omega;
      }
    }
  }
  return total;
}

double EnvMap::highlightSolidAngle(int highlight_index,
                                   double margin_deg) const {
  if (highlight_index < 0 ||
      highlight_index >= static_cast<int>(highlights_.size())) {
    return 0.0;
  }
  double total = 0.0;
  for (int row = 0; row < height_; ++row) {
    const double omega = texelSolidAngle(row);
    for (int col = 0; col < width_; ++col) {
      if (isNearHighlight(directionFromUv((col + 0.5) / width_,
                                          (row + 0.5) / height_),
                          highlight_index, margin_deg)) {
        total += omega;
      }
    }
  }
  return total;
}

}  // namespace ibl
