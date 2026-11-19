#pragma once

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

#include "camera.h"
#include "integrators.h"
#include "scene.h"
#include "shading.h"
#include "vec.h"

enum class VertexType { Camera, Light, Surface };

struct Vertex {
    VertexType type = VertexType::Surface;
    const Camera* camera = nullptr;
    Vec3 p{};
    Vec3 n{};
    Vec3 wo{};
    Vec3 beta{1, 1, 1};
    Material material;
    bool delta = false;
    double pdfFwd = 0.0;
    double pdfRev = 0.0;

    bool onSurface() const { return type != VertexType::Camera; }
    bool isLight() const { return type == VertexType::Light; }
    bool connectible() const {
        return type == VertexType::Surface && !delta;
    }

    Vec3 f(const Vertex& next) const {
        if (!connectible()) {
            return {};
        }
        const Vec3 wi = normalize(next.p - p);
        return evalBSDF(material, n, wo, wi);
    }

    double convertDensity(double pdf, const Vertex& next) const {
        if (!next.onSurface()) {
            return pdf;
        }
        const Vec3 w = next.p - p;
        const double dist2 = lengthSquared(w);
        if (dist2 <= 0.0) {
            return 0.0;
        }
        const double cosNext = std::abs(dot(next.n, w / std::sqrt(dist2)));
        if (cosNext <= 0.0) {
            return 0.0;
        }
        return pdf * cosNext / dist2;
    }

    double pdfLight(const Scene& scene, const Vertex& v,
                    double pdfChoice) const {
        (void)scene;
        if (type != VertexType::Light) {
            return 0.0;
        }
        Vec3 w = v.p - p;
        const double dist2 = lengthSquared(w);
        if (dist2 <= 0.0) {
            return 0.0;
        }
        w = w / std::sqrt(dist2);
        const double cosLight = dot(n, w);
        if (cosLight <= 0.0) {
            return 0.0;
        }
        double pdf = (cosLight / kPi) / dist2;
        if (v.onSurface()) {
            const double cosV = std::abs(dot(v.n, w));
            pdf *= cosV;
        }
        return pdf * pdfChoice;
    }

    double pdfLightOrigin(double pdfChoice) const {
        if (type != VertexType::Light) {
            return 0.0;
        }
        const Scene* scene = sceneRef;
        if (!scene || scene->lights.empty()) {
            return 0.0;
        }
        const Primitive& light = scene->primitives[scene->lights[0]];
        return pdfChoice / light.area();
    }

    const Scene* sceneRef = nullptr;

    double pdf(const Vertex* prev, const Vertex& next,
               double lightPdfChoice) const {
        if (type == VertexType::Camera) {
            if (!camera) {
                return 0.0;
            }
            Ray ray{p, normalize(next.p - p), 0.0, kInf};
            double pdfPos = 0.0, pdfDir = 0.0;
            camera->pdfWe(ray, pdfPos, pdfDir);
            return convertDensity(pdfDir, next);
        }
        if (type == VertexType::Light) {
            return pdfLight(*sceneRef, next, lightPdfChoice);
        }
        if (delta) {
            return 0.0;
        }
        Vec3 wi = next.p - p;
        if (lengthSquared(wi) <= 0.0) {
            return 0.0;
        }
        wi = normalize(wi);
        Vec3 incoming = wo;
        if (prev) {
            incoming = prev->p - p;
            if (lengthSquared(incoming) <= 0.0) {
                return 0.0;
            }
            incoming = normalize(incoming);
        }
        const double pdir = pdfBSDF(material, n, incoming, wi);
        return convertDensity(pdir, next);
    }

    Vec3 Le(const Vertex& prev) const {
        if (type != VertexType::Light) {
            return {};
        }
        Vec3 toward = prev.p - p;
        if (lengthSquared(toward) <= 0.0) {
            return {};
        }
        return emitted(material, n, normalize(toward));
    }
};

