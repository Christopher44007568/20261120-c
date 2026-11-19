#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>

namespace hzb {

constexpr float kPi = 3.14159265358979323846f;

struct Vec3 {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;

    Vec3 operator+(const Vec3& rhs) const { return {x + rhs.x, y + rhs.y, z + rhs.z}; }
    Vec3 operator-(const Vec3& rhs) const { return {x - rhs.x, y - rhs.y, z - rhs.z}; }
    Vec3 operator*(float scale) const { return {x * scale, y * scale, z * scale}; }
    Vec3& operator+=(const Vec3& rhs) {
        x += rhs.x;
        y += rhs.y;
        z += rhs.z;
        return *this;
    }
};

inline float dot(const Vec3& a, const Vec3& b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

inline Vec3 cross(const Vec3& a, const Vec3& b) {
    return {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    };
}

inline Vec3 normalize(const Vec3& value) {
    const float length = std::sqrt(dot(value, value));
    return length > 1.0e-8f ? value * (1.0f / length) : Vec3{};
}

struct Mat4 {
    std::array<float, 16> value{};

    static Mat4 identity() {
        Mat4 result;
        result.value = {1.0f, 0.0f, 0.0f, 0.0f,
                        0.0f, 1.0f, 0.0f, 0.0f,
                        0.0f, 0.0f, 1.0f, 0.0f,
                        0.0f, 0.0f, 0.0f, 1.0f};
        return result;
    }
};

inline Mat4 operator*(const Mat4& lhs, const Mat4& rhs) {
    Mat4 result;
    for (int column = 0; column < 4; ++column) {
        for (int row = 0; row < 4; ++row) {
            float sum = 0.0f;
            for (int k = 0; k < 4; ++k) {
                sum += lhs.value[k * 4 + row] * rhs.value[column * 4 + k];
            }
            result.value[column * 4 + row] = sum;
        }
    }
    return result;
}

inline std::array<float, 4> transform(const Mat4& matrix, const Vec3& point) {
    std::array<float, 4> result{};
    for (int row = 0; row < 4; ++row) {
        result[row] = matrix.value[row] * point.x +
                      matrix.value[4 + row] * point.y +
                      matrix.value[8 + row] * point.z +
                      matrix.value[12 + row];
    }
    return result;
}

inline Mat4 perspective(float verticalFovRadians, float aspect, float nearPlane, float farPlane) {
    const float focal = 1.0f / std::tan(verticalFovRadians * 0.5f);
    Mat4 result;
    result.value[0] = focal / aspect;
    result.value[5] = focal;
    result.value[10] = (farPlane + nearPlane) / (nearPlane - farPlane);
    result.value[11] = -1.0f;
    result.value[14] = (2.0f * farPlane * nearPlane) / (nearPlane - farPlane);
    return result;
}

inline Mat4 lookAt(const Vec3& eye, const Vec3& target, const Vec3& up) {
    const Vec3 forward = normalize(target - eye);
    const Vec3 side = normalize(cross(forward, up));
    const Vec3 correctedUp = cross(side, forward);

    Mat4 result = Mat4::identity();
    result.value[0] = side.x;
    result.value[1] = correctedUp.x;
    result.value[2] = -forward.x;
    result.value[4] = side.y;
    result.value[5] = correctedUp.y;
    result.value[6] = -forward.y;
    result.value[8] = side.z;
    result.value[9] = correctedUp.z;
    result.value[10] = -forward.z;
    result.value[12] = -dot(side, eye);
    result.value[13] = -dot(correctedUp, eye);
    result.value[14] = dot(forward, eye);
    return result;
}

struct Aabb {
    Vec3 min;
    Vec3 max;

    Vec3 center() const { return (min + max) * 0.5f; }
    Vec3 extent() const { return max - min; }
};

struct Camera {
    Vec3 position;
    Vec3 target;
    Vec3 up{0.0f, 1.0f, 0.0f};
    float verticalFovDegrees = 60.0f;
    float nearPlane = 0.08f;
    float farPlane = 40.0f;

    Mat4 viewProjection(float aspect) const {
        const Mat4 projection =
            perspective(verticalFovDegrees * kPi / 180.0f, aspect, nearPlane, farPlane);
        return projection * lookAt(position, target, up);
    }
};

inline float clampf(float value, float low, float high) {
    return std::max(low, std::min(high, value));
}

}  // namespace hzb
