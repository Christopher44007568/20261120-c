#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

namespace {

constexpr double kPi = 3.141592653589793238462643383279502884;
constexpr double kHeight = 2.0;
constexpr double kWallX = 2.0;
constexpr double kWallTop = 1.1;
constexpr int kImageWidth = 120;
constexpr int kImageHeight = 64;
constexpr double kXMin = -2.5;
constexpr double kXMax = 6.5;
constexpr double kYMin = -2.5;
constexpr double kYMax = 2.5;
constexpr double kPower = 100.0;
constexpr double kArea = 1.0;
constexpr double kRadiance = kPower / (kPi * kArea);
constexpr double kMeanThreshold = 0.015;
constexpr double kP99Threshold = 0.040;
constexpr double kRmseThreshold = 0.020;
constexpr double kFluxThreshold = 0.005;
constexpr double kWidthThreshold = 0.020;

struct Shape {
    std::string name;
    int index;
    double radius = 0.0;
    double coreLength = 0.0;
    double width = 0.0;
    double height = 0.0;
    double xHalfExtent = 0.0;
};

struct Pixel {
    double x = 0.0;
    double y = 0.0;
    double analytic = 0.0;
    double monteCarlo = 0.0;
    double visible = 0.0;
};

struct Penumbra {
    double umbraEnd = 0.0;
    double penumbraEnd = 0.0;
    double geometricWidth = 0.0;
    double halfLightX = 0.0;
    double analytic05 = 0.0;
    double analytic95 = 0.0;
    double analyticWidth = 0.0;
    double mc05 = 0.0;
    double mc95 = 0.0;
    double mcWidth = 0.0;
    double widthError = 0.0;
};

struct FluxResult {
    double analytic = 0.0;
    double monteCarlo = 0.0;
    double relativeError = 0.0;
};

struct Summary {
    double meanRelative = 0.0;
    double p99Relative = 0.0;
    double normalizedRmse = 0.0;
    double maxNormalized = 0.0;
    double peak = 0.0;
};

class Pcg32 {
public:
    explicit Pcg32(uint64_t seed, uint64_t stream = 0xda3e39cb94b95bdbULL)
        : state_(0U), inc_((stream << 1U) | 1U) {
        nextU32();
        state_ += seed;
        nextU32();
    }

    uint32_t nextU32() {
        const uint64_t old = state_;
        state_ = old * 6364136223846793005ULL + inc_;
        const uint32_t xorshifted =
            static_cast<uint32_t>(((old >> 18U) ^ old) >> 27U);
        const uint32_t rot = static_cast<uint32_t>(old >> 59U);
        return (xorshifted >> rot) | (xorshifted << ((~rot + 1U) & 31U));
    }

    double uniform() {
        return (static_cast<double>(nextU32()) + 0.5) *
               0x1.0p-32;
    }

private:
    uint64_t state_;
    uint64_t inc_;
};

double clamp01(double value) {
    return std::max(0.0, std::min(1.0, value));
}

double pixelX(int ix) {
    return kXMin + (static_cast<double>(ix) + 0.5) *
                       (kXMax - kXMin) / kImageWidth;
}

double pixelY(int iy) {
    return kYMin + (static_cast<double>(iy) + 0.5) *
                       (kYMax - kYMin) / kImageHeight;
}

std::vector<Shape> makeShapes() {
    const double capsuleRadius = 0.25;
    const double capsuleCore =
        (kArea - kPi * capsuleRadius * capsuleRadius) /
        (2.0 * capsuleRadius);
    const double diskRadius = std::sqrt(kArea / kPi);

    return {
        {"capsule", 0, capsuleRadius, capsuleCore, 0.0, 0.0,
         capsuleCore * 0.5 + capsuleRadius},
        {"disk", 1, diskRadius, 0.0, 0.0, 0.0, diskRadius},
        {"rectangle", 2, 0.0, 0.0, 0.8, 1.25, 0.4},
    };
}

class GaussLegendre {
public:
    explicit GaussLegendre(int count) : nodes_(count), weights_(count) {
        for (int i = 0; i < (count + 1) / 2; ++i) {
            double z = std::cos(kPi * (i + 0.75) / (count + 0.5));
            double derivative = 0.0;
            for (int iteration = 0; iteration < 30; ++iteration) {
                double p0 = 1.0;
                double p1 = z;
                for (int degree = 2; degree <= count; ++degree) {
                    const double p2 =
                        ((2.0 * degree - 1.0) * z * p1 -
                         (degree - 1.0) * p0) /
                        degree;
                    p0 = p1;
                    p1 = p2;
                }
                derivative =
                    count * (z * p1 - p0) / (z * z - 1.0);
                const double next = z - p1 / derivative;
                if (std::abs(next - z) < 1e-15) {
                    z = next;
                    break;
                }
                z = next;
            }
            const double weight =
                2.0 / ((1.0 - z * z) * derivative * derivative);
            nodes_[i] = -z;
            nodes_[count - 1 - i] = z;
            weights_[i] = weight;
            weights_[count - 1 - i] = weight;
        }
    }