inline double geometryTerm(const Scene& scene, const Vertex& a,
                           const Vertex& b) {
    Vec3 d = b.p - a.p;
    const double dist2 = lengthSquared(d);
    if (dist2 <= 0.0) {
        return 0.0;
    }
    d = d / std::sqrt(dist2);
    double g = 1.0 / dist2;
    if (a.onSurface()) {
        g *= std::abs(dot(a.n, d));
    }
    if (b.onSurface()) {
        g *= std::abs(dot(b.n, -d));
    }
    if (g <= 0.0 || !scene.visible(a.p, b.p)) {
        return 0.0;
    }
    return g;
}

inline void generateCameraSubpath(const Scene& scene, const Camera& camera,
                                  double pixelX, double pixelY, Rng& rng,
                                  int maxDepth,
                                  std::vector<Vertex>& path) {
    path.clear();
    Vertex start;
    start.type = VertexType::Camera;
    start.camera = &camera;
    start.p = camera.origin;
    start.n = camera.forward;
    start.beta = {1, 1, 1};
    path.push_back(start);

    Ray ray = camera.generateRay(pixelX + rng.uniform(),
                                 pixelY + rng.uniform(), rng.sampleDisk());
    double pdfPos = 0.0, pdfDir = 0.0;
    camera.pdfWe(ray, pdfPos, pdfDir);
    if (!(pdfDir > 0.0)) {
        return;
    }

    double pdfFwd = pdfDir;
    double pdfRev = 0.0;
    Vec3 beta{1, 1, 1};

    for (int bounce = 0; bounce < maxDepth; ++bounce) {
        Hit hit;
        if (!scene.intersect(ray, hit)) {
            break;
        }
        const Primitive& prim = scene.primitives[hit.primitive];
        const Vec3 wo = -ray.d;

        Vertex v;
        v.p = hit.p;
        v.beta = beta;
        v.material = prim.material;
        v.sceneRef = &scene;

        if (prim.material.type == MaterialType::Emissive) {
            v.type = VertexType::Light;
            v.n = prim.normal;
            v.pdfFwd = path.back().convertDensity(pdfFwd, v);
            path.push_back(v);
            break;
        }

        const bool isGlass = prim.material.type == MaterialType::Glass;
        const Vec3 shadeN = isGlass ? hit.n : faceForward(hit.n, wo);
        v.type = VertexType::Surface;
        v.n = shadeN;
        v.wo = wo;
        v.pdfFwd = path.back().convertDensity(pdfFwd, v);
        path.push_back(v);
        const size_t current = path.size() - 1;

        BSDFSample bs = sampleBSDF(prim.material, shadeN, wo, rng);
        if (!bs.valid || bs.pdf <= 0.0 || isBlack(bs.f)) {
            break;
        }
        const double cosTheta = std::abs(dot(shadeN, bs.wi));
        beta *= bs.f * (cosTheta / bs.pdf);
        if (!isFinite(beta) || maxComponent(beta) <= 0.0) {
            break;
        }

        path[current].delta = bs.delta;
        pdfFwd = bs.delta ? 0.0 : bs.pdf;
        pdfRev = bs.delta ? 0.0 : bs.pdf;
        path[current - 1].pdfRev =
            path[current].convertDensity(pdfRev, path[current - 1]);
        ray = {hit.p + bs.wi * 1e-5, bs.wi, 0.0, kInf};
    }
}

