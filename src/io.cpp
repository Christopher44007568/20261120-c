#include "ibl/io.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>

namespace ibl {
namespace {

double filmicToneMap(double x, double exposure) {
  const double value = std::max(0.0, x * exposure);
  const double mapped =
      (value * (2.51 * value + 0.03)) /
      (value * (2.43 * value + 0.59) + 0.14);
  return std::clamp(mapped, 0.0, 1.0);
}

std::uint8_t toByte(double linear, double exposure) {
  const double value = filmicToneMap(linear, exposure);
  const double srgb =
      value <= 0.0031308 ? 12.92 * value
                         : 1.055 * std::pow(value, 1.0 / 2.4) - 0.055;
  return static_cast<std::uint8_t>(
      std::clamp(std::lround(srgb * 255.0), 0L, 255L));
}

}  // namespace

void ensureDirectory(const std::string& path) {
  if (!path.empty()) {
    std::filesystem::create_directories(path);
  }
}

void writePpm(const std::string& path, int width, int height,
              const std::vector<Vec3>& pixels, double exposure) {
  if (width <= 0 || height <= 0 ||
      pixels.size() != static_cast<std::size_t>(width * height)) {
    throw std::invalid_argument("invalid PPM dimensions");
  }
  std::ofstream out(path, std::ios::binary);
  if (!out) {
    throw std::runtime_error("cannot open " + path);
  }
  out << "P6\n" << width << ' ' << height << "\n255\n";
  for (const Vec3& pixel : pixels) {
    const char rgb[3] = {
        static_cast<char>(toByte(pixel.x, exposure)),
        static_cast<char>(toByte(pixel.y, exposure)),
        static_cast<char>(toByte(pixel.z, exposure)),
    };
    out.write(rgb, 3);
  }
}

void writeLinearF32(const std::string& path, int width, int height,
                    const std::vector<Vec3>& pixels) {
  if (width <= 0 || height <= 0 ||
      pixels.size() != static_cast<std::size_t>(width * height)) {
    throw std::invalid_argument("invalid linear image dimensions");
  }
  std::ofstream out(path, std::ios::binary);
  if (!out) {
    throw std::runtime_error("cannot open " + path);
  }
  const std::int32_t header[2] = {width, height};
  out.write(reinterpret_cast<const char*>(header), sizeof(header));
  for (const Vec3& pixel : pixels) {
    const float rgb[3] = {static_cast<float>(pixel.x),
                          static_cast<float>(pixel.y),
                          static_cast<float>(pixel.z)};
    out.write(reinterpret_cast<const char*>(rgb), sizeof(rgb));
  }
}

}  // namespace ibl
