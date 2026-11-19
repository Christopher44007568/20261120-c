#pragma once

#include <algorithm>
#include <cmath>

#include "camera.h"
#include "scene.h"
#include "shading.h"
#include "vec.h"

struct DirectLightSample {
    Vec3 p{};
    Vec3 n{};
    Vec3 wi{};
    Vec3 le{};
    double dist = 0.0;
    double pdf = 0.0;
    bool valid = false;
};

inline DirectLightSample sampleLight(const Scene& scene, const Vec3& ref,
                                     Rng& rng) {
    DirectLightSample s;
    if (scene.lights.empty()) {
        return s;
    }
    const int li = scene.lights[static_cast<size_t>(
        std::min<int>(static_cast<int>(scene.lights.size() - 1),
                      static_cast<int>(rng.uniform() * scene.lights.size())))];
    const Primitive& light = scene.primitives[li];
    s.p = light.samplePoint(rng.uniform(), rng.uniform());
    s.n = light.normal;
    Vec3 toLight = s.p - ref;
    s.dist = length(toLight);
    if (s.dist <= 0.0 || dot(s.n, -toLight) <= 0.0) {
        return s;
    }
    s.wi = toLight / s.dist;
    const double cosLight = dot(s.n, -s.wi);
    if (cosLight <= 0.0) {
        return s;
    }
    s.le = light.material.emission;
    const double pdfChoice = 1.0 / static_cast<double>(scene.lights.size());
    s.pdf = pdfChoice * (s.dist * s.dist) / (light.area() * cosLight);
    s.valid = s.pdf > 0.0 && !isBlack(s.le);
    return s;
}

inline double lightPdfAt(const Scene& scene, const Vec3& ref,
                         const Hit& lightHit) {
    if (lightHit.primitive < 0) {
        return 0.0;
    }
    const Primitive& light = scene.primitives[lightHit.primitive];
    if (light.material.type != MaterialType::Emissive) {
        return 0.0;
    }
    Vec3 toLight = lightHit.p - ref;
    const double dist2 = lengthSquared(toLight);
    if (dist2 <= 0.0) {
        return 0.0;
    }
    const double cosLight = dot(light.normal, -normalize(toLight));
    if (cosLight <= 0.0) {
        return 0.0;
    }
    const double pdfChoice = 1.0 / static_cast<double>(scene.lights.size());
    return pdfChoice * dist2 / (light.area() * cosLight);
}

inline double misBalance(double a, double b) {
    if (!(a > 0.0)) {
        return 0.0;
    }
    return a / (a + b);
}

inline Vec3 tracePath(const Scene& scene, const Camera& camera, double pixelX,
                      double pixelY, Rng& rng, int maxDepth) {
    const double filmX = pixelX + rng.uniform();
    const double filmY = pixelY + rng.uniform();
    Ray ray = camera.generateRay(filmX, filmY, rng.sampleDisk());

    Vec3 radiance{};
    Vec3 throughput{1, 1, 1};
    double prevPdf = 0.0;
    bool prevDelta = false;

    for (int depth = 0; depth < maxDepth; ++depth) {
        Hit hit;
        if (!scene.intersect(ray, hit)) {
            break;
        }
        const Primitive& prim = scene.primitives[hit.primitive];
        if (prim.material.type == MaterialType::Emissive) {
            const Vec3 le = emitted(prim.material, prim.normal, -ray.d);
            if (!isBlack(le)) {
                double weight = 1.0;
                if (depth > 0 && !prevDelta) {
                    const double pLight = lightPdfAt(scene, ray.o, hit);
                    weight = misBalance(prevPdf, pLight);
                }
                radiance += throughput * le * weight;
            }
            break;
        }

        const Material& mat = prim.material;
        const Vec3 wo = -ray.d;
        const bool glass = mat.type == MaterialType::Glass;
        const Vec3 n = glass ? hit.n : faceForward(hit.n, wo);
        if (dot(n, wo) <= 0.0) {
            break;
        }

        if (mat.type == MaterialType::Diffuse) {
            DirectLightSample ls = sampleLight(scene, hit.p, rng);
            if (ls.valid && scene.visible(hit.p, ls.p)) {
                const double cosSurface = std::max(0.0, dot(n, ls.wi));
                const Vec3 f = evalBSDF(mat, n, wo, ls.wi);
                const double pBsdf = pdfBSDF(mat, n, wo, ls.wi);
                const double weight = misBalance(ls.pdf, pBsdf);
                if (cosSurface > 0.0 && weight > 0.0) {
                    radiance += throughput * f * ls.le *
                                (cosSurface * weight / ls.pdf);
                }
            }
        }

        BSDFSample bs = sampleBSDF(mat, n, wo, rng);
        if (!bs.valid || isBlack(bs.f) || bs.pdf <= 0.0) {
            break;
        }
        const double cosTheta = std::abs(dot(n, bs.wi));
        throughput *= bs.f * (cosTheta / bs.pdf);
        prevDelta = bs.delta;
        prevPdf = bs.delta ? 0.0 : bs.pdf;
        if (maxComponent(throughput) <= 0.0 || !isFinite(throughput)) {
            break;
        }
        ray = {hit.p + bs.wi * 1e-5, bs.wi, 0.0, kInf};
    }
    return radiance;
}