inline void generateLightSubpath(const Scene& scene, Rng& rng, int maxDepth,
                                 std::vector<Vertex>& path) {
    path.clear();
    if (scene.lights.empty()) {
        return;
    }
    const double pdfChoice = 1.0 / static_cast<double>(scene.lights.size());
    const int li = scene.lights[static_cast<size_t>(
        std::min<int>(static_cast<int>(scene.lights.size() - 1),
                      static_cast<int>(rng.uniform() * scene.lights.size())))];
    const Primitive& light = scene.primitives[li];

    const Vec3 p = light.samplePoint(rng.uniform(), rng.uniform());
    const Vec3 n = light.normal;
    const Vec3 dir = sampleCosineHemisphere(n, rng.uniform(), rng.uniform());
    const double cosOut = dot(n, dir);
    const double pdfPos = 1.0 / light.area();
    const double pdfDir = cosineHemispherePdf(cosOut);
    if (pdfDir <= 0.0) {
        return;
    }

    Vertex start;
    start.type = VertexType::Light;
    start.p = p;
    start.n = n;
    start.material = light.material;
    start.sceneRef = &scene;
    start.beta = light.material.emission *
                 (cosOut / (pdfChoice * pdfPos * pdfDir));
    start.pdfFwd = pdfChoice * pdfPos;
    path.push_back(start);

    double pdfFwd = pdfDir;
    Vec3 beta = start.beta;
    Ray ray{p + dir * 1e-5, dir, 0.0, kInf};

    for (int bounce = 0; bounce < maxDepth; ++bounce) {
        Hit hit;
        if (!scene.intersect(ray, hit)) {
            break;
        }
        const Primitive& prim = scene.primitives[hit.primitive];
        if (prim.material.type == MaterialType::Emissive) {
            break;
        }
        const Vec3 wo = -ray.d;
        const bool isGlass = prim.material.type == MaterialType::Glass;
        const Vec3 shadeN = isGlass ? hit.n : faceForward(hit.n, wo);

        Vertex v;
        v.type = VertexType::Surface;
        v.p = hit.p;
        v.n = shadeN;
        v.wo = wo;
        v.beta = beta;
        v.material = prim.material;
        v.sceneRef = &scene;
        v.pdfFwd = path.back().convertDensity(pdfFwd, v);
        path.push_back(v);
        const size_t current = path.size() - 1;

        BSDFSample bs = sampleBSDF(prim.material, shadeN, wo, rng);
        if (!bs.valid || bs.pdf <= 0.0 || isBlack(bs.f)) {
            break;
        }
        const double cosTheta = std::abs(dot(shadeN, bs.wi));
        beta *= bs.f * (cosTheta / bs.pdf);
        if (!isFinite(beta) || maxComponent(beta) <= 0.0) {
            break;
        }

        path[current].delta = bs.delta;
        pdfFwd = bs.delta ? 0.0 : bs.pdf;
        const double pdfRev = bs.delta ? 0.0 : bs.pdf;
        path[current - 1].pdfRev =
            path[current].convertDensity(pdfRev, path[current - 1]);
        ray = {hit.p + bs.wi * 1e-5, bs.wi, 0.0, kInf};
    }
}

inline double bdptMisWeight(const Scene& scene, std::vector<Vertex>& light,
                            std::vector<Vertex>& eye, Vertex& sampled, int s,
                            int t, double pdfChoice) {
    if (s + t == 2) {
        return 1.0;
    }

    Vertex* qs = s == 1 ? &sampled : (s > 0 ? &light[s - 1] : nullptr);
    Vertex* pt = t == 1 ? &sampled : (t > 0 ? &eye[t - 1] : nullptr);
    Vertex* qsMinus = s > 1 ? &light[s - 2] : nullptr;
    Vertex* ptMinus = t > 1 ? &eye[t - 2] : nullptr;

    struct Saved {
        Vertex* vertex;
        bool delta;
        double pdfRev;
    };
    Saved saved[4];
    int savedCount = 0;
    auto remember = [&](Vertex* v) {
        if (v) {
            saved[savedCount++] = {v, v->delta, v->pdfRev};
        }
    };
    remember(qs);
    remember(pt);
    remember(qsMinus);
    remember(ptMinus);

    if (pt) {
        pt->delta = false;
    }
    if (qs) {
        qs->delta = false;
    }

    if (pt) {
        pt->pdfRev = s > 0 ? qs->pdf(qsMinus, *pt, pdfChoice)
                          : pt->pdfLightOrigin(pdfChoice);
    }
    if (ptMinus) {
        ptMinus->pdfRev = s > 0
                              ? pt->pdf(qs, *ptMinus, pdfChoice)
                              : pt->pdfLight(scene, *ptMinus, pdfChoice);
    }
    if (qs) {
        qs->pdfRev = pt ? pt->pdf(ptMinus, *qs, pdfChoice) : 0.0;
    }
    if (qsMinus) {
        qsMinus->pdfRev = qs->pdf(pt, *qsMinus, pdfChoice);
    }

    auto remap0 = [](double f) { return f != 0.0 ? f : 1.0; };
    double sumRi = 0.0;
    double ri = 1.0;
    for (int i = t - 1; i > 0; --i) {
        ri *= remap0(eye[i].pdfRev) / remap0(eye[i].pdfFwd);
        if (!eye[i].delta && !eye[i - 1].delta) {
            sumRi += ri;
        }
    }

    static const bool debugMis = std::getenv("RPT_DEBUG_MIS") != nullptr;
    ri = 1.0;
    for (int i = s - 1; i >= 0; --i) {
        ri *= remap0(light[i].pdfRev) / remap0(light[i].pdfFwd);
        if (debugMis) {
            std::fprintf(stderr,
                         "      L%d rev=%.6g fwd=%.6g ri=%.6g delta=%d\n", i,
                         light[i].pdfRev, light[i].pdfFwd, ri,
                         light[i].delta ? 1 : 0);
        }
        const bool deltaLightOrigin = i > 0 ? light[i - 1].delta : false;
        if (!light[i].delta && !deltaLightOrigin) {
            sumRi += ri;
        }
    }

    for (int i = 0; i < savedCount; ++i) {
        saved[i].vertex->delta = saved[i].delta;
        saved[i].vertex->pdfRev = saved[i].pdfRev;
    }
    (void)scene;
    if (debugMis) {
        std::fprintf(stderr, "    MIS s=%d t=%d sumRi=%.6g\n", s, t, sumRi);
    }
    return 1.0 / (1.0 + sumRi);
}

