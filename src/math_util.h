#pragma once

#include <algorithm>
#include <cmath>

struct Vec2 {
    float x = 0.0f;
    float y = 0.0f;

    Vec2() = default;
    Vec2(float px, float py) : x(px), y(py) {}

    Vec2 operator+(const Vec2& o) const { return {x + o.x, y + o.y}; }
    Vec2 operator-(const Vec2& o) const { return {x - o.x, y - o.y}; }
    Vec2 operator*(float s) const { return {x * s, y * s}; }
    Vec2& operator+=(const Vec2& o) { x += o.x; y += o.y; return *this; }
};

inline float dot(const Vec2& a, const Vec2& b) { return a.x * b.x + a.y * b.y; }

inline float length(const Vec2& v) { return std::sqrt(dot(v, v)); }

inline Vec2 normalize(const Vec2& v) {
    float len = length(v);
    if (len <= 1e-9f) return {0.0f, 0.0f};
    return {v.x / len, v.y / len};
}

inline Vec2 perp(const Vec2& v) { return {-v.y, v.x}; }

inline float clamp01(float v) { return std::clamp(v, 0.0f, 1.0f); }

inline float clampf(float v, float lo, float hi) { return std::clamp(v, lo, hi); }
