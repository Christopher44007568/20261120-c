#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>

constexpr double kPi = 3.14159265358979323846;
constexpr double kInf = std::numeric_limits<double>::infinity();
constexpr double kEps = 1e-7;

struct Vec3 {
    double x = 0.0, y = 0.0, z = 0.0;

    Vec3() = default;
    Vec3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}

    Vec3 operator+(const Vec3& b) const { return {x + b.x, y + b.y, z + b.z}; }
    Vec3 operator-(const Vec3& b) const { return {x - b.x, y - b.y, z - b.z}; }
    Vec3 operator-() const { return {-x, -y, -z}; }
    Vec3 operator*(double s) const { return {x * s, y * s, z * s}; }
    Vec3 operator/(double s) const { return {x / s, y / s, z / s}; }
    Vec3& operator+=(const Vec3& b) { x += b.x; y += b.y; z += b.z; return *this; }
    Vec3& operator*=(const Vec3& b) { x *= b.x; y *= b.y; z *= b.z; return *this; }
    Vec3& operator*=(double s) { x *= s; y *= s; z *= s; return *this; }
    double operator[](int i) const { return i == 0 ? x : (i == 1 ? y : z); }
};

inline Vec3 operator*(double s, const Vec3& v) { return v * s; }
inline Vec3 operator*(const Vec3& a, const Vec3& b) {
    return {a.x * b.x, a.y * b.y, a.z * b.z};
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
    return len > 0.0 ? v / len : Vec3{};
}
inline double maxComponent(const Vec3& v) {
    return std::max(v.x, std::max(v.y, v.z));
}
inline bool isBlack(const Vec3& v) {
    return v.x <= 0.0 && v.y <= 0.0 && v.z <= 0.0;
}
inline bool isFinite(const Vec3& v) {
    return std::isfinite(v.x) && std::isfinite(v.y) && std::isfinite(v.z);
}
inline Vec3 faceForward(const Vec3& n, const Vec3& toward) {
    return dot(n, toward) < 0.0 ? -n : n;
}
inline Vec3 lerp(const Vec3& a, const Vec3& b, double t) {
    return a * (1.0 - t) + b * t;
}

struct Ray {
    Vec3 o;
    Vec3 d;
    double tmin = 0.0;
    double tmax = kInf;

    Vec3 at(double t) const { return o + d * t; }
};

inline Vec3 sphericalToWorld(const Vec3& n, double u1, double u2) {
    const double z = u1;
    const double r = std::sqrt(std::max(0.0, 1.0 - z * z));
    const double phi = 2.0 * kPi * u2;
    Vec3 t;
    if (std::abs(n.x) > 0.1) {
        t = normalize(cross(Vec3{0, 1, 0}, n));
    } else {
        t = normalize(cross(Vec3{0, 0, 1}, n));
    }
    const Vec3 b = cross(n, t);
    return normalize(t * (r * std::cos(phi)) + b * (r * std::sin(phi)) + n * z);
}

inline void buildBasis(const Vec3& n, Vec3& t, Vec3& b) {
    if (std::abs(n.x) > 0.1) {
        t = normalize(cross(Vec3{0, 1, 0}, n));
    } else {
        t = normalize(cross(Vec3{0, 0, 1}, n));
    }
    b = cross(n, t);
}

inline Vec3 sampleCosineHemisphere(const Vec3& n, double u1, double u2) {
    const double r = std::sqrt(u1);
    const double phi = 2.0 * kPi * u2;
    Vec3 t;
    Vec3 b;
    buildBasis(n, t, b);
    return normalize(t * (r * std::cos(phi)) + b * (r * std::sin(phi)) +
                     n * std::sqrt(std::max(0.0, 1.0 - u1)));
}

inline double cosineHemispherePdf(double cosTheta) {
    return cosTheta > 0.0 ? cosTheta / kPi : 0.0;
}

inline Vec3 reflected(const Vec3& d, const Vec3& n) {
    return normalize(d - n * (2.0 * dot(d, n)));
}

inline bool refract(const Vec3& d, const Vec3& n, double etaI, double etaT,
                    Vec3& out) {
    const double cosI = -dot(d, n);
    const double eta = etaI / etaT;
    const double k = 1.0 - eta * eta * (1.0 - cosI * cosI);
    if (k < 0.0) {
        return false;
    }
    out = normalize(d * eta + n * (eta * cosI - std::sqrt(k)));
    return true;
}

inline double fresnelDielectric(double cosI, double etaI, double etaT) {
    cosI = std::clamp(cosI, 0.0, 1.0);
    const double sinT2 = (etaI / etaT) * (etaI / etaT) * (1.0 - cosI * cosI);
    if (sinT2 >= 1.0) {
        return 1.0;
    }
    const double cosT = std::sqrt(1.0 - sinT2);
    const double r0 = (etaI * cosI - etaT * cosT) / (etaI * cosI + etaT * cosT);
    const double r1 = (etaI * cosT - etaT * cosI) / (etaI * cosT + etaT * cosI);
    return 0.5 * (r0 * r0 + r1 * r1);
}

struct Rng {
    uint64_t state;

    explicit Rng(uint64_t seed)
        : state(seed + 0x9e3779b97f4a7c15ULL) {}

    uint64_t nextU64() {
        state += 0x9e3779b97f4a7c15ULL;
        uint64_t z = state;
        z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
        z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
        return z ^ (z >> 31);
    }

    double uniform() {
        return static_cast<double>(nextU64() >> 11) * 0x1.0p-53;
    }

    double uniform(double lo, double hi) { return lo + (hi - lo) * uniform(); }

    Vec3 sampleDisk() {
        const double r = std::sqrt(uniform());
        const double phi = 2.0 * kPi * uniform();
        return {r * std::cos(phi), r * std::sin(phi), 0.0};
    }
};

inline uint64_t hashSeed(uint64_t a, uint64_t b, uint64_t c = 0) {
    uint64_t x = a + 0x9e3779b97f4a7c15ULL;
    x ^= b + 0x9e3779b97f4a7c15ULL + (x << 6) + (x >> 2);
    x ^= c + 0x9e3779b97f4a7c15ULL + (x << 6) + (x >> 2);
    return x;
}