    template <typename Function>
    double integrate(Function&& function, double lower,
                     double upper) const {
        if (!(upper > lower)) {
            return 0.0;
        }
        const double half = 0.5 * (upper - lower);
        const double middle = 0.5 * (upper + lower);
        double sum = 0.0;
        for (std::size_t i = 0; i < nodes_.size(); ++i) {
            sum += weights_[i] * function(middle + half * nodes_[i]);
        }
        return half * sum;
    }

private:
    std::vector<double> nodes_;
    std::vector<double> weights_;
};

const GaussLegendre kQuadrature(64);

bool visibleAt(double observerX, double sourceU, double sourceV) {
    if (observerX < kWallX) {
        return true;
    }
    const double denominator = sourceU - observerX;
    if (std::abs(denominator) < 1e-15) {
        return sourceV >= kWallTop;
    }
    const double t = (kWallX - observerX) / denominator;
    if (!(t > 0.0 && t < 1.0)) {
        return true;
    }
    const double wallZ = kHeight * t;
    return wallZ > kWallTop;
}

double shadowCutU(double observerX) {
    if (observerX < kWallX) {
        return -1e100;
    }
    return observerX + kHeight * (kWallX - observerX) / kWallTop;
}

double antiderivativeV(double u, double observerX, double observerY,
                       double v) {
    const double a2 =
        kHeight * kHeight + (u - observerX) * (u - observerX);
    const double a = std::sqrt(a2);
    const double w = v - observerY;
    return w / (2.0 * a2 * (a2 + w * w)) +
           std::atan(w / a) / (2.0 * a2 * a);
}

double verticalIntegral(double u, double observerX, double observerY,
                        double lowerV, double upperV) {
    return kHeight * kHeight *
           (antiderivativeV(u, observerX, observerY, upperV) -
            antiderivativeV(u, observerX, observerY, lowerV));
}

double analyticIrradiance(const Shape& shape, double observerX,
                          double observerY, bool applyOccluder = true) {
    const double lowerVisible =
        applyOccluder ? shadowCutU(observerX) : -1e100;
    double integral = 0.0;

    if (shape.index == 2) {
        const double halfWidth = shape.width * 0.5;
        const double halfHeight = shape.height * 0.5;
        const double lower = std::max(-halfWidth, lowerVisible);
        if (lower < halfWidth) {
            integral = kQuadrature.integrate(
                [&](double u) {
                    return verticalIntegral(u, observerX, observerY,
                                            -halfHeight, halfHeight);
                },
                lower, halfWidth);
        }
    } else if (shape.index == 1) {
        const double radius = shape.radius;
        const double lowerU = std::max(-radius, lowerVisible);
        if (lowerU < radius) {
            const double lowerTheta =
                std::asin(std::max(-1.0, std::min(1.0, lowerU / radius)));
            integral = kQuadrature.integrate(
                [&](double theta) {
                    const double u = radius * std::sin(theta);
                    const double halfHeight = radius * std::cos(theta);
                    return radius * std::cos(theta) *
                           verticalIntegral(u, observerX, observerY,
                                            -halfHeight, halfHeight);
                },
                lowerTheta, kPi * 0.5);
        }
    } else {
        const double radius = shape.radius;
        const double halfCore = shape.coreLength * 0.5;
        const double coreLower = std::max(-halfCore, lowerVisible);
        if (coreLower < halfCore) {
            integral += kQuadrature.integrate(
                [&](double u) {
                    return verticalIntegral(u, observerX, observerY,
                                            -radius, radius);
                },
                coreLower, halfCore);
        }

        if (lowerVisible < halfCore + radius) {
            const double rightLower =
                std::max(-1.0, (lowerVisible - halfCore) / radius);
            integral += kQuadrature.integrate(
                [&](double theta) {
                    const double u = halfCore + radius * std::sin(theta);
                    const double halfHeight = radius * std::cos(theta);
                    return radius * std::cos(theta) *
                           verticalIntegral(u, observerX, observerY,
                                            -halfHeight, halfHeight);
                },
                std::max(0.0, std::asin(rightLower)), kPi * 0.5);
        }

        const double leftEnd = -halfCore;
        if (lowerVisible < leftEnd) {
            const double leftStart = -halfCore - radius;
            const double sCut = leftEnd - std::max(leftStart, lowerVisible);
            const double thetaUpper =
                std::asin(std::max(-1.0, std::min(1.0, sCut / radius)));
            integral += kQuadrature.integrate(
                [&](double theta) {
                    const double s = radius * std::sin(theta);
                    const double u = -halfCore - s;
                    const double halfHeight = radius * std::cos(theta);
                    return radius * std::cos(theta) *
                           verticalIntegral(u, observerX, observerY,
                                            -halfHeight, halfHeight);
                },
                0.0, thetaUpper);
        }
    }
    return kRadiance * integral;
}

void sampleShape(const Shape& shape, Pcg32& random, double& u,
                 double& v) {
    if (shape.index == 2) {
        u = (random.uniform() - 0.5) * shape.width;
        v = (random.uniform() - 0.5) * shape.height;
        return;
    }
    if (shape.index == 1) {
        const double radius = shape.radius * std::sqrt(random.uniform());
        const double phi = 2.0 * kPi * random.uniform();
        u = radius * std::cos(phi);
        v = radius * std::sin(phi);
        return;
    }

    const double radius = shape.radius;
    const double halfCore = shape.coreLength * 0.5;
    const double coreArea = shape.coreLength * 2.0 * radius;
    const double capArea = kPi * radius * radius;
    const double selector = random.uniform() * kArea;
    if (selector < coreArea) {
        u = (random.uniform() - 0.5) * shape.coreLength;
        v = (random.uniform() - 0.5) * 2.0 * radius;
        return;
    }
    const bool right = selector < coreArea + 0.5 * capArea;
    const double radial = radius * std::sqrt(random.uniform());
    const double phi = -0.5 * kPi + kPi * random.uniform();
    const double side = right ? 1.0 : -1.0;
    u = side * (halfCore + radial * std::cos(phi));
    v = radial * std::sin(phi);
}

double monteCarloIrradiance(const Shape& shape, double observerX,
                            double observerY, int samples,
                            uint64_t seedOffset = 0) {
    Pcg32 random(0x9e3779b97f4a7c15ULL *
                     static_cast<uint64_t>(shape.index + 1) +
                 0x243f6a8885a308d3ULL + seedOffset);
    double sum = 0.0;
    for (int i = 0; i < samples; ++i) {
        double u = 0.0;
        double v = 0.0;
        sampleShape(shape, random, u, v);
        if (!visibleAt(observerX, u, v)) {
            continue;
        }
        const double dx = u - observerX;
        const double dy = v - observerY;
        const double distanceSquared =
            kHeight * kHeight + dx * dx + dy * dy;
        sum += kHeight * kHeight /
               (distanceSquared * distanceSquared);
    }
    return kPower * sum / (kPi * samples);
}

double visibleFraction(const Shape& shape, double observerX,
                       double observerY) {
    const double clear = analyticIrradiance(
        shape, observerX, observerY, false);
    if (!(clear > 1e-15)) {
        return 0.0;
    }
    return clamp01(analyticIrradiance(shape, observerX, observerY, true) /
                   clear);
}

double mcVisibleFraction(const Shape& shape, double observerX,
                         double observerY, int samples, uint64_t seed) {
    Pcg32 random(0xd1b54a32d192ed03ULL ^ seed ^
                 (static_cast<uint64_t>(shape.index + 1) << 56U));
    double clear = 0.0;
    double visible = 0.0;
    for (int i = 0; i < samples; ++i) {
        double u = 0.0;
        double v = 0.0;
        sampleShape(shape, random, u, v);
        const double dx = u - observerX;
        const double dy = v - observerY;
        const double distanceSquared =
            kHeight * kHeight + dx * dx + dy * dy;
        const double kernel =
            kHeight * kHeight / (distanceSquared * distanceSquared);
        clear += kernel;
        if (visibleAt(observerX, u, v)) {
            visible += kernel;
        }
    }
    return clear > 0.0 ? clamp01(visible / clear) : 0.0;
}

template <typename Function>
double findIncreasingRoot(Function&& function, double lower, double upper,
                          double target) {
    for (int iteration = 0; iteration < 64; ++iteration) {
        const double middle = 0.5 * (lower + upper);
        if (function(middle) < target) {
            lower = middle;
        } else {
            upper = middle;
        }
    }
    return 0.5 * (lower + upper);
}

Penumbra computePenumbra(const Shape& shape, int samples) {
    Penumbra result;
    const double ratio = kWallTop / kHeight;
    const double inverse = 1.0 - ratio;
    result.umbraEnd = (kWallX - ratio * shape.xHalfExtent) / inverse;
    result.penumbraEnd =
        (kWallX + ratio * shape.xHalfExtent) / inverse;
    result.geometricWidth =
        2.0 * ratio * shape.xHalfExtent / inverse;
    result.halfLightX = kWallX / inverse;

    const double searchLower = kWallX - 0.2;
    const double searchUpper = result.penumbraEnd + 2.0;
    result.analytic95 = findIncreasingRoot(
        [&](double x) { return visibleFraction(shape, x, 0.0); },
        searchLower, searchUpper, 0.95);
    result.analytic05 = findIncreasingRoot(
        [&](double x) { return visibleFraction(shape, x, 0.0); },
        searchLower, searchUpper, 0.05);
    result.analyticWidth = result.analytic95 - result.analytic05;

    const uint64_t baseSeed =
        0xa4093822299f31d0ULL ^
        (static_cast<uint64_t>(shape.index + 1) << 48U);
    result.mc95 = findIncreasingRoot(
        [&](double x) {
            return mcVisibleFraction(shape, x, 0.0, samples, baseSeed);
        },
        searchLower, searchUpper, 0.95);
    result.mc05 = findIncreasingRoot(
        [&](double x) {
            return mcVisibleFraction(shape, x, 0.0, samples, baseSeed + 1);
        },
        searchLower, searchUpper, 0.05);
    result.mcWidth = result.mc95 - result.mc05;
    result.widthError = std::abs(result.mcWidth - result.analyticWidth);
    return result;
}

FluxResult computeFlux(const Shape& shape, int samples) {
    Pcg32 random(0x13198a2e03707344ULL +
                 static_cast<uint64_t>(shape.index + 1));
    double sum = 0.0;
    for (int i = 0; i < samples; ++i) {
        const double cosine = random.uniform();
        sum += cosine;
    }
    FluxResult result;
    result.analytic = kPi * kRadiance * kArea;
    result.monteCarlo = 2.0 * kPi * kRadiance * kArea * sum / samples;
    result.relativeError =
        std::abs(result.monteCarlo - result.analytic) / result.analytic;
    return result;
}

Summary computeSummary(const std::vector<Pixel>& pixels) {
    Summary result;
    std::vector<double> relative;
    relative.reserve(pixels.size());
    for (const Pixel& pixel : pixels) {
        result.peak = std::max(result.peak, pixel.analytic);
    }
    double squaredError = 0.0;
    for (const Pixel& pixel : pixels) {
        if (pixel.analytic >= 0.01 * result.peak) {
            relative.push_back(
                std::abs(pixel.monteCarlo - pixel.analytic) /
                pixel.analytic);
        }
        const double normalized =
            std::abs(pixel.monteCarlo - pixel.analytic) / result.peak;
        result.maxNormalized = std::max(result.maxNormalized, normalized);
        squaredError += normalized * normalized;
    }
    result.meanRelative =
        std::accumulate(relative.begin(), relative.end(), 0.0) /
        static_cast<double>(relative.size());
    std::sort(relative.begin(), relative.end());
    const std::size_t p99Index =
        static_cast<std::size_t>(0.99 * (relative.size() - 1));
    result.p99Relative = relative[p99Index];
    result.normalizedRmse =
        std::sqrt(squaredError / static_cast<double>(pixels.size()));
    return result;
}

void writeParameters(const fs::path& path, const std::vector<Shape>& shapes) {
    std::ofstream out(path);
    out << "shape,area_m2,power_W,radiance_W_m2_sr,radius_m,"
           "core_length_m,width_x_m,width_y_m,x_min_m,x_max_m,y_max_m,"
           "source_height_m,wall_x_m,wall_top_z_m\n";
    out << std::setprecision(12);
    for (const Shape& shape : shapes) {
        out << shape.name << ',' << kArea << ',' << kPower << ','
            << kRadiance << ',' << shape.radius << ',' << shape.coreLength
            << ',' << shape.width << ',' << shape.height << ','
            << -shape.xHalfExtent << ',' << shape.xHalfExtent << ','
            << (shape.index == 2 ? shape.height * 0.5 : shape.radius)
            << ',' << kHeight << ',' << kWallX << ',' << kWallTop << '\n';
    }
}

void writePixels(const fs::path& path, const Shape& shape,
                 const std::vector<Pixel>& pixels, double penumbraWidth,
                 double peak) {
    std::ofstream out(path);
    out << std::setprecision(15);
    out << "shape,ix,iy,x_m,y_m,E_analytic_W_m2,E_monte_carlo_W_m2,"
           "relative_error,normalized_error,visible_fraction,"
           "penumbra_width_m\n";
    for (int iy = 0; iy < kImageHeight; ++iy) {
        for (int ix = 0; ix < kImageWidth; ++ix) {
            const std::size_t index =
                static_cast<std::size_t>(iy * kImageWidth + ix);
            const Pixel& pixel = pixels[index];
            const double relative =
                pixel.analytic > 0.0
                    ? std::abs(pixel.monteCarlo - pixel.analytic) /
                          pixel.analytic
                    : 0.0;
            const double normalized =
                peak > 0.0
                    ? std::abs(pixel.monteCarlo - pixel.analytic) / peak
                    : 0.0;
            out << shape.name << ',' << ix << ',' << iy << ','
                << pixelX(ix) << ',' << pixelY(iy) << ','
                << pixel.analytic << ',' << pixel.monteCarlo << ','
                << relative << ',' << normalized << ',' << pixel.visible
                << ',' << penumbraWidth << '\n';
        }
    }
}

void writeDirections(const fs::path& path, const Shape& shape,
                     const Penumbra& penumbra, int samples) {
    const double x25 =
        0.5 * (penumbra.umbraEnd + penumbra.halfLightX);
    const double x75 =
        0.5 * (penumbra.halfLightX + penumbra.penumbraEnd);
    const std::array<std::pair<const char*, double>, 5> probes{{
        {"beam_center", 0.0},
        {"penumbra_25pct", x25},
        {"penumbra_50pct", penumbra.halfLightX},
        {"penumbra_75pct", x75},
        {"fully_lit", penumbra.penumbraEnd + 0.35},
    }};

    std::ofstream out(path);
    out << std::setprecision(15);
    out << "shape,probe,x_m,y_m,to_light_centroid_x,"
           "to_light_centroid_y,to_light_centroid_z,mean_to_light_x,"
           "mean_to_light_y,mean_to_light_z,distance_m,"
           "distance_attenuation,E_analytic_W_m2,visible_fraction\n";
    out.setf(std::ios::fixed);
    out << std::setprecision(12);
    for (const auto& [name, x] : probes) {
        const double y = 0.0;
        const double distance = std::sqrt(x * x + y * y + kHeight * kHeight);
        const double centroidX = -x / distance;
        const double centroidY = -y / distance;
        const double centroidZ = kHeight / distance;

        Pcg32 random(0x452821e638d01377ULL ^
                     (static_cast<uint64_t>(shape.index + 1) << 40U) ^
                     static_cast<uint64_t>(std::llround((x + 8.0) * 1e6)));
        double meanU = 0.0;
        double meanV = 0.0;
        double weightSum = 0.0;
        for (int i = 0; i < samples; ++i) {
            double u = 0.0;
            double v = 0.0;
            sampleShape(shape, random, u, v);
            if (!visibleAt(x, u, v)) {
                continue;
            }
            const double dx = u - x;
            const double dy = v - y;
            const double rayDistance =
                std::sqrt(dx * dx + dy * dy + kHeight * kHeight);
            const double weight = kHeight * kHeight /
                                  (rayDistance * rayDistance *
                                   rayDistance * rayDistance);
            meanU += weight * u;
            meanV += weight * v;
            weightSum += weight;
        }
        meanU /= weightSum;
        meanV /= weightSum;
        const double meanDx = meanU - x;
        const double meanDy = meanV - y;
        const double meanDistance =
            std::sqrt(meanDx * meanDx + meanDy * meanDy +
                      kHeight * kHeight);
        const double meanX = meanDx / meanDistance;
        const double meanY = meanDy / meanDistance;
        const double meanZ = kHeight / meanDistance;
        out << shape.name << ',' << name << ',' << x << ',' << y << ','
            << centroidX << ',' << centroidY << ',' << centroidZ << ','
            << meanX << ',' << meanY << ',' << meanZ << ',' << distance << ','
            << kHeight * kHeight / (distance * distance) << ','
            << analyticIrradiance(shape, x, y) << ','
            << visibleFraction(shape, x, y) << '\n';
    }
}

void writeSummaries(const fs::path& path,
                    const std::vector<Shape>& shapes,
                    const std::vector<Summary>& summaries, int samples) {
    std::ofstream out(path);
    out << "shape,mean_relative_error,p99_relative_error,"
           "normalized_rmse,max_normalized_error,mean_threshold,"
           "p99_threshold,nrmse_threshold,pass,pixels,samples_per_pixel\n";
    out << std::setprecision(12);
    for (std::size_t i = 0; i < shapes.size(); ++i) {
        const Summary& summary = summaries[i];
        const bool pass = summary.meanRelative <= kMeanThreshold &&
                          summary.p99Relative <= kP99Threshold &&
                          summary.normalizedRmse <= kRmseThreshold;
        out << shapes[i].name << ',' << summary.meanRelative << ','
            << summary.p99Relative << ',' << summary.normalizedRmse << ','
            << summary.maxNormalized << ',' << kMeanThreshold << ','
            << kP99Threshold << ',' << kRmseThreshold << ','
            << (pass ? "true" : "false") << ','
            << kImageWidth * kImageHeight << ',' << samples << '\n';
    }
}

void writePenumbras(const fs::path& path,
                    const std::vector<Shape>& shapes,
                    const std::vector<Penumbra>& penumbras) {
    std::ofstream out(path);
    out << "shape,wall_x_m,umbra_start_x_m,umbra_end_x_m,"
           "penumbra_end_x_m,geometric_penumbra_width_m,"
           "geometric_penumbra_width_px,half_light_x_m,"
           "penumbra_5_95_analytic_m,penumbra_5_95_mc_m,width_error_m,"
           "threshold_m,pass\n";
    out << std::setprecision(15);
    const double pixelSize = (kXMax - kXMin) / kImageWidth;
    for (std::size_t i = 0; i < shapes.size(); ++i) {
        const Penumbra& value = penumbras[i];
        out << shapes[i].name << ',' << kWallX << ',' << kWallX << ','
            << value.umbraEnd << ',' << value.penumbraEnd << ','
            << value.geometricWidth << ','
            << value.geometricWidth / pixelSize << ','
            << value.halfLightX << ',' << value.analyticWidth << ','
            << value.mcWidth << ',' << value.widthError << ','
            << kWidthThreshold << ','
            << (value.widthError <= kWidthThreshold ? "true" : "false")
            << '\n';
    }
}

void writeFlux(const fs::path& path, const std::vector<Shape>& shapes,
               const std::vector<FluxResult>& fluxes, int samples) {
    std::ofstream out(path);
    out << "shape,power_analytic_W,power_monte_carlo_W,relative_error,"
           "threshold,pass,monte_carlo_samples\n";
    out << std::setprecision(15);
    for (std::size_t i = 0; i < shapes.size(); ++i) {
        out << shapes[i].name << ',' << fluxes[i].analytic << ','
            << fluxes[i].monteCarlo << ',' << fluxes[i].relativeError
            << ',' << kFluxThreshold << ','
            << (fluxes[i].relativeError <= kFluxThreshold ? "true" : "false")
            << ',' << samples << '\n';
    }
}

void writeConfig(const fs::path& path, int pixelSamples, int fluxSamples,
                 int penumbraSamples) {
    std::ofstream out(path);
    out << "key,value\n";
    out << "pixel_samples," << pixelSamples << '\n';
    out << "flux_samples," << fluxSamples << '\n';
    out << "penumbra_mc_samples," << penumbraSamples << '\n';
    out << "pixel_width," << kImageWidth << '\n';
    out << "pixel_height," << kImageHeight << '\n';
    out << "x_min_m," << kXMin << '\n';
    out << "x_max_m," << kXMax << '\n';
    out << "y_min_m," << kYMin << '\n';
    out << "y_max_m," << kYMax << '\n';
    out << "mean_relative_threshold," << kMeanThreshold << '\n';
    out << "p99_relative_threshold," << kP99Threshold << '\n';
    out << "normalized_rmse_threshold," << kRmseThreshold << '\n';
    out << "flux_relative_threshold," << kFluxThreshold << '\n';
    out << "penumbra_width_threshold_m," << kWidthThreshold << '\n';
}

}  // namespace