struct ConnectionResult {
    Vec3 L{};
    double misWeight = 0.0;
    double rasterX = -1.0;
    double rasterY = -1.0;
    bool splat = false;
};

inline ConnectionResult connectBDPT(const Scene& scene, const Camera& camera,
                                    std::vector<Vertex>& light,
                                    std::vector<Vertex>& eye, int s,
                                    int t, Rng& rng, double pdfChoice) {
    ConnectionResult result;
    if (s < 0 || t < 1 || s > static_cast<int>(light.size()) ||
        t > static_cast<int>(eye.size())) {
        return result;
    }

    Vertex sampled;
    sampled.sceneRef = &scene;
    Vec3 L{};

    if (s == 0) {
        const Vertex& pt = eye[t - 1];
        if (pt.isLight() && !isBlack(pt.Le(eye[t - 2]))) {
            L = pt.Le(eye[t - 2]) * pt.beta;
        }
    } else if (t == 1) {
        const Vertex& qs = light[s - 1];
        if (qs.connectible()) {
            const Vec3 lensSample = rng.sampleDisk();
            Vec3 wi{};
            double pdf = 0.0;
            double rx = 0.0, ry = 0.0;
            bool visibleFlag = false;
            const Vec3 wiWeight =
                camera.sampleWi(qs.p, lensSample, wi, pdf, rx, ry, visibleFlag);
            if (pdf > 0.0 && !isBlack(wiWeight)) {
                sampled.type = VertexType::Camera;
                sampled.camera = &camera;
                sampled.p = camera.lensPoint(lensSample);
                sampled.n = camera.forward;
                sampled.beta = wiWeight / pdf;
                L = qs.beta * qs.f(sampled) * sampled.beta;
                L *= std::abs(dot(wi, qs.n));
                if (!isBlack(L) && !scene.visible(qs.p, sampled.p)) {
                    L = {};
                }
                result.rasterX = rx;
                result.rasterY = ry;
                result.splat = true;
            }
        }
    } else if (s == 1) {
        const Vertex& pt = eye[t - 1];
        if (pt.connectible()) {
            DirectLightSample ls = sampleLight(scene, pt.p, rng);
            if (ls.valid && scene.visible(pt.p, ls.p)) {
                sampled.type = VertexType::Light;
                sampled.p = ls.p;
                sampled.n = ls.n;
                sampled.material.type = MaterialType::Emissive;
                sampled.material.emission = ls.le;
                sampled.beta = ls.le / ls.pdf;
                sampled.pdfFwd = pdfChoice / scene.primitives[
                    scene.lights[0]].area();
                L = pt.beta * pt.f(sampled) * sampled.beta;
                L *= std::abs(dot(ls.wi, pt.n));
            }
        }
    } else {
        const Vertex& qs = light[s - 1];
        const Vertex& pt = eye[t - 1];
        if (qs.connectible() && pt.connectible()) {
            L = qs.beta * qs.f(pt) * pt.f(qs) * pt.beta;
            if (!isBlack(L)) {
                L *= geometryTerm(scene, qs, pt);
            }
        }
    }

    if (isBlack(L) || !isFinite(L)) {
        result.L = {};
        return result;
    }
    result.misWeight =
        bdptMisWeight(scene, light, eye, sampled, s, t, pdfChoice);
    result.L = L * result.misWeight;
    return result;
}

