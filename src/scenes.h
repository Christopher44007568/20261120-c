#pragma once

#include <string>

#include "scene.h"

inline void addRoom(Scene& scene, double half = 4.0, double height = 4.0,
                    const Vec3& leftColor = {0.55, 0.16, 0.13},
                    const Vec3& rightColor = {0.14, 0.45, 0.18},
                    const Vec3& wallColor = {0.72, 0.72, 0.70}) {
    const Material floorMat = diffuse({0.68, 0.68, 0.66});
    const Material ceilMat = diffuse(wallColor);
    const Material leftMat = diffuse(leftColor);
    const Material rightMat = diffuse(rightColor);
    const Material backMat = diffuse(wallColor);
    const Material frontMat = diffuse(wallColor);

    scene.add(Primitive::quad({-half, 0, -half}, {-half, 0, half},
                              {half, 0, -half}, floorMat));
    scene.add(Primitive::quad({-half, height, -half}, {half, height, -half},
                              {-half, height, half}, ceilMat));
    scene.add(Primitive::quad({-half, 0, -half}, {half, 0, -half},
                              {-half, height, -half}, backMat));
    scene.add(Primitive::quad({half, 0, half}, {-half, 0, half},
                              {half, height, half}, frontMat));
    scene.add(Primitive::quad({-half, 0, half}, {-half, 0, -half},
                              {-half, height, half}, leftMat));
    scene.add(Primitive::quad({half, 0, -half}, {half, 0, half},
                              {half, height, -half}, rightMat));
}

inline void addBox(Scene& scene, const Vec3& lo, const Vec3& hi,
                   const Material& mat) {
    const Vec3 p000{lo.x, lo.y, lo.z};
    const Vec3 p001{lo.x, lo.y, hi.z};
    const Vec3 p010{lo.x, hi.y, lo.z};
    const Vec3 p011{lo.x, hi.y, hi.z};
    const Vec3 p100{hi.x, lo.y, lo.z};
    const Vec3 p101{hi.x, lo.y, hi.z};
    const Vec3 p110{hi.x, hi.y, lo.z};
    const Vec3 p111{hi.x, hi.y, hi.z};
    scene.add(Primitive::quad(p000, p010, p100, mat));
    scene.add(Primitive::quad(p001, p101, p011, mat));
    scene.add(Primitive::quad(p000, p100, p001, mat));
    scene.add(Primitive::quad(p010, p011, p110, mat));
    scene.add(Primitive::quad(p000, p001, p010, mat));
    scene.add(Primitive::quad(p100, p110, p101, mat));
}

inline Scene makeIndirectScene() {
    Scene scene;
    scene.name = "indirect";
    addRoom(scene, 4.0, 4.0, {0.55, 0.16, 0.13}, {0.14, 0.45, 0.18},
            {0.72, 0.72, 0.70});
    scene.add(Primitive::sphere({0.0, 1.05, 0.0}, 1.0,
                                diffuse({0.76, 0.58, 0.34})));
    addBox(scene, {-2.4, 0.0, -2.4}, {-1.2, 2.1, -1.2}, diffuse({0.32, 0.38, 0.78}));
    scene.add(Primitive::quad({-2.65, 3.97, -2.2}, {2.65, 3.97, -2.2},
                              {-2.65, 3.97, 2.2}, emissive({18, 18, 18})));
    scene.background = {};
    return scene;
}

inline Scene makeInteriorScene() {
    Scene scene;
    scene.name = "interior";
    addRoom(scene, 4.2, 4.2, {0.50, 0.18, 0.12}, {0.12, 0.42, 0.20},
            {0.74, 0.72, 0.66});
    addBox(scene, {-3.25, 0.0, -3.25}, {-1.75, 1.6, -1.75},
           diffuse({0.72, 0.42, 0.18}));
    addBox(scene, {1.15, 0.0, -0.7}, {2.75, 2.35, 0.8},
           diffuse({0.18, 0.32, 0.68}));
    scene.add(Primitive::sphere({-0.55, 0.82, 1.25}, 0.82, glass(1.5)));
    scene.add(Primitive::sphere({2.05, 0.48, 2.05}, 0.48, mirror({0.85, 0.9, 0.95})));
    scene.add(Primitive::quad({-2.4, 4.17, -2.4}, {2.4, 4.17, -2.4},
                              {-2.4, 4.17, 2.4}, emissive({21, 20, 18})));
    scene.background = {};
    return scene;
}

inline Scene makeCausticScene() {
    Scene scene;
    scene.name = "caustic";
    addRoom(scene, 4.0, 4.0, {0.48, 0.20, 0.16}, {0.17, 0.40, 0.22},
            {0.68, 0.68, 0.64});
    scene.add(Primitive::sphere({0.0, 1.02, -0.15}, 0.92, glass(1.5)));
    addBox(scene, {-3.5, 0.0, -3.5}, {-2.5, 1.0, -2.5}, diffuse({0.20, 0.24, 0.70}));
    addBox(scene, {2.35, 0.0, -3.2}, {3.35, 1.25, -2.2}, diffuse({0.72, 0.28, 0.12}));
    scene.add(Primitive::quad({-0.75, 3.97, -0.75}, {0.75, 3.97, -0.75},
                              {-0.75, 3.97, 0.75}, emissive({100, 98, 94})));
    scene.background = {};
    return scene;
}

inline Scene makeScene(const std::string& name) {
    if (name == "indirect") {
        return makeIndirectScene();
    }
    if (name == "interior") {
        return makeInteriorScene();
    }
    if (name == "caustic") {
        return makeCausticScene();
    }
    return makeCausticScene();
}

inline Camera makeCamera(const std::string& sceneName, int width, int height) {
    Camera c;
    if (sceneName == "caustic") {
        c.init({0.0, 2.05, 3.72}, {0.0, 0.82, -0.35}, {0, 1, 0}, 56.0,
               width, height, 0.0, 4.2);
    } else if (sceneName == "interior") {
        c.init({0.0, 2.15, 3.78}, {0.0, 1.40, -0.65}, {0, 1, 0}, 62.0,
               width, height, 0.0, 4.8);
    } else {
        c.init({0.0, 2.15, 3.72}, {0.0, 1.40, -0.7}, {0, 1, 0}, 64.0,
               width, height, 0.0, 4.8);
    }
    return c;
}
