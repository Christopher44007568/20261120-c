#pragma once
#include <cmath>

struct Vec3 {
  double x, y, z;
  Vec3() : x(0), y(0), z(0) {}
  Vec3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}
  Vec3 operator+(const Vec3& o) const { return {x + o.x, y + o.y, z + o.z}; }
  Vec3 operator-(const Vec3& o) const { return {x - o.x, y - o.y, z - o.z}; }
  Vec3 operator*(double s) const { return {x * s, y * s, z * s}; }
  Vec3 operator*(const Vec3& o) const { return {x * o.x, y * o.y, z * o.z}; }
  Vec3 operator/(double s) const { return {x / s, y / s, z / s}; }
  double dot(const Vec3& o) const { return x * o.x + y * o.y + z * o.z; }
  Vec3 cross(const Vec3& o) const {
    return {y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x};
  }
  double length() const { return std::sqrt(dot(*this)); }
  Vec3 normalized() const { return *this / length(); }
};

inline Vec3 reflect(const Vec3& d, const Vec3& n) {
  return d - n * (2.0 * d.dot(n));
}

// Build an orthonormal basis (t, b) around normal n.
inline void onb(const Vec3& n, Vec3& t, Vec3& b) {
  Vec3 up = std::abs(n.y) < 0.9 ? Vec3(0, 1, 0) : Vec3(1, 0, 0);
  t = up.cross(n).normalized();
  b = n.cross(t);
}
