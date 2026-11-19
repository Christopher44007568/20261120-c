#pragma once

#include <algorithm>
#include <cmath>

struct Vec3 {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;

    Vec3() = default;
    Vec3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}

    Vec3 operator+(const Vec3& rhs) const { return {x + rhs.x, y + rhs.y, z + rhs.z}; }
    Vec3 operator-(const Vec3& rhs) const { return {x - rhs.x, y - rhs.y, z - rhs.z}; }
    Vec3 operator-() const { return {-x, -y, -z}; }
    Vec3 operator*(double s) const { return {x * s, y * s, z * s}; }
    Vec3 operator/(double s) const { return {x / s, y / s, z / s}; }
    Vec3 operator*(const Vec3& rhs) const { return {x * rhs.x, y * rhs.y, z * rhs.z}; }
    Vec3& operator+=(const Vec3& rhs) { x += rhs.x; y += rhs.y; z += rhs.z; return *this; }
    Vec3& operator*=(double s) { x *= s; y *= s; z *= s; return *this; }
    Vec3& operator*=(const Vec3& rhs) { x *= rhs.x; y *= rhs.y; z *= rhs.z; return *this; }
};

inline Vec3 operator*(double s, const Vec3& v) { return v * s; }
inline double dot(const Vec3& a, const Vec3& b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
inline Vec3 cross(const Vec3& a, const Vec3& b) {
    return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}
inline double lengthSquared(const Vec3& v) { return dot(v, v); }
inline double length(const Vec3& v) { return std::sqrt(lengthSquared(v)); }
inline Vec3 normalize(const Vec3& v) { return v / std::max(length(v), 1e-12); }
inline Vec3 clamp01(const Vec3& v) {
    return {std::clamp(v.x, 0.0, 1.0), std::clamp(v.y, 0.0, 1.0), std::clamp(v.z, 0.0, 1.0)};
}
inline double luminance(const Vec3& v) { return 0.2126 * v.x + 0.7152 * v.y + 0.0722 * v.z; }

struct Ray {
    Vec3 origin;
    Vec3 direction;
};

