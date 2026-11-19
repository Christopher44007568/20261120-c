#pragma once

#include "vec.h"

#include <cmath>
#include <limits>
#include <vector>

struct Material {
    Vec3 albedo{0.6, 0.6, 0.6};
    Vec3 emission{0.0, 0.0, 0.0};
};

struct Hit {
    double t = std::numeric_limits<double>::infinity();
    Vec3 position;
    Vec3 normal;
    Material material;
    int objectId = -1;
};

struct Sphere {
    Vec3 center;
    double radius;
    Material material;
    int objectId;
};

struct Box {
    Vec3 minimum;
    Vec3 maximum;
    Material material;
    int objectId;
};

struct Plane {
    Vec3 normal;
    double offset;
    Material material;
    int objectId;
};

inline bool intersectSphere(const Ray& ray, const Sphere& sphere, double tMin, double tMax, Hit& hit) {
    const Vec3 oc = ray.origin - sphere.center;
    const double a = dot(ray.direction, ray.direction);
    const double halfB = dot(oc, ray.direction);
    const double c = dot(oc, oc) - sphere.radius * sphere.radius;
    const double discriminant = halfB * halfB - a * c;
    if (discriminant < 0.0) {
        return false;
    }
    const double root = std::sqrt(discriminant);
    double t = (-halfB - root) / a;
    if (t < tMin) {
        t = (-halfB + root) / a;
    }
    if (t < tMin || t >= tMax) {
        return false;
    }
    hit.t = t;
    hit.position = ray.origin + ray.direction * t;
    hit.normal = normalize(hit.position - sphere.center);
    hit.material = sphere.material;
    hit.objectId = sphere.objectId;
    return true;
}

inline bool intersectBox(const Ray& ray, const Box& box, double tMin, double tMax, Hit& hit) {
    double nearT = tMin;
    double farT = tMax;
    int nearAxis = -1;
    for (int axis = 0; axis < 3; ++axis) {
        const double origin = axis == 0 ? ray.origin.x : (axis == 1 ? ray.origin.y : ray.origin.z);
        const double direction =
            axis == 0 ? ray.direction.x : (axis == 1 ? ray.direction.y : ray.direction.z);
        const double lo = axis == 0 ? box.minimum.x : (axis == 1 ? box.minimum.y : box.minimum.z);
        const double hi = axis == 0 ? box.maximum.x : (axis == 1 ? box.maximum.y : box.maximum.z);
        if (std::abs(direction) < 1e-12) {
            if (origin < lo || origin > hi) {
                return false;
            }
            continue;
        }
        double t0 = (lo - origin) / direction;
        double t1 = (hi - origin) / direction;
        if (t0 > t1) {
            std::swap(t0, t1);
        }
        if (t0 > nearT) {
            nearT = t0;
            nearAxis = axis;
        }
        farT = std::min(farT, t1);
        if (nearT > farT) {
            return false;
        }
    }
    if (nearAxis < 0 || nearT < tMin || nearT >= tMax) {
        return false;
    }
    hit.t = nearT;
    hit.position = ray.origin + ray.direction * nearT;
    hit.normal = Vec3(
        nearAxis == 0 ? (ray.direction.x > 0.0 ? -1.0 : 1.0) : 0.0,
        nearAxis == 1 ? (ray.direction.y > 0.0 ? -1.0 : 1.0) : 0.0,
        nearAxis == 2 ? (ray.direction.z > 0.0 ? -1.0 : 1.0) : 0.0);
    hit.material = box.material;
    hit.objectId = box.objectId;
    return true;
}

inline bool intersectPlane(const Ray& ray, const Plane& plane, double tMin, double tMax, Hit& hit) {
    const double denominator = dot(ray.direction, plane.normal);
    if (std::abs(denominator) < 1e-12) {
        return false;
    }
    const double t = (plane.offset - dot(ray.origin, plane.normal)) / denominator;
    if (t < tMin || t >= tMax) {
        return false;
    }
    hit.t = t;
    hit.position = ray.origin + ray.direction * t;
    hit.normal = denominator < 0.0 ? plane.normal : -plane.normal;
    hit.material = plane.material;
    hit.objectId = plane.objectId;
    return true;
}

