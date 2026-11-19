#pragma once
#include <cmath>
#include <cstdint>
#include <algorithm>
#include <limits>

struct Vec3 {
    float x = 0, y = 0, z = 0;
    Vec3() = default;
    Vec3(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}
    Vec3 operator+(const Vec3& o) const { return {x + o.x, y + o.y, z + o.z}; }
    Vec3 operator-(const Vec3& o) const { return {x - o.x, y - o.y, z - o.z}; }
    Vec3 operator*(float s) const { return {x * s, y * s, z * s}; }
    Vec3 operator*(const Vec3& o) const { return {x * o.x, y * o.y, z * o.z}; }
    float dot(const Vec3& o) const { return x * o.x + y * o.y + z * o.z; }
    Vec3 cross(const Vec3& o) const {
        return {y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x};
    }
    float length() const { return std::sqrt(dot(*this)); }
    Vec3 normalized() const { float l = length(); return l > 0 ? (*this) * (1.0f / l) : *this; }
    float& operator[](int i) { return (&x)[i]; }
    float operator[](int i) const { return (&x)[i]; }
};

struct Mat4 {
    float m[3][4];
    static Mat4 identity() {
        Mat4 r{};
        r.m[0][0] = r.m[1][1] = r.m[2][2] = 1.0f;
        return r;
    }
    static Mat4 compose(const Vec3& t, float rotY, const Vec3& s) {
        float c = std::cos(rotY), sn = std::sin(rotY);
        Mat4 r{};
        r.m[0][0] = c * s.x;   r.m[0][1] = 0;    r.m[0][2] = sn * s.z;  r.m[0][3] = t.x;
        r.m[1][0] = 0;         r.m[1][1] = s.y;  r.m[1][2] = 0;         r.m[1][3] = t.y;
        r.m[2][0] = -sn * s.x; r.m[2][1] = 0;    r.m[2][2] = c * s.z;   r.m[2][3] = t.z;
        return r;
    }
    Vec3 transformPoint(const Vec3& p) const {
        return {m[0][0] * p.x + m[0][1] * p.y + m[0][2] * p.z + m[0][3],
                m[1][0] * p.x + m[1][1] * p.y + m[1][2] * p.z + m[1][3],
                m[2][0] * p.x + m[2][1] * p.y + m[2][2] * p.z + m[2][3]};
    }
    Vec3 transformVector(const Vec3& v) const {
        return {m[0][0] * v.x + m[0][1] * v.y + m[0][2] * v.z,
                m[1][0] * v.x + m[1][1] * v.y + m[1][2] * v.z,
                m[2][0] * v.x + m[2][1] * v.y + m[2][2] * v.z};
    }
    Mat4 inverse() const {
        float a = m[0][0], b = m[0][1], c = m[0][2];
        float d = m[1][0], e = m[1][1], f = m[1][2];
        float g = m[2][0], h = m[2][1], i = m[2][2];
        float A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
        float det = a * A + b * B + c * C;
        float inv = 1.0f / det;
        Mat4 r{};
        r.m[0][0] = A * inv;
        r.m[0][1] = -(b * i - c * h) * inv;
        r.m[0][2] = (b * f - c * e) * inv;
        r.m[1][0] = B * inv;
        r.m[1][1] = (a * i - c * g) * inv;
        r.m[1][2] = -(a * f - c * d) * inv;
        r.m[2][0] = C * inv;
        r.m[2][1] = -(a * h - b * g) * inv;
        r.m[2][2] = (a * e - b * d) * inv;
        Vec3 t{m[0][3], m[1][3], m[2][3]};
        Vec3 ti = r.transformVector(t);
        r.m[0][3] = -ti.x; r.m[1][3] = -ti.y; r.m[2][3] = -ti.z;
        return r;
    }
};

struct AABB {
    Vec3 lo{std::numeric_limits<float>::max(), std::numeric_limits<float>::max(),
            std::numeric_limits<float>::max()};
    Vec3 hi{std::numeric_limits<float>::lowest(), std::numeric_limits<float>::lowest(),
            std::numeric_limits<float>::lowest()};
    void expand(const Vec3& p) {
        lo.x = std::min(lo.x, p.x); lo.y = std::min(lo.y, p.y); lo.z = std::min(lo.z, p.z);
        hi.x = std::max(hi.x, p.x); hi.y = std::max(hi.y, p.y); hi.z = std::max(hi.z, p.z);
    }
    void expand(const AABB& b) { expand(b.lo); expand(b.hi); }
    Vec3 centroid() const { return (lo + hi) * 0.5f; }
    AABB transformed(const Mat4& m) const {
        AABB r;
        for (int c = 0; c < 8; ++c) {
            Vec3 p{(c & 1) ? hi.x : lo.x, (c & 2) ? hi.y : lo.y, (c & 4) ? hi.z : lo.z};
            r.expand(m.transformPoint(p));
        }
        return r;
    }
    bool intersect(const Vec3& ro, const Vec3& invD, float tMax) const {
        float t0 = (lo.x - ro.x) * invD.x, t1 = (hi.x - ro.x) * invD.x;
        float tmin = std::min(t0, t1), tmax = std::max(t0, t1);
        t0 = (lo.y - ro.y) * invD.y; t1 = (hi.y - ro.y) * invD.y;
        tmin = std::max(tmin, std::min(t0, t1)); tmax = std::min(tmax, std::max(t0, t1));
        t0 = (lo.z - ro.z) * invD.z; t1 = (hi.z - ro.z) * invD.z;
        tmin = std::max(tmin, std::min(t0, t1)); tmax = std::min(tmax, std::max(t0, t1));
        return tmax >= std::max(tmin, 0.0f) && tmin <= tMax;
    }
};

struct Ray {
    Vec3 origin, dir, invDir;
    static Ray make(const Vec3& o, const Vec3& d) {
        Ray r;
        r.origin = o;
        r.dir = d;
        r.invDir = {1.0f / d.x, 1.0f / d.y, 1.0f / d.z};
        return r;
    }
};

struct Tri {
    Vec3 v0, v1, v2;
    Vec3 centroid() const { return (v0 + v1 + v2) * (1.0f / 3.0f); }
    AABB bounds() const { AABB b; b.expand(v0); b.expand(v1); b.expand(v2); return b; }
    bool intersect(const Ray& r, float& t) const {
        Vec3 e1 = v1 - v0, e2 = v2 - v0;
        Vec3 p = r.dir.cross(e2);
        float det = e1.dot(p);
        if (std::fabs(det) < 1e-9f) return false;
        float inv = 1.0f / det;
        Vec3 s = r.origin - v0;
        float u = s.dot(p) * inv;
        if (u < 0.0f || u > 1.0f) return false;
        Vec3 q = s.cross(e1);
        float v = r.dir.dot(q) * inv;
        if (v < 0.0f || u + v > 1.0f) return false;
        float tt = e2.dot(q) * inv;
        if (tt <= 1e-6f || tt >= t) return false;
        t = tt;
        return true;
    }
};
