#pragma once
#include <cmath>
#include <cfloat>

struct Vec3 {
  float x = 0, y = 0, z = 0;
  Vec3() = default;
  Vec3(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}
  float operator[](int i) const { return (&x)[i]; }
  float& operator[](int i) { return (&x)[i]; }
  Vec3 operator+(const Vec3& o) const { return {x + o.x, y + o.y, z + o.z}; }
  Vec3 operator-(const Vec3& o) const { return {x - o.x, y - o.y, z - o.z}; }
  Vec3 operator*(float s) const { return {x * s, y * s, z * s}; }
  float dot(const Vec3& o) const { return x * o.x + y * o.y + z * o.z; }
  Vec3 cross(const Vec3& o) const {
    return {y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x};
  }
  float length() const { return std::sqrt(dot(*this)); }
  Vec3 normalized() const {
    float l = length();
    return l > 0 ? (*this) * (1.0f / l) : *this;
  }
};

struct Ray {
  Vec3 o, d, invd;
  int sign[3] = {0, 0, 0};
  void precompute() {
    for (int i = 0; i < 3; ++i) {
      invd[i] = 1.0f / d[i];
      sign[i] = invd[i] < 0 ? 1 : 0;
    }
  }
};

struct AABB {
  Vec3 mn{FLT_MAX, FLT_MAX, FLT_MAX};
  Vec3 mx{-FLT_MAX, -FLT_MAX, -FLT_MAX};
  void expand(const Vec3& p) {
    for (int i = 0; i < 3; ++i) {
      if (p[i] < mn[i]) mn[i] = p[i];
      if (p[i] > mx[i]) mx[i] = p[i];
    }
  }
  void expand(const AABB& b) {
    expand(b.mn);
    expand(b.mx);
  }
  float surfaceArea() const {
    float ex = mx.x - mn.x, ey = mx.y - mn.y, ez = mx.z - mn.z;
    if (ex < 0 || ey < 0 || ez < 0) return 0.0f;
    return 2.0f * (ex * ey + ey * ez + ez * ex);
  }
};

struct Triangle {
  Vec3 v0, v1, v2;
  AABB bounds() const {
    AABB b;
    b.expand(v0);
    b.expand(v1);
    b.expand(v2);
    return b;
  }
};

struct Hit {
  float t = FLT_MAX;
  int triId = -1;
};

// Moller-Trumbore, two-sided.
inline bool intersectTriangle(const Ray& ray, const Triangle& tri, float& tOut) {
  const float eps = 1e-9f;
  Vec3 e1 = tri.v1 - tri.v0;
  Vec3 e2 = tri.v2 - tri.v0;
  Vec3 p = ray.d.cross(e2);
  float det = e1.dot(p);
  if (std::fabs(det) < eps) return false;
  float inv = 1.0f / det;
  Vec3 s = ray.o - tri.v0;
  float u = s.dot(p) * inv;
  if (u < 0.0f || u > 1.0f) return false;
  Vec3 q = s.cross(e1);
  float v = ray.d.dot(q) * inv;
  if (v < 0.0f || u + v > 1.0f) return false;
  float t = e2.dot(q) * inv;
  if (t < 0.0f) return false;
  tOut = t;
  return true;
}