inline void addSplat(std::vector<Vec3>& film, int width, int height, double x,
                     double y, const Vec3& value) {
    if (!(x >= 0.0 && x < width && y >= 0.0 && y < height) ||
        !isFinite(value)) {
        return;
    }
    const double sx = x - 0.5;
    const double sy = y - 0.5;
    const int x0 = static_cast<int>(std::floor(sx));
    const int y0 = static_cast<int>(std::floor(sy));
    const double tx = sx - x0;
    const double ty = sy - y0;
    const double weights[4] = {(1.0 - tx) * (1.0 - ty), tx * (1.0 - ty),
                               (1.0 - tx) * ty, tx * ty};
    const int xs[4] = {x0, x0 + 1, x0, x0 + 1};
    const int ys[4] = {y0, y0, y0 + 1, y0 + 1};
    for (int i = 0; i < 4; ++i) {
        if (xs[i] >= 0 && xs[i] < width && ys[i] >= 0 && ys[i] < height) {
            film[static_cast<size_t>(ys[i] * width + xs[i])] +=
                value * weights[i];
        }
    }
}

inline Vec3 traceBDPT(const Scene& scene, const Camera& camera, int pixelX,
                      int pixelY, Rng& rng, int maxDepth,
                      std::vector<Vec3>& film) {
    thread_local std::vector<Vertex> eye;
    thread_local std::vector<Vertex> light;
    generateCameraSubpath(scene, camera, pixelX, pixelY, rng, maxDepth + 1,
                          eye);
    generateLightSubpath(scene, rng, maxDepth + 1, light);

    const double pdfChoice = 1.0 / static_cast<double>(scene.lights.size());
    Vec3 Lsum{};
    static const bool debugEnabled = std::getenv("RPT_DEBUG") != nullptr;
    static const bool debugAll = std::getenv("RPT_DEBUG_ANY") != nullptr;
    const bool debug =
        debugEnabled &&
        (debugAll || (pixelX == camera.width / 2 &&
                      pixelY == camera.height / 2));
    if (debug) {
        std::fprintf(stderr, "BDPT pixel=(%d,%d) eye=%zu light=%zu\n", pixelX,
                     pixelY, eye.size(), light.size());
    }
    for (int t = 1; t <= static_cast<int>(eye.size()); ++t) {
        for (int s = 0; s <= static_cast<int>(light.size()); ++s) {
            const int depth = s + t - 2;
            if ((s == 1 && t == 1) || depth < 0 || depth > maxDepth) {
                continue;
            }
            ConnectionResult c =
                connectBDPT(scene, camera, light, eye, s, t, rng, pdfChoice);
            if (debug) {
                std::fprintf(stderr, "  s=%d t=%d L=(%.5g %.5g %.5g) w=%.5g\n",
                             s, t, c.L.x, c.L.y, c.L.z, c.misWeight);
            }
            if (isBlack(c.L)) {
                continue;
            }
            if (t == 1) {
                if (c.splat) {
                    addSplat(film, camera.width, camera.height, c.rasterX,
                             c.rasterY, c.L);
                }
            } else {
                Lsum += c.L;
            }
        }
    }
    return Lsum;
}
