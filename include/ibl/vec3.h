#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>

namespace ibl {

constexpr double kPi = 3.14159265358979323846;

struct Vec3 {
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;

  Vec3() = default;
  Vec3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}

  double& operator[](std::size_t i) { return i == 0 ? x : (i == 1 ? y : z); }
  double operator[](std::size_t i) const {
    return i == 0 ? x : (i == 1 ? y : z);
  }
};

inline Vec3 operator+(const Vec3& a, const Vec3& b) {
  return {a.x + b.x, a.y + b.y, a.z + b.z};
}
inline Vec3 operator-(const Vec3& a, const Vec3& b) {
  return {a.x - b.x, a.y - b.y, a.z - b.z};
}
inline Vec3 operator-(const Vec3& v) { return {-v.x, -v.y, -v.z}; }
inline Vec3 operator*(const Vec3& v, double s) {
  return {v.x * s, v.y * s, v.z * s};
}
inline Vec3 operator*(double s, const Vec3& v) { return v * s; }
inline Vec3 operator*(const Vec3& a, const Vec3& b) {
  return {a.x * b.x, a.y * b.y, a.z * b.z};
}
inline Vec3 operator/(const Vec3& v, double s) {
  return {v.x / s, v.y / s, v.z / s};
}
inline Vec3& operator+=(Vec3& a, const Vec3& b) {
  a.x += b.x;
  a.y += b.y;
  a.z += b.z;
  return a;
}
inline Vec3& operator*=(Vec3& a, double s) {
  a.x *= s;
  a.y *= s;
  a.z *= s;
  return a;
}

inline double dot(const Vec3& a, const Vec3& b) {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}
inline Vec3 cross(const Vec3& a, const Vec3& b) {
  return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z,
          a.x * b.y - a.y * b.x};
}
inline double lengthSquared(const Vec3& v) { return dot(v, v); }
inline double length(const Vec3& v) { return std::sqrt(lengthSquared(v)); }
inline Vec3 normalize(const Vec3& v) {
  const double len = length(v);
  return len > 0.0 ? v / len : Vec3{0.0, 1.0, 0.0};
}
inline Vec3 reflect(const Vec3& incident, const Vec3& normal) {
  return incident - normal * (2.0 * dot(incident, normal));
}
inline Vec3 clamped(const Vec3& v, double lo, double hi) {
  return {std::clamp(v.x, lo, hi), std::clamp(v.y, lo, hi),
          std::clamp(v.z, lo, hi)};
}
inline double luminance(const Vec3& v) {
  return 0.2126 * v.x + 0.7152 * v.y + 0.0722 * v.z;
}
inline Vec3 expComponent(const Vec3& v) {
  return {std::exp(v.x), std::exp(v.y), std::exp(v.z)};
}

}  // namespace ibl
