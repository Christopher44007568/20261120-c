#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <vector>

#include "renderer.h"
#include "scenes.h"

struct Args {
    std::map<std::string, std::string> values;

    std::string get(const std::string& key, const std::string& fallback) const {
        auto it = values.find(key);
        return it == values.end() ? fallback : it->second;
    }
    double getDouble(const std::string& key, double fallback) const {
        auto it = values.find(key);
        return it == values.end() ? fallback : std::stod(it->second);
    }
    int getInt(const std::string& key, int fallback) const {
        auto it = values.find(key);
        return it == values.end() ? fallback : std::stoi(it->second);
    }
};

inline Args parseArgs(int argc, char** argv) {
    Args args;
    for (int i = 2; i < argc; ++i) {
        std::string key = argv[i];
        if (key.rfind("--", 0) != 0) {
            continue;
        }
        key = key.substr(2);
        std::string value = "1";
        if (i + 1 < argc && std::string(argv[i + 1]).rfind("--", 0) != 0) {
            value = argv[++i];
        }
        args.values[key] = value;
    }
    return args;
}

inline std::string stripExtension(const std::string& path) {
    const size_t slash = path.find_last_of('/');
    const size_t dot = path.find_last_of('.');
    if (dot == std::string::npos || (slash != std::string::npos && dot < slash)) {
        return path;
    }
    return path.substr(0, dot);
}

inline bool readPfm(const std::string& path, int& width, int& height,
                    std::vector<Vec3>& pixels) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        return false;
    }
    std::string magic;
    double scale = 1.0;
    in >> magic >> width >> height >> scale;
    in.ignore(1);
    if (magic != "PF" || width <= 0 || height <= 0) {
        return false;
    }
    pixels.assign(static_cast<size_t>(width) * height, Vec3{});
    for (int y = height - 1; y >= 0; --y) {
        for (int x = 0; x < width; ++x) {
            float rgb[3];
            in.read(reinterpret_cast<char*>(rgb), sizeof(rgb));
            if (!in) {
                return false;
            }
            pixels[static_cast<size_t>(y * width + x)] =
                Vec3{rgb[0], rgb[1], rgb[2]};
        }
    }
    return true;
}

inline double luminance(const Vec3& c) {
    return 0.2126 * c.x + 0.7152 * c.y + 0.0722 * c.z;
}

inline int comparePfm(const std::string& referencePath,
                      const std::string& imagePath) {
    int rw = 0, rh = 0, iw = 0, ih = 0;
    std::vector<Vec3> ref, img;
    if (!readPfm(referencePath, rw, rh, ref) ||
        !readPfm(imagePath, iw, ih, img) || rw != iw || rh != ih) {
        std::cerr << "Cannot read PFM pair: " << referencePath << ", "
                  << imagePath << "\n";
        return 1;
    }
    double mse = 0.0, mseLum = 0.0, refEnergy = 0.0, sumError = 0.0;
    double maxError = 0.0;
    for (size_t i = 0; i < ref.size(); ++i) {
        const Vec3 d = img[i] - ref[i];
        const double e2 = dot(d, d);
        mse += e2 / 3.0;
        const double dl = luminance(img[i]) - luminance(ref[i]);
        mseLum += dl * dl;
        refEnergy += luminance(ref[i]) * luminance(ref[i]);
        sumError += std::abs(dl);
        maxError = std::max(maxError, std::abs(dl));
    }
    const double n = static_cast<double>(ref.size());
    mse /= n;
    mseLum /= n;
    refEnergy /= n;
    const double rmse = std::sqrt(mse);
    const double rmseLum = std::sqrt(mseLum);
    const double relRmse =
        refEnergy > 0.0 ? std::sqrt(mseLum / refEnergy) : 0.0;
    const double psnr = mse > 0.0 ? 10.0 * std::log10(1.0 / mse) : 99.0;
    std::cout << std::fixed << std::setprecision(9) << "mse=" << mse
              << ",rmse=" << rmse << ",rmse_lum=" << rmseLum
              << ",relative_rmse=" << relRmse << ",psnr=" << psnr
              << ",mean_abs_lum=" << (sumError / n)
              << ",max_abs_lum=" << maxError << "\n";
    return 0;
}