int main(int argc, char** argv) {
    fs::path outputDirectory = "artifacts";
    int pixelSamples = 131072;
    int fluxSamples = 2000000;
    int penumbraSamples = 131072;

    for (int i = 1; i < argc; ++i) {
        const std::string argument = argv[i];
        auto nextValue = [&]() -> std::string {
            if (i + 1 >= argc) {
                throw std::runtime_error("missing value for " + argument);
            }
            return argv[++i];
        };
        try {
            if (argument == "--out") {
                outputDirectory = nextValue();
            } else if (argument == "--pixel-samples") {
                pixelSamples = std::stoi(nextValue());
            } else if (argument == "--flux-samples") {
                fluxSamples = std::stoi(nextValue());
            } else if (argument == "--penumbra-samples") {
                penumbraSamples = std::stoi(nextValue());
            } else if (argument == "--help" || argument == "-h") {
                std::cout
                    << "usage: area_lights [--out DIR] [--pixel-samples N] "
                       "[--flux-samples N] [--penumbra-samples N]\n";
                return 0;
            } else {
                throw std::runtime_error("unknown argument: " + argument);
            }
        } catch (const std::exception& error) {
            std::cerr << error.what() << '\n';
            return 2;
        }
    }
    if (pixelSamples <= 0 || fluxSamples <= 0 ||
        penumbraSamples <= 0) {
        std::cerr << "sample counts must be positive\n";
        return 2;
    }

    const fs::path dataDirectory = outputDirectory / "data";
    const fs::path imageDirectory = outputDirectory / "images";
    fs::create_directories(dataDirectory);
    fs::create_directories(imageDirectory);

    const std::vector<Shape> shapes = makeShapes();
    writeParameters(dataDirectory / "parameters.csv", shapes);
    writeConfig(dataDirectory / "run_config.csv", pixelSamples,
                fluxSamples, penumbraSamples);

    bool allPassed = true;
    std::vector<std::vector<Pixel>> allPixels;
    std::vector<Summary> summaries;
    std::vector<Penumbra> penumbras;
    std::vector<FluxResult> fluxes;
    allPixels.reserve(shapes.size());
    summaries.reserve(shapes.size());
    penumbras.reserve(shapes.size());
    fluxes.reserve(shapes.size());

    for (const Shape& shape : shapes) {
        allPixels.emplace_back(kImageWidth * kImageHeight);
        std::vector<Pixel>& pixels = allPixels.back();
        for (int iy = 0; iy < kImageHeight; ++iy) {
            for (int ix = 0; ix < kImageWidth; ++ix) {
                const std::size_t index =
                    static_cast<std::size_t>(iy * kImageWidth + ix);
                Pixel& pixel = pixels[index];
                pixel.x = pixelX(ix);
                pixel.y = pixelY(iy);
                pixel.analytic =
                    analyticIrradiance(shape, pixel.x, pixel.y);
                const uint64_t pixelSeed =
                    (static_cast<uint64_t>(shape.index + 1) << 56U) ^
                    (static_cast<uint64_t>(iy * kImageWidth + ix) *
                     0x9e3779b97f4a7c15ULL);
                pixel.monteCarlo = monteCarloIrradiance(
                    shape, pixel.x, pixel.y, pixelSamples, pixelSeed);
                pixel.visible =
                    visibleFraction(shape, pixel.x, pixel.y);
            }
        }

        const Summary summary = computeSummary(pixels);
        const Penumbra penumbra =
            computePenumbra(shape, penumbraSamples);
        const FluxResult flux = computeFlux(shape, fluxSamples);
        summaries.push_back(summary);
        penumbras.push_back(penumbra);
        fluxes.push_back(flux);
        const bool pixelPass =
            summary.meanRelative <= kMeanThreshold &&
            summary.p99Relative <= kP99Threshold &&
            summary.normalizedRmse <= kRmseThreshold;
        const bool penumbraPass =
            penumbra.widthError <= kWidthThreshold;
        const bool fluxPass = flux.relativeError <= kFluxThreshold;
        allPassed =
            allPassed && pixelPass && penumbraPass && fluxPass;

        writePixels(dataDirectory / (shape.name + "_pixels.csv"), shape,
                    pixels, penumbra.analyticWidth, summary.peak);
        writeDirections(dataDirectory / (shape.name + "_directions.csv"),
                        shape, penumbra, 524288);

        std::cout << std::setprecision(6) << shape.name
                  << ": peak=" << summary.peak
                  << " meanRel=" << summary.meanRelative
                  << " p99Rel=" << summary.p99Relative
                  << " nrmse=" << summary.normalizedRmse
                  << " widthErr=" << penumbra.widthError
                  << " fluxErr=" << flux.relativeError
                  << " pass=" << (pixelPass && penumbraPass && fluxPass)
                  << '\n';
    }

    writeSummaries(dataDirectory / "pixel_summary.csv", shapes,
                   summaries, pixelSamples);
    writePenumbras(dataDirectory / "penumbra.csv", shapes, penumbras);
    writeFlux(dataDirectory / "flux_validation.csv", shapes, fluxes,
              fluxSamples);

    std::cout << (allPassed ? "ALL_CHECKS_PASS" : "CHECK_FAILED")
              << '\n';
    return allPassed ? 0 : 1;
}
