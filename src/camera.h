#pragma once

#include <algorithm>
#include <cmath>

#include "vec.h"

struct Camera {
    Vec3 origin{0, 0, 0};
    Vec3 forward{0, 0, 1};
    Vec3 right{1, 0, 0};
    Vec3 up{0, 1, 0};
    double tanHalfFov = 0.5;
    double aspect = 1.0;
    double lensRadius = 0.0;
    double focalDistance = 10.0;
    int width = 1;
    int height = 1;
    double xmin = 0.0, xmax = 0.0, ymin = 0.0, ymax = 0.0;
    double A = 1.0;
    double lensArea = 1.0;

    void init(const Vec3& eye, const Vec3& target, const Vec3& worldUp,
              double fovDegrees, int w, int h, double lensR = 0.0,
              double focus = 10.0) {
        origin = eye;
        forward = normalize(target - eye);
        right = normalize(cross(forward, worldUp));
        up = cross(right, forward);
        tanHalfFov = std::tan(0.5 * fovDegrees * kPi / 180.0);
        aspect = static_cast<double>(w) / static_cast<double>(h);
        width = w;
        height = h;
        lensRadius = lensR;
        focalDistance = focus;
        xmin = -tanHalfFov * aspect;
        xmax = tanHalfFov * aspect;
        ymin = -tanHalfFov;
        ymax = tanHalfFov;
        A = (xmax - xmin) * (ymax - ymin);
        lensArea = lensRadius > 0.0 ? kPi * lensRadius * lensRadius : 1.0;
    }

    Vec3 toWorld(const Vec3& local) const {
        return origin + right * local.x + up * local.y + forward * local.z;
    }

    Vec3 toLocalVector(const Vec3& v) const {
        return {dot(v, right), dot(v, up), dot(v, forward)};
    }

    Vec3 cameraPoint(double px, double py) const {
        const double x = xmin + (xmax - xmin) * px / static_cast<double>(width);
        const double y = ymax - (ymax - ymin) * py / static_cast<double>(height);
        return {x, y, 1.0};
    }

    Vec3 lensPoint(const Vec3& lensSample) const {
        if (lensRadius <= 0.0) {
            return toWorld(Vec3{});
        }
        return toWorld({lensSample.x * lensRadius, lensSample.y * lensRadius,
                        0.0});
    }

    bool rasterFromCameraPoint(const Vec3& pc, double& px, double& py) const {
        if (pc.z == 0.0) {
            return false;
        }
        const double x = pc.x / pc.z;
        const double y = pc.y / pc.z;
        px = (x - xmin) / (xmax - xmin) * static_cast<double>(width);
        py = (ymax - y) / (ymax - ymin) * static_cast<double>(height);
        return px >= 0.0 && px < static_cast<double>(width) && py >= 0.0 &&
               py < static_cast<double>(height);
    }

    Ray generateRay(double px, double py, const Vec3& lensSample) const {
        const Vec3 pCamera = cameraPoint(px, py);
        const Vec3 dirCamera = normalize(pCamera);
        Vec3 oLocal{};
        Vec3 dLocal = dirCamera;
        if (lensRadius > 0.0) {
            oLocal = {lensSample.x * lensRadius, lensSample.y * lensRadius, 0.0};
            const Vec3 pFocus = dirCamera * (focalDistance / dirCamera.z);
            dLocal = normalize(pFocus - oLocal);
        }
        return {toWorld(oLocal), normalize(toWorld(dLocal) - toWorld(Vec3{})), 0.0,
                kInf};
    }

    Vec3 toLocalRayOrigin(const Ray& ray) const {
        return toLocalVector(ray.o - origin);
    }

    Vec3 we(const Ray& ray, double* rasterX = nullptr,
            double* rasterY = nullptr) const {
        const Vec3 dLocal = toLocalVector(ray.d);
        const double cosTheta = dLocal.z;
        if (cosTheta <= 0.0) {
            return {};
        }
        const Vec3 oLocal = toLocalRayOrigin(ray);
        const double zPlane = (lensRadius > 0.0 ? focalDistance : 1.0) / cosTheta;
        const Vec3 pFocus = oLocal + dLocal * zPlane;
        double px = 0.0, py = 0.0;
        if (!rasterFromCameraPoint(pFocus, px, py)) {
            return {};
        }
        if (rasterX) {
            *rasterX = px;
        }
        if (rasterY) {
            *rasterY = py;
        }
        const double c2 = cosTheta * cosTheta;
        return Vec3{1.0 / (A * lensArea * c2 * c2), 1.0 / (A * lensArea * c2 * c2),
                    1.0 / (A * lensArea * c2 * c2)};
    }

    void pdfWe(const Ray& ray, double& pdfPos, double& pdfDir) const {
        const Vec3 dLocal = toLocalVector(ray.d);
        const double cosTheta = dLocal.z;
        if (cosTheta <= 0.0) {
            pdfPos = pdfDir = 0.0;
            return;
        }
        const Vec3 oLocal = toLocalRayOrigin(ray);
        const double zPlane = (lensRadius > 0.0 ? focalDistance : 1.0) / cosTheta;
        const Vec3 pFocus = oLocal + dLocal * zPlane;
        double px = 0.0, py = 0.0;
        if (!rasterFromCameraPoint(pFocus, px, py)) {
            pdfPos = pdfDir = 0.0;
            return;
        }
        pdfPos = 1.0 / lensArea;
        pdfDir = 1.0 / (A * cosTheta * cosTheta * cosTheta);
    }

    Vec3 sampleWi(const Vec3& ref, const Vec3& lensSample, Vec3& wi,
                  double& pdf, double& rasterX, double& rasterY,
                  bool& visible) const {
        const Vec3 pLens = lensPoint(lensSample);
        const Vec3 toLens = pLens - ref;
        const double dist = length(toLens);
        if (dist <= 0.0) {
            return {};
        }
        wi = toLens / dist;
        const double cosLens = std::abs(dot(wi, forward));
        if (cosLens <= 0.0) {
            return {};
        }
        pdf = (dist * dist) / (cosLens * lensArea);

        Ray cameraRay{pLens, normalize(ref - pLens), 0.0, dist * (1.0 - 1e-9)};
        visible = true;
        const Vec3 weight = we(cameraRay, &rasterX, &rasterY);
        return weight;
    }
};