class Scene {
public:
    Scene() {
        planes_.push_back(
            Plane{{0.0, 1.0, 0.0}, 0.0, Material{{0.0, 0.0, 0.0}}, 0});
        planes_.push_back(
            Plane{{0.0, 0.0, 1.0}, -4.5, Material{{0.38, 0.41, 0.48}}, 1});

        boxes_.push_back(Box{{-1.65, 0.0, -0.95}, {-0.55, 1.30, 0.15},
                             Material{{0.68, 0.16, 0.11}}, 20});
        boxes_.push_back(Box{{0.75, 0.0, -1.80}, {1.70, 1.85, -0.85},
                             Material{{0.13, 0.48, 0.18}}, 21});
        boxes_.push_back(Box{{1.25, 0.0, 1.05}, {1.90, 0.55, 1.70},
                             Material{{0.72, 0.55, 0.18}}, 22});

        spheres_.push_back(Sphere{{0.05, 0.72, 0.58}, 0.72,
                                  Material{{0.22, 0.36, 0.72}}, 30});
        spheres_.push_back(Sphere{{-2.15, 0.62, 0.85}, 0.62,
                                  Material{{0.74, 0.48, 0.19}}, 31});

        light_.center = {2.25, 3.35, 0.25};
        light_.radius = 0.38;
        light_.material.emission = {22.0, 16.0, 10.0};
        light_.objectId = 99;
    }

    bool intersect(const Ray& ray, double tMin, double tMax, Hit& hit) const {
        bool found = false;
        Hit candidate;
        for (const Plane& plane : planes_) {
            if (intersectPlane(ray, plane, tMin, found ? hit.t : tMax, candidate)) {
                hit = candidate;
                if (plane.objectId == 0) {
                    const double tile =
                        (static_cast<int>(std::floor(candidate.position.x * 2.0)) +
                         static_cast<int>(std::floor(candidate.position.z * 2.0))) &
                        1;
                    hit.material.albedo = tile ? Vec3(0.56, 0.55, 0.52) : Vec3(0.19, 0.21, 0.24);
                }
                found = true;
            }
        }
        for (const Box& box : boxes_) {
            if (intersectBox(ray, box, tMin, found ? hit.t : tMax, candidate)) {
                hit = candidate;
                found = true;
            }
        }
        for (const Sphere& sphere : spheres_) {
            if (intersectSphere(ray, sphere, tMin, found ? hit.t : tMax, candidate)) {
                hit = candidate;
                found = true;
            }
        }
        if (intersectSphere(ray, light_, tMin, found ? hit.t : tMax, candidate)) {
            hit = candidate;
            found = true;
        }
        return found;
    }

    bool occluded(const Ray& ray, double maxDistance) const {
        Hit hit;
        return intersect(ray, 1e-5, maxDistance, hit);
    }

    Vec3 sky(const Vec3& direction) const {
        const double up = std::clamp(0.5 + 0.5 * direction.y, 0.0, 1.0);
        return Vec3(0.025, 0.045, 0.085) * (0.75 + 0.5 * up);
    }

    const Sphere& light() const { return light_; }

private:
    std::vector<Plane> planes_;
    std::vector<Box> boxes_;
    std::vector<Sphere> spheres_;
    Sphere light_;
};

struct Camera {
    Vec3 position{0.0, 1.55, 5.0};
    Vec3 target{0.0, 1.05, -0.9};
    Vec3 up{0.0, 1.0, 0.0};
    double verticalFovDegrees = 48.0;
    Vec3 forward;
    Vec3 right;
    Vec3 cameraUp;
    double halfHeight;

    void update() {
        forward = normalize(target - position);
        right = normalize(cross(forward, up));
        cameraUp = cross(right, forward);
        halfHeight = std::tan(verticalFovDegrees * 3.14159265358979323846 / 360.0);
    }

    Ray primaryRay(double pixelX, double pixelY, int width, int height) const {
        const double aspect = static_cast<double>(width) / static_cast<double>(height);
        const double ndcX = (2.0 * (pixelX + 0.5) / width - 1.0) * halfHeight * aspect;
        const double ndcY = (1.0 - 2.0 * (pixelY + 0.5) / height) * halfHeight;
        const Vec3 direction = normalize(forward + right * ndcX + cameraUp * ndcY);
        return {position, direction};
    }

    bool project(const Vec3& world, int width, int height, double& pixelX, double& pixelY,
                 double& viewDepth, double& viewX, double& viewY) const {
        const Vec3 relative = world - position;
        viewDepth = dot(relative, forward);
        if (viewDepth <= 1e-5) {
            return false;
        }
        const double aspect = static_cast<double>(width) / static_cast<double>(height);
        viewX = dot(relative, right) / viewDepth;
        viewY = dot(relative, cameraUp) / viewDepth;
        pixelX = (viewX / (halfHeight * aspect) * 0.5 + 0.5) * width - 0.5;
        pixelY = (0.5 - viewY / halfHeight * 0.5) * height - 0.5;
        return true;
    }
};

