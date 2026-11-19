#include "renderer.h"

#include "rng.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <stdexcept>

namespace {

constexpr double kPi = 3.14159265358979323846;

void buildBasis(const Vec3& normal, Vec3& tangent, Vec3& bitangent) {
    const Vec3 helper = std::abs(normal.z) < 0.999 ? Vec3(0.0, 0.0, 1.0) : Vec3(0.0, 1.0, 0.0);
    tangent = normalize(cross(helper, normal));
    bitangent = cross(normal, tangent);
}

Vec3 sampleCosineHemisphere(const Vec3& normal, Rng& rng) {
    const double u1 = rng.next();
    const double u2 = rng.next();
    const double radius = std::sqrt(u1);
    const double phi = 2.0 * kPi * u2;
    const double localX = radius * std::cos(phi);
    const double localY = radius * std::sin(phi);
    const double localZ = std::sqrt(std::max(0.0, 1.0 - u1));
    Vec3 tangent;
    Vec3 bitangent;
    buildBasis(normal, tangent, bitangent);
    return normalize(tangent * localX + bitangent * localY + normal * localZ);
}

Vec3 sampleCone(const Vec3& centerDirection, double cosThetaMax, Rng& rng) {
    const double u1 = rng.next();
    const double u2 = rng.next();
    const double cosTheta = 1.0 - u1 * (1.0 - cosThetaMax);
    const double sinTheta = std::sqrt(std::max(0.0, 1.0 - cosTheta * cosTheta));
    const double phi = 2.0 * kPi * u2;
    Vec3 tangent;
    Vec3 bitangent;
    buildBasis(centerDirection, tangent, bitangent);
    return normalize(tangent * (sinTheta * std::cos(phi)) +
                     bitangent * (sinTheta * std::sin(phi)) + centerDirection * cosTheta);
}

Vec3 estimateDirectLight(const Scene& scene, const Hit& hit, Rng& rng) {
    const Sphere& light = scene.light();
    const Vec3 toCenter = light.center - hit.position;
    const double distanceSquared = lengthSquared(toCenter);
    const double radiusSquared = light.radius * light.radius;
    if (distanceSquared <= radiusSquared * 1.0001) {
        return light.material.emission;
    }

    const double distance = std::sqrt(distanceSquared);
    const double cosThetaMax = std::sqrt(std::max(0.0, 1.0 - radiusSquared / distanceSquared));
    const Vec3 direction = sampleCone(toCenter / distance, cosThetaMax, rng);
    const double cosine = std::max(0.0, dot(hit.normal, direction));
    if (cosine <= 0.0) {
        return {};
    }
    const Vec3 shadowOrigin = hit.position + hit.normal * 2e-4;
    if (scene.occluded({shadowOrigin, direction}, distance - light.radius * 0.999)) {
        return {};
    }
    const double solidAnglePdf = 1.0 / (2.0 * kPi * std::max(1e-6, 1.0 - cosThetaMax));
    return light.material.emission * (hit.material.albedo * (cosine / (kPi * solidAnglePdf)));
}

Vec3 tracePath(const Scene& scene, Ray ray, Rng& rng) {
    Vec3 radiance;
    Vec3 throughput(1.0, 1.0, 1.0);
    for (int bounce = 0; bounce < 4; ++bounce) {
        Hit hit;
        if (!scene.intersect(ray, 2e-4, 1e30, hit)) {
            radiance += throughput * scene.sky(ray.direction);
            break;
        }
        if (hit.objectId == 99) {
            if (bounce == 0) {
                radiance += throughput * hit.material.emission;
            }
            break;
        }
        radiance += throughput * estimateDirectLight(scene, hit, rng);
        throughput *= hit.material.albedo;
        if (std::max({throughput.x, throughput.y, throughput.z}) < 1e-4) {
            break;
        }
        const Vec3 nextDirection = sampleCosineHemisphere(hit.normal, rng);
        ray = {hit.position + hit.normal * 2e-4, nextDirection};
    }
    return radiance;
}

unsigned char toSrgb(double linear) {
    const double mapped = std::pow(std::clamp(linear, 0.0, 1.0), 1.0 / 2.2);
    return static_cast<unsigned char>(std::clamp(mapped * 255.0 + 0.5, 0.0, 255.0));
}

void writeHeader(std::ofstream& output, int width, int height) {
    output << "P6\n" << width << ' ' << height << "\n255\n";
}

}  // namespace

RenderFrame renderFrame(const Scene& scene, const Camera& camera, int width, int height,
                        int samplesPerPixel, int frameIndex, std::uint64_t seed) {
    if (width <= 0 || height <= 0 || samplesPerPixel <= 0) {
        throw std::invalid_argument("render dimensions and sample count must be positive");
    }
    RenderFrame frame;
    frame.width = width;
    frame.height = height;
    frame.camera = camera;
    frame.samplesPerPixel = samplesPerPixel;
    frame.frameIndex = frameIndex;
    const std::size_t pixelCount = static_cast<std::size_t>(width) * height;
    frame.color.assign(pixelCount, {});
    frame.normal.assign(pixelCount, {});
    frame.worldPosition.assign(pixelCount, {});
    frame.depth.assign(pixelCount, 1e30);
    frame.objectId.assign(pixelCount, -1);

    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const std::size_t pixel = static_cast<std::size_t>(y) * width + x;
            const Ray primary = camera.primaryRay(x, y, width, height);
            Hit hit;
            if (scene.intersect(primary, 2e-4, 1e30, hit)) {
                frame.normal[pixel] = hit.normal;
                frame.worldPosition[pixel] = hit.position;
                frame.objectId[pixel] = hit.objectId;
                const Vec3 relative = hit.position - camera.position;
                frame.depth[pixel] = dot(relative, camera.forward);
            } else {
                frame.worldPosition[pixel] = primary.origin + primary.direction * 1e5;
            }

            Vec3 sum;
            for (int sample = 0; sample < samplesPerPixel; ++sample) {
                Rng rng(hashSeed(seed, static_cast<std::uint64_t>(pixel),
                                 static_cast<std::uint64_t>(sample + 1)));
                sum += tracePath(scene, primary, rng);
            }
            frame.color[pixel] = sum / samplesPerPixel;
        }
    }
    return frame;
}

void writePpm(const std::string& path, const RenderFrame& frame) {
    writePpm(path, frame.width, frame.height, frame.color);
}

void writePpm(const std::string& path, int width, int height, const std::vector<Vec3>& pixels) {
    if (pixels.size() != static_cast<std::size_t>(width) * height) {
        throw std::invalid_argument("pixel count does not match image dimensions");
    }
    std::ofstream output(path, std::ios::binary);
    if (!output) {
        throw std::runtime_error("cannot open output image: " + path);
    }
    writeHeader(output, width, height);
    for (const Vec3& pixel : pixels) {
        const unsigned char rgb[3] = {toSrgb(pixel.x), toSrgb(pixel.y), toSrgb(pixel.z)};
        output.write(reinterpret_cast<const char*>(rgb), 3);
    }
}

void writePpm(const std::string& path, int width, int height, const std::vector<double>& values) {
    if (values.size() != static_cast<std::size_t>(width) * height) {
        throw std::invalid_argument("pixel count does not match image dimensions");
    }
    std::vector<Vec3> pixels(values.size());
    for (std::size_t i = 0; i < values.size(); ++i) {
        pixels[i] = Vec3(values[i], values[i], values[i]);
    }
    writePpm(path, width, height, pixels);
}