inline int statsPfm(const std::vector<std::string>& paths) {
    if (paths.empty()) {
        return 1;
    }
    int w = 0, h = 0;
    std::vector<std::vector<Vec3>> images;
    for (const auto& p : paths) {
        int iw = 0, ih = 0;
        std::vector<Vec3> img;
        if (!readPfm(p, iw, ih, img) || (!images.empty() && (iw != w || ih != h))) {
            return 1;
        }
        w = iw;
        h = ih;
        images.push_back(std::move(img));
    }
    const size_t n = images.size();
    double totalVariance = 0.0;
    double totalMean = 0.0;
    for (size_t i = 0; i < images[0].size(); ++i) {
        Vec3 mean{};
        for (const auto& img : images) {
            mean += img[i];
        }
        mean = mean / static_cast<double>(n);
        Vec3 variance{};
        if (n > 1) {
            for (const auto& img : images) {
                const Vec3 d = img[i] - mean;
                variance += d * d;
            }
            variance = variance / static_cast<double>(n - 1);
        }
        totalVariance += luminance(variance);
        totalMean += luminance(mean);
    }
    totalVariance /= static_cast<double>(images[0].size());
    totalMean /= static_cast<double>(images[0].size());
    std::cout << std::fixed << std::setprecision(9)
              << "runs=" << n << ",mean_lum=" << totalMean
              << ",mean_pixel_variance=" << totalVariance
              << ",relative_variance="
              << (totalMean > 0.0 ? totalVariance / (totalMean * totalMean) : 0.0)
              << "\n";
    return 0;
}

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr
            << "Usage:\n"
            << "  rpt render --scene caustic --integrator bdpt --spp 16 "
               "--width 160 --height 120 --out image\n"
            << "  rpt compare --reference ref.pfm --image test.pfm\n"
            << "  rpt stats img1.pfm img2.pfm ...\n";
        return 1;
    }
    const std::string command = argv[1];
    if (command == "render") {
        Args args = parseArgs(argc, argv);
        const std::string sceneName = args.get("scene", "caustic");
        const std::string integratorName = args.get("integrator", "bdpt");
        const int width = args.getInt("width", 160);
        const int height = args.getInt("height", 120);
        const int spp = args.getInt("spp", 4);
        const int maxDepth = args.getInt("max-depth", 8);
        const double timeLimit = args.getDouble("time", 0.0);
        const double exposure = args.getDouble("exposure", 1.0);
        const unsigned threads = static_cast<unsigned>(
            args.getInt("threads", static_cast<int>(std::thread::hardware_concurrency())));
        const uint64_t seed =
            static_cast<uint64_t>(std::stoull(args.get("seed", "1")));
        const std::string outBase = stripExtension(args.get("out", "render"));
        const IntegratorKind kind =
            integratorName == "pt" ? IntegratorKind::PathTracing
                                   : IntegratorKind::BDPT;

        Scene scene = makeScene(sceneName);
        Camera camera = makeCamera(sceneName, width, height);
        RenderResult result = renderImage(scene, camera, kind, spp, timeLimit,
                                          maxDepth, seed, static_cast<int>(threads));

        const std::string ppmPath = outBase + ".ppm";
        const std::string pfmPath = outBase + ".pfm";
        writePpm(result, ppmPath, exposure);
        writePfm(result, pfmPath);
        std::cout << std::fixed << std::setprecision(6)
                  << "scene=" << sceneName << ",integrator=" << integratorName
                  << ",width=" << width << ",height=" << height
                  << ",spp=" << result.spp << ",seconds=" << result.seconds
                  << ",samples_per_second="
                  << (result.seconds > 0.0
                          ? result.pathSamples / result.seconds
                          : 0.0)
                  << ",ppm=" << ppmPath << ",pfm=" << pfmPath << "\n";
        return 0;
    }
    if (command == "compare") {
        Args args = parseArgs(argc, argv);
        return comparePfm(args.get("reference", ""), args.get("image", ""));
    }
    if (command == "stats") {
        std::vector<std::string> paths;
        for (int i = 2; i < argc; ++i) {
            paths.emplace_back(argv[i]);
        }
        return statsPfm(paths);
    }
    return 1;
}
