#pragma once

#include <cmath>
#include <string>
#include <vector>

#include "vec.h"

enum class MaterialType { Diffuse, Mirror, Glass, Emissive };

struct Material {
    MaterialType type = MaterialType::Diffuse;
    Vec3 albedo{0.8, 0.8, 0.8};
    Vec3 emission{};
    double ior = 1.5;
};

struct Hit {
    double t = kInf;
    Vec3 p{};
    Vec3 n{};
    int primitive = -1;
};

struct Primitive {
    enum class Kind { Quad, Sphere };

    Kind kind = Kind::Quad;
    Material material;
    bool isLight = false;
    Vec3 a{}, b{}, c{}, normal{};
    Vec3 center{};
    double radius = 0.0;

    static Primitive quad(const Vec3& a, const Vec3& b, const Vec3& c,
                          const Material& m) {
        Primitive p;
        p.kind = Kind::Quad;
        p.a = a;
        p.b = b;
        p.c = c;
        p.normal = normalize(cross(b - a, c - a));
        p.material = m;
        return p;
    }

    static Primitive sphere(const Vec3& center, double radius,
                            const Material& m) {
        Primitive p;
        p.kind = Kind::Sphere;
        p.center = center;
        p.radius = radius;
        p.material = m;
        return p;
    }

    double area() const {
        if (kind == Kind::Quad) {
            return length(cross(b - a, c - a));
        }
        return 4.0 * kPi * radius * radius;
    }

    bool intersect(const Ray& r, Hit& hit) const {
        if (kind == Kind::Sphere) {
            const Vec3 oc = r.o - center;
            const double A = dot(r.d, r.d);
            const double B = 2.0 * dot(oc, r.d);
            const double C = dot(oc, oc) - radius * radius;
            const double disc = B * B - 4.0 * A * C;
            if (disc <= 0.0) {
                return false;
            }
            const double s = std::sqrt(disc);
            double t = (-B - s) / (2.0 * A);
            if (t < r.tmin || t > r.tmax) {
                t = (-B + s) / (2.0 * A);
            }
            if (t < r.tmin || t > r.tmax) {
                return false;
            }
            hit.t = t;
            hit.p = r.at(t);
            hit.n = normalize(hit.p - center);
            return true;
        }

        const Vec3 e1 = b - a;
        const Vec3 e2 = c - a;
        const Vec3 pvec = cross(r.d, e2);
        const double det = dot(e1, pvec);
        if (std::abs(det) < 1e-10) {
            return false;
        }
        const double invDet = 1.0 / det;
        const Vec3 tvec = r.o - a;
        const double u = dot(tvec, pvec) * invDet;
        if (u < 0.0 || u > 1.0) {
            return false;
        }
        const Vec3 qvec = cross(tvec, e1);
        const double v = dot(r.d, qvec) * invDet;
        if (v < 0.0 || u + v > 1.0) {
            return false;
        }
        const double t = dot(e2, qvec) * invDet;
        if (t < r.tmin || t > r.tmax) {
            return false;
        }
        hit.t = t;
        hit.p = r.at(t);
        hit.n = normal;
        return true;
    }

    Vec3 samplePoint(double u1, double u2) const {
        if (kind == Kind::Quad) {
            return a + (b - a) * u1 + (c - a) * u2;
        }
        const double z = 1.0 - 2.0 * u1;
        const double r = std::sqrt(std::max(0.0, 1.0 - z * z));
        const double phi = 2.0 * kPi * u2;
        return center + Vec3{r * std::cos(phi), z, r * std::sin(phi)} * radius;
    }

    Vec3 sampleNormal(const Hit& h) const {
        return kind == Kind::Sphere ? normalize(h.p - center) : normal;
    }
};

struct Scene {
    std::string name;
    std::vector<Primitive> primitives;
    std::vector<int> lights;
    Vec3 background{};

    void add(Primitive p) {
        if (p.material.type == MaterialType::Emissive) {
            p.isLight = true;
            lights.push_back(static_cast<int>(primitives.size()));
        }
        primitives.push_back(std::move(p));
    }

    bool intersect(const Ray& ray, Hit& hit) const {
        hit.t = ray.tmax;
        bool found = false;
        for (size_t i = 0; i < primitives.size(); ++i) {
            Hit h;
            h.t = hit.t;
            if (primitives[i].intersect(ray, h)) {
                hit = h;
                hit.primitive = static_cast<int>(i);
                found = true;
            }
        }
        return found;
    }

    bool visible(const Vec3& a, const Vec3& b) const {
        Vec3 d = b - a;
        const double dist = length(d);
        if (dist < 1e-9) {
            return true;
        }
        d = d / dist;
        Ray ray{a + d * 1e-6, d, 0.0, dist - 1e-6};
        Hit h;
        return !intersect(ray, h);
    }
};

inline Material diffuse(const Vec3& albedo) {
    Material m;
    m.type = MaterialType::Diffuse;
    m.albedo = albedo;
    return m;
}

inline Material mirror(const Vec3& tint = Vec3{1, 1, 1}) {
    Material m;
    m.type = MaterialType::Mirror;
    m.albedo = tint;
    return m;
}

inline Material glass(double ior = 1.5) {
    Material m;
    m.type = MaterialType::Glass;
    m.albedo = {1, 1, 1};
    m.ior = ior;
    return m;
}

inline Material emissive(const Vec3& radiance) {
    Material m;
    m.type = MaterialType::Emissive;
    m.emission = radiance;
    return m;
}
