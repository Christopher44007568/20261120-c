#pragma once

#include <algorithm>

#include "scene.h"
#include "vec.h"

struct BSDFSample {
    Vec3 wi{};
    Vec3 f{};
    double pdf = 0.0;
    bool delta = false;
    bool valid = false;
};

inline Vec3 evalBSDF(const Material& mat, const Vec3& n, const Vec3& wo,
                     const Vec3& wi) {
    if (mat.type != MaterialType::Diffuse) {
        return {};
    }
    if (dot(n, wo) <= 0.0 || dot(n, wi) <= 0.0) {
        return {};
    }
    return mat.albedo / kPi;
}

inline double pdfBSDF(const Material& mat, const Vec3& n, const Vec3& wo,
                      const Vec3& wi) {
    if (mat.type != MaterialType::Diffuse) {
        return 0.0;
    }
    const double cosTheta = dot(n, wi);
    if (dot(n, wo) <= 0.0 || cosTheta <= 0.0) {
        return 0.0;
    }
    return cosineHemispherePdf(cosTheta);
}

inline BSDFSample sampleBSDF(const Material& mat, const Vec3& n,
                             const Vec3& wo, Rng& rng) {
    BSDFSample s;
    if (mat.type == MaterialType::Diffuse) {
        s.wi = sampleCosineHemisphere(n, rng.uniform(), rng.uniform());
        const double cosTheta = dot(n, s.wi);
        if (cosTheta <= 0.0 || dot(n, wo) <= 0.0) {
            return s;
        }
        s.f = mat.albedo / kPi;
        s.pdf = cosineHemispherePdf(cosTheta);
        s.valid = s.pdf > 0.0;
        return s;
    }
    if (mat.type == MaterialType::Mirror) {
        s.wi = reflected(-wo, n);
        s.f = mat.albedo;
        s.pdf = 1.0;
        s.delta = true;
        s.valid = true;
        return s;
    }
    if (mat.type == MaterialType::Glass) {
        const bool entering = dot(n, wo) > 0.0;
        const Vec3 nn = entering ? n : -n;
        const double cosI = std::clamp(dot(nn, wo), 0.0, 1.0);
        if (cosI <= 0.0) {
            return s;
        }
        const double etaI = entering ? 1.0 : mat.ior;
        const double etaT = entering ? mat.ior : 1.0;
        const double fresnel = fresnelDielectric(cosI, etaI, etaT);
        if (rng.uniform() < fresnel) {
            s.wi = reflected(-wo, nn);
        } else if (!refract(-wo, nn, etaI, etaT, s.wi)) {
            s.wi = reflected(-wo, nn);
        }
        s.f = mat.albedo;
        s.pdf = 1.0;
        s.delta = true;
        s.valid = true;
        return s;
    }
    return s;
}

inline Vec3 emitted(const Material& mat, const Vec3& n, const Vec3& toward) {
    if (mat.type != MaterialType::Emissive) {
        return {};
    }
    return dot(n, toward) > 0.0 ? mat.emission : Vec3{};
}
