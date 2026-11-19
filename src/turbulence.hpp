#pragma once

#include <array>
#include <cstddef>
#include <vector>

namespace hzb {

struct TurbulenceResult {
    int particleCount = 0;
    int steps = 0;
    double dt = 0.0;
    double finalTime = 0.0;
    double meanDivergence = 0.0;
    double maxAbsDivergence = 0.0;
    double initialMeanNearestNeighbor = 0.0;
    double finalMeanNearestNeighbor = 0.0;
    double nearestNeighborRatio = 0.0;
    double initialOccupancyCv = 0.0;
    double finalOccupancyCv = 0.0;
    double occupancyCvRatio = 0.0;
    double finalOccupancyP99OverMedian = 0.0;
    double finalMaxCellOccupancyRatio = 0.0;
    int trackCount = 0;
    int trackSamples = 0;
    std::vector<std::array<float, 3>> tracks;
};

TurbulenceResult runTurbulenceValidation();

}  // namespace hzb
