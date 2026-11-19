#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <string>
#include <thread>
#include <vector>

#include "bdpt.h"
#include "integrators.h"

struct RenderResult {
    int width = 0;
    int height = 0;
    int spp = 0;
    double seconds = 0.0;
    uint64_t pathSamples = 0;
    std::vector<Vec3> pixels;
};

enum class IntegratorKind { PathTracing, BDPT };

template <typename Fn>
static void parallelForPixels(int width, int height, int threadCount,
                              std::vector<std::vector<Vec3>>& threadFilms,
                              Fn&& fn) {
    std::atomic<int> next{0};
    const int total = width * height;
    auto worker = [&](int tid) {
        auto& film = threadFilms[static_cast<size_t>(tid)];
        while (true) {
            const int pixel = next.fetch_add(1, std::memory_order_relaxed);
            if (pixel >= total) {
                break;
            }
            fn(tid, pixel % width, pixel / width, film);
        }
    };
    std::vector<std::thread> threads;
    threads.reserve(static_cast<size_t>(threadCount));
    for (int i = 0; i < threadCount; ++i) {
        threads.emplace_back(worker, i);
    }
    for (auto& t : threads) {
        t.join();
    }
}

inline RenderResult renderImage(const Scene& scene, const Camera& camera,
                                IntegratorKind integrator, int spp,
                                double timeLimit, int maxDepth, uint64_t seed,
                                int threadCount) {
    RenderResult result;
    result.width = camera.width;
    result.height = camera.height;
    threadCount = std::max(1, threadCount);
    const size_t pixelCount =
        static_cast<size_t>(camera.width) * static_cast<size_t>(camera.height);
    std::vector<std::vector<Vec3>> threadFilms(
        static_cast<size_t>(threadCount), std::vector<Vec3>(pixelCount));

    const auto begin = std::chrono::steady_clock::now();
    int pass = 0;
    while (true) {
        if (timeLimit <= 0.0 && pass >= spp) {
            break;
        }
        if (timeLimit > 0.0) {
            const double elapsed =
                std::chrono::duration<double>(std::chrono::steady_clock::now() -
                                              begin)
                    .count();
            if (elapsed >= timeLimit) {
                break;
            }
        }

        parallelForPixels(
            camera.width, camera.height, threadCount, threadFilms,
            [&](int, int x, int y, std::vector<Vec3>& film) {
                const uint64_t pixel =
                    static_cast<uint64_t>(y * camera.width + x);
                Rng rng(hashSeed(seed, pixel, static_cast<uint64_t>(pass)));
                if (integrator == IntegratorKind::BDPT) {
                    Vec3 L = traceBDPT(scene, camera, x, y, rng, maxDepth, film);
                    film[static_cast<size_t>(y * camera.width + x)] += L;
                } else {
                    Vec3 L = tracePath(scene, camera, x, y, rng, maxDepth);
                    film[static_cast<size_t>(y * camera.width + x)] += L;
                }
            });
        ++pass;
    }

    const double elapsed =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - begin)
            .count();
    result.spp = pass;
    result.seconds = elapsed;
    result.pathSamples =
        static_cast<uint64_t>(pass) * static_cast<uint64_t>(pixelCount);
    result.pixels.assign(pixelCount, Vec3{});
    for (const auto& film : threadFilms) {
        for (size_t i = 0; i < pixelCount; ++i) {
            result.pixels[i] += film[i];
        }
    }
    if (pass > 0) {
        const double inv = 1.0 / static_cast<double>(pass);
        for (Vec3& p : result.pixels) {
            p *= inv;
        }
    }
    return result;
}

inline bool writePfm(const RenderResult& image, const std::string& path) {
    std::ofstream out(path, std::ios::binary);
    if (!out) {
        return false;
    }
    out << "PF\n" << image.width << ' ' << image.height << "\n-1.0\n";
    for (int y = image.height - 1; y >= 0; --y) {
        for (int x = 0; x < image.width; ++x) {
            const Vec3& p =
                image.pixels[static_cast<size_t>(y * image.width + x)];
            const float rgb[3] = {static_cast<float>(p.x),
                                  static_cast<float>(p.y),
                                  static_cast<float>(p.z)};
            out.write(reinterpret_cast<const char*>(rgb), sizeof(rgb));
        }
    }
    return true;
}

inline void writePpm(const RenderResult& image, const std::string& path,
                     double exposure = 1.0) {
    std::ofstream out(path, std::ios::binary);
    out << "P6\n" << image.width << ' ' << image.height << "\n255\n";
    auto encode = [&](double c) {
        c = std::max(0.0, c * exposure);
        c = c / (1.0 + c);
        c = std::pow(c, 1.0 / 2.2);
        return static_cast<unsigned char>(
            std::clamp(static_cast<int>(c * 255.0 + 0.5), 0, 255));
    };
    for (const Vec3& p : image.pixels) {
        const unsigned char rgb[3] = {encode(p.x), encode(p.y), encode(p.z)};
        out.write(reinterpret_cast<const char*>(rgb), 3);
    }
}
