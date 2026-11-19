#pragma once

#include "renderer.h"

#include <vector>

struct DenoiseParams {
    int spatialRadius = 1;
    double sigmaSpatial = 1.0;
    double sigmaNormal = 0.18;
    double sigmaDepth = 0.018;
    double sigmaColor = 0.11;
    double colorGate = 0.12;
    double maxHistoryWeight = 0.95;
    double fastMotionPixels = 1.25;
    bool guardHistory = true;
};

struct DenoiseStats {
    std::vector<unsigned char> historyMismatch;
    std::vector<unsigned char> geometricMismatch;
    std::vector<unsigned char> photometricMismatch;
    std::vector<unsigned char> fastMotion;
    std::vector<float> historyWeight;
    std::vector<float> screenMotionPixels;
};

class DenoiseState {
public:
    bool hasHistory = false;
    int width = 0;
    int height = 0;
    Camera previousCamera;
    std::vector<Vec3> color;
    std::vector<Vec3> normal;
    std::vector<Vec3> worldPosition;
    std::vector<double> depth;
    std::vector<int> objectId;
    std::vector<float> historyLength;

    void reset();
};

RenderFrame denoiseFrame(const RenderFrame& input, DenoiseState& state, const DenoiseParams& params,
                         DenoiseStats* stats = nullptr);

