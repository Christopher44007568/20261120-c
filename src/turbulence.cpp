#include "turbulence.hpp"

#include "math.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <vector>

namespace hzb {
namespace {

constexpr double kTwoPi = 6.28318530717958647692;
constexpr double kA = 1.0;
constexpr double kB = 0.82;
constexpr double kC = 0.64;
constexpr double kOmega = 0.17;
constexpr int kParticleCount = 16384;
constexpr int kSteps = 600;
constexpr double kDt = 0.008;
constexpr int kGridSize = 19;
constexpr int kTrackCount = 64;
constexpr int kTrackEvery = 3;

class Rng {
public:
    explicit Rng(std::uint64_t seed) : state_(seed) {}

    std::uint64_t next() {
        state_ += 0x9E3779B97F4A7C15ULL;
        std::uint64_t value = state_;
        value = (value ^ (value >> 30)) * 0xBF58476D1CE4E5B9ULL;
        value = (value ^ (value >> 27)) * 0x94D049BB133111EBULL;
        return value ^ (value >> 31);
    }

    double unit() {
        return static_cast<double>(next() >> 11) * (1.0 / 9007199254740992.0);
    }

private:
    std::uint64_t state_;
};

struct Particle {
    double x;
    double y;
    double z;
};

struct Vec3d {
    double x;
    double y;
    double z;
};

double wrapCoordinate(double value) {
    value = std::fmod(value, kTwoPi);
    return value < 0.0 ? value + kTwoPi : value;
}

Vec3d abcVelocity(const Vec3d& point, double time) {
    const double phase = kOmega * time;
    return {
        kA * std::sin(point.z + phase) + kC * std::cos(point.y),
        kB * std::sin(point.x + phase) + kA * std::cos(point.z),
        kC * std::sin(point.y + phase) + kB * std::cos(point.x),
    };
}

Particle integrateRk4(const Particle& particle, double time) {
    const Vec3d p{particle.x, particle.y, particle.z};
    const Vec3d k1 = abcVelocity(p, time);
    const Vec3d k2 = abcVelocity({p.x + 0.5 * kDt * k1.x,
                                  p.y + 0.5 * kDt * k1.y,
                                  p.z + 0.5 * kDt * k1.z},
                                 time + 0.5 * kDt);
    const Vec3d k3 = abcVelocity({p.x + 0.5 * kDt * k2.x,
                                  p.y + 0.5 * kDt * k2.y,
                                  p.z + 0.5 * kDt * k2.z},
                                 time + 0.5 * kDt);
    const Vec3d k4 = abcVelocity({p.x + kDt * k3.x,
                                  p.y + kDt * k3.y,
                                  p.z + kDt * k3.z},
                                 time + kDt);
    return {
        wrapCoordinate(p.x + (kDt / 6.0) * (k1.x + 2.0 * k2.x + 2.0 * k3.x + k4.x)),
        wrapCoordinate(p.y + (kDt / 6.0) * (k1.y + 2.0 * k2.y + 2.0 * k3.y + k4.y)),
        wrapCoordinate(p.z + (kDt / 6.0) * (k1.z + 2.0 * k2.z + 2.0 * k3.z + k4.z)),
    };
}

double periodicDelta(double value) {
    value = std::fmod(std::abs(value), kTwoPi);
    return std::min(value, kTwoPi - value);
}

int wrapCell(int value) {
    return (value + kGridSize) % kGridSize;
}

struct OccupancyStats {
    double meanNearestNeighbor = 0.0;
    double occupancyCv = 0.0;
    double p99OverMedian = 0.0;
    double maxOverMean = 0.0;
};

OccupancyStats measureDistribution(const std::vector<Particle>& particles) {
    const int cellCount = kGridSize * kGridSize * kGridSize;
    std::vector<int> counts(static_cast<std::size_t>(cellCount), 0);
    for (std::size_t index = 0; index < particles.size(); ++index) {
        const int cx = static_cast<int>(particles[index].x / kTwoPi * kGridSize);
        const int cy = static_cast<int>(particles[index].y / kTwoPi * kGridSize);
        const int cz = static_cast<int>(particles[index].z / kTwoPi * kGridSize);
        const int cell = wrapCell(cx) +
                         kGridSize * (wrapCell(cy) + kGridSize * wrapCell(cz));
        ++counts[static_cast<std::size_t>(cell)];
    }

    std::vector<int> starts(static_cast<std::size_t>(cellCount + 1), 0);
    for (int cell = 0; cell < cellCount; ++cell) {
        starts[static_cast<std::size_t>(cell + 1)] =
            starts[static_cast<std::size_t>(cell)] + counts[static_cast<std::size_t>(cell)];
    }
    std::vector<int> writeCursor(starts.begin(), starts.end() - 1);
    std::vector<int> particlesByCell(particles.size(), 0);
    for (std::size_t index = 0; index < particles.size(); ++index) {
        const int cx = static_cast<int>(particles[index].x / kTwoPi * kGridSize);
        const int cy = static_cast<int>(particles[index].y / kTwoPi * kGridSize);
        const int cz = static_cast<int>(particles[index].z / kTwoPi * kGridSize);
        const int cell = wrapCell(cx) +
                         kGridSize * (wrapCell(cy) + kGridSize * wrapCell(cz));
        const int slot = writeCursor[static_cast<std::size_t>(cell)]++;
        particlesByCell[static_cast<std::size_t>(slot)] = static_cast<int>(index);
    }

    double nearestSum = 0.0;
    for (std::size_t index = 0; index < particles.size(); ++index) {
        const int cx = wrapCell(static_cast<int>(particles[index].x / kTwoPi * kGridSize));
        const int cy = wrapCell(static_cast<int>(particles[index].y / kTwoPi * kGridSize));
        const int cz = wrapCell(static_cast<int>(particles[index].z / kTwoPi * kGridSize));
        double bestSquared = std::numeric_limits<double>::max();
        for (int dz = -1; dz <= 1; ++dz) {
            for (int dy = -1; dy <= 1; ++dy) {
                for (int dx = -1; dx <= 1; ++dx) {
                    const int neighborCell = wrapCell(cx + dx) +
                                             kGridSize * (wrapCell(cy + dy) +
                                                          kGridSize * wrapCell(cz + dz));
                    const int begin = starts[static_cast<std::size_t>(neighborCell)];
                    const int end = starts[static_cast<std::size_t>(neighborCell + 1)];
                    for (int cursor = begin; cursor < end; ++cursor) {
                        const int other = particlesByCell[static_cast<std::size_t>(cursor)];
                        if (other == static_cast<int>(index)) {
                            continue;
                        }
                        const double deltaX =
                            periodicDelta(particles[index].x - particles[other].x);
                        const double deltaY =
                            periodicDelta(particles[index].y - particles[other].y);
                        const double deltaZ =
                            periodicDelta(particles[index].z - particles[other].z);
                        bestSquared = std::min(bestSquared,
                                               deltaX * deltaX + deltaY * deltaY +
                                                   deltaZ * deltaZ);
                    }
                }
            }
        }
        nearestSum += std::sqrt(bestSquared);
    }

    const double meanOccupancy = static_cast<double>(particles.size()) / cellCount;
    double variance = 0.0;
    int maximum = 0;
    for (int count : counts) {
        const double delta = static_cast<double>(count) - meanOccupancy;
        variance += delta * delta;
        maximum = std::max(maximum, count);
    }
    variance /= cellCount;

    std::vector<int> sortedCounts = counts;
    std::sort(sortedCounts.begin(), sortedCounts.end());
    const int median = sortedCounts[static_cast<std::size_t>(cellCount / 2)];
    const int p99Index =
        std::min(cellCount - 1, static_cast<int>(0.99 * static_cast<double>(cellCount)));
    const int p99 = sortedCounts[static_cast<std::size_t>(p99Index)];

    OccupancyStats stats;
    stats.meanNearestNeighbor = nearestSum / static_cast<double>(particles.size());
    stats.occupancyCv = meanOccupancy > 0.0 ? std::sqrt(variance) / meanOccupancy : 0.0;
    stats.p99OverMedian = median > 0 ? static_cast<double>(p99) / median : 0.0;
    stats.maxOverMean =
        meanOccupancy > 0.0 ? static_cast<double>(maximum) / meanOccupancy : 0.0;
    return stats;
}

void measureDivergence(double& meanAbs, double& maxAbs) {
    Rng rng(0xD1A0BEEF12345678ULL);
    constexpr int sampleCount = 4096;
    constexpr double h = 1.0e-5;
    double sum = 0.0;
    double maximum = 0.0;
    for (int sample = 0; sample < sampleCount; ++sample) {
        const Vec3d point{rng.unit() * kTwoPi, rng.unit() * kTwoPi, rng.unit() * kTwoPi};
        const Vec3d xPlus = abcVelocity({point.x + h, point.y, point.z}, 0.0);
        const Vec3d xMinus = abcVelocity({point.x - h, point.y, point.z}, 0.0);
        const Vec3d yPlus = abcVelocity({point.x, point.y + h, point.z}, 0.0);
        const Vec3d yMinus = abcVelocity({point.x, point.y - h, point.z}, 0.0);
        const Vec3d zPlus = abcVelocity({point.x, point.y, point.z + h}, 0.0);
        const Vec3d zMinus = abcVelocity({point.x, point.y, point.z - h}, 0.0);
        const double divergence =
            (xPlus.x - xMinus.x + yPlus.y - yMinus.y + zPlus.z - zMinus.z) / (2.0 * h);
        const double magnitude = std::abs(divergence);
        sum += magnitude;
        maximum = std::max(maximum, magnitude);
    }
    meanAbs = sum / sampleCount;
    maxAbs = maximum;
}

}  // namespace

TurbulenceResult runTurbulenceValidation() {
    TurbulenceResult result;
    result.particleCount = kParticleCount;
    result.steps = kSteps;
    result.dt = kDt;
    result.finalTime = kDt * kSteps;
    measureDivergence(result.meanDivergence, result.maxAbsDivergence);

    Rng rng(0x1234ABCD5EED9876ULL);
    std::vector<Particle> particles(static_cast<std::size_t>(kParticleCount));
    for (Particle& particle : particles) {
        particle = {rng.unit() * kTwoPi, rng.unit() * kTwoPi, rng.unit() * kTwoPi};
    }
    const OccupancyStats initial = measureDistribution(particles);

    result.trackCount = kTrackCount;
    result.trackSamples = 1 + kSteps / kTrackEvery;
    result.tracks.reserve(static_cast<std::size_t>(result.trackCount) *
                          static_cast<std::size_t>(result.trackSamples));
    for (int track = 0; track < kTrackCount; ++track) {
        const Particle& particle = particles[static_cast<std::size_t>(track)];
        result.tracks.push_back({static_cast<float>(particle.x),
                                 static_cast<float>(particle.y),
                                 static_cast<float>(particle.z)});
    }

    for (int step = 0; step < kSteps; ++step) {
        const double time = step * kDt;
        for (Particle& particle : particles) {
            particle = integrateRk4(particle, time);
        }
        if ((step + 1) % kTrackEvery == 0) {
            for (int track = 0; track < kTrackCount; ++track) {
                const Particle& particle = particles[static_cast<std::size_t>(track)];
                result.tracks.push_back({static_cast<float>(particle.x),
                                         static_cast<float>(particle.y),
                                         static_cast<float>(particle.z)});
            }
        }
    }

    const OccupancyStats final = measureDistribution(particles);
    result.initialMeanNearestNeighbor = initial.meanNearestNeighbor;
    result.finalMeanNearestNeighbor = final.meanNearestNeighbor;
    result.nearestNeighborRatio =
        initial.meanNearestNeighbor > 0.0
            ? final.meanNearestNeighbor / initial.meanNearestNeighbor
            : 0.0;
    result.initialOccupancyCv = initial.occupancyCv;
    result.finalOccupancyCv = final.occupancyCv;
    result.occupancyCvRatio =
        initial.occupancyCv > 0.0 ? final.occupancyCv / initial.occupancyCv : 0.0;
    result.finalOccupancyP99OverMedian = final.p99OverMedian;
    result.finalMaxCellOccupancyRatio = final.maxOverMean;
    return result;
}

}  // namespace hzb
