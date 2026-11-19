#pragma once

#include "denoiser.h"
#include "renderer.h"

#include <vector>

double mseRgb(const std::vector<Vec3>& a, const std::vector<Vec3>& b);
double mseLuminance(const std::vector<Vec3>& a, const std::vector<Vec3>& b);
double meanAbsoluteLuminanceError(const std::vector<Vec3>& candidate,
                                  const std::vector<Vec3>& reference);
double meanTemporalLuminanceVariance(const std::vector<RenderFrame>& frames);
std::vector<unsigned char> edgeMask(const RenderFrame& guide);
std::vector<unsigned char> ghostMask(const RenderFrame& candidate, const RenderFrame& raw,
                                    const RenderFrame& reference);
double maskRatio(const std::vector<unsigned char>& mask);
double maskedRatio(const std::vector<unsigned char>& numerator,
                   const std::vector<unsigned char>& denominator);
int firstConvergedFrame(const std::vector<double>& errors, double target, int stableFrames);

