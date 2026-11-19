#include "raster.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

namespace {

void usage() {
    std::cerr <<
        "usage:\n"
        "  tile_rast compare [opts]            immediate vs tiled, one tile size\n"
        "  tile_rast sweep   [opts] out.csv    tile-size sweep\n"
        "  tile_rast matrix  [opts] out.csv    tile-size x triangle-size grid\n"
        "  tile_rast tiles   [opts] out.csv    per-tile triangle counts & batches\n"
        "  tile_rast tilehist [opts]           histogram of per-tile load\n"
        "  tile_rast scaling [opts] out.csv    triangle-count scaling sweep\n"
        "opts: --width --height --tile --macro --scene --tris --seed --scale --repeat\n"
        "scenes: clustered | uniform | large | offscreen\n";
}

int parseInt(const char* s, int dflt) {
    try { return std::stoi(s); } catch (...) { return dflt; }
}

float parseFloat(const char* s, float dflt) {
    try { return std::stof(s); } catch (...) { return dflt; }
}

Config parseConfig(int argc, char** argv, int& pos) {
    Config c;
    int firstPositional = argc;
    for (int i = pos; i < argc; ++i) {
        std::string k = argv[i];
        if (k.rfind("--", 0) != 0) {
            firstPositional = std::min(firstPositional, i);
            continue;
        }
        auto next = [&]() -> std::string {
            return i + 1 < argc ? std::string(argv[++i]) : std::string();
        };
        if (k == "--width") c.width = parseInt(next().c_str(), c.width);
        else if (k == "--height") c.height = parseInt(next().c_str(), c.height);
        else if (k == "--tile") c.tile = parseInt(next().c_str(), c.tile);
        else if (k == "--macro") c.macroTiles = parseInt(next().c_str(), c.macroTiles);
        else if (k == "--scene") c.scene = next();
        else if (k == "--tris") c.triangles = parseInt(next().c_str(), c.triangles);
        else if (k == "--seed") c.seed = (unsigned)parseInt(next().c_str(), c.seed);
        else if (k == "--scale") c.triScale = parseFloat(next().c_str(), c.triScale);
        else if (k == "--repeat") c.repeat = parseInt(next().c_str(), c.repeat);
        else std::cerr << "ignoring unknown flag " << k << "\n";
    }
    pos = firstPositional;
    return c;
}

std::string headerLine(const Config& c) {
    std::ostringstream os;
    os << c.width << "x" << c.height << " scene=" << c.scene
       << " tris=" << c.triangles << " scale=" << c.triScale
       << " seed=" << c.seed << " macro=" << c.macroTiles;
    return os.str();
}

void printResult(const char* name, const Result& r) {
    double mb = r.bwTotal / 1e6;
    std::cout << std::left << std::setw(10) << name
              << " time=" << std::fixed << std::setprecision(4)
              << (r.binTime + r.rasterTime) << "s"
              << " submit=" << r.accepted
              << " batches=" << r.batches
              << " emptyTiles=" << r.emptyTiles << "/" << r.totalTiles
              << " BW=" << std::setprecision(2) << mb << " MB\n";
}

void writeTilesCsv(const Result& r, const std::string& path) {
    std::ofstream f(path);
    f << "tx,ty,candidates,accepted,batches,coveredPixels\n";
    for (const TileStat& t : r.tiles)
        f << t.tx << ',' << t.ty << ',' << t.candidates << ','
          << t.accepted << ',' << t.batches << ',' << t.coveredPixels << '\n';
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 2) { usage(); return 1; }
    std::string cmd = argv[1];
    int pos = 2;
    Config cfg = parseConfig(argc, argv, pos);

    if (cmd == "compare") {
        std::cout << "# " << headerLine(cfg) << " tile=" << cfg.tile << "\n";
        auto tris = generateScene(cfg);
        Result imm = runImmediate(tris, cfg);
        Result tiled = runTiled(tris, cfg);
        printResult("immediate", imm);
        printResult("tiled", tiled);
        long long tested = tiled.macroReject + tiled.fineReject + tiled.accepted;
        double cullPct = 100.0 * (1.0 - (double)tiled.accepted /
                                         std::max(1LL, tested));
        std::cout << "candidates=" << tested
                  << " macroReject=" << tiled.macroReject
                  << " fineReject=" << tiled.fineReject
                  << " cullRate=" << std::fixed << std::setprecision(2)
                  << cullPct << "%\n";
        std::cout << std::fixed << std::setprecision(3)
                  << "speedup=" << imm.rasterTime /
                         std::max(1e-9, tiled.binTime + tiled.rasterTime)
                  << "x  BW_ratio_tiled/imm="
                  << (double)tiled.bwTotal / std::max(1LL, imm.bwTotal) << "\n";
        std::cout << "coverageCheck imm=" << imm.coveredPixels
                  << " tiled=" << tiled.coveredPixels << "\n";
        return 0;
    }

    if (cmd == "tiles") {
        std::string out = pos < argc ? argv[pos++] : "tiles.csv";
        auto tris = generateScene(cfg);
        Result tiled = runTiled(tris, cfg);
        writeTilesCsv(tiled, out);
        std::cout << "wrote " << out << " (" << tiled.tiles.size()
                  << " tiles, " << tiled.batches << " batches)\n";
        return 0;
    }

    if (cmd == "tilehist") {
        auto tris = generateScene(cfg);
        Result r = runTiled(tris, cfg);
        int maxLoad = 0;
        for (const TileStat& t : r.tiles) maxLoad = std::max(maxLoad, t.accepted);
        std::vector<int> hist(11, 0);
        long long sumLoad = 0, sumBatch = 0;
        for (const TileStat& t : r.tiles) {
            int bucket = t.accepted == 0 ? 0
                         : std::min(10, 1 + (int)std::log2((double)t.accepted));
            ++hist[bucket];
            sumLoad += t.accepted;
            sumBatch += t.batches;
        }
        std::cout << "# tile=" << cfg.tile << "px tiles=" << r.tiles.size()
                  << " empty=" << r.emptyTiles
                  << " maxTriPerTile=" << maxLoad
                  << " meanTriPerActiveTile="
                  << (double)sumLoad / std::max(1LL, r.totalTiles - r.emptyTiles)
                  << " totalBatches=" << sumBatch << "\n";
        std::cout << "bucket,trisPerTileRange,tiles\n";
        std::cout << "0,0," << hist[0] << "\n";
        for (int i = 1; i < 10; ++i)
            std::cout << i << "," << (1 << (i - 1)) << "-"
                      << ((1 << i) - 1) << "," << hist[i] << "\n";
        std::cout << "10,>=512," << hist[10] << "\n";
        return 0;
    }

    if (cmd == "scaling") {
        std::string out = pos < argc ? argv[pos++] : "scaling.csv";
        std::ofstream f(out);
        f << "tris,totalTiles,emptyTiles,emptyPct,accepted,submissionsPerTri,"
             "batches,macroReject,fineReject,cullPct,binTime,rasterTime,"
             "totalTime,bwMB,immTime,immBWMB,speedup,bwRatio\n";
        const int sizes[7] = {10000, 25000, 50000, 100000,
                              250000, 500000, 1000000};
        for (int n : sizes) {
            Config c2 = cfg;
            c2.triangles = n;
            c2.repeat = 2;
            auto tris = generateScene(c2);
            Result imm = runImmediate(tris, c2);
            Result r = runTiled(tris, c2);
            long long tested = r.macroReject + r.fineReject + r.accepted;
            double cull = 100.0 * (1.0 - (double)r.accepted /
                                           std::max(1LL, tested));
            f << n << ',' << r.totalTiles << ',' << r.emptyTiles << ','
              << (100.0 * r.emptyTiles / std::max(1LL, r.totalTiles)) << ','
              << r.accepted << ','
              << (double)r.accepted / std::max(1LL, r.totalTris) << ','
              << r.batches << ',' << r.macroReject << ',' << r.fineReject
              << ',' << cull << ',' << r.binTime << ',' << r.rasterTime << ','
              << (r.binTime + r.rasterTime) << ',' << r.bwTotal / 1e6 << ','
              << imm.rasterTime << ',' << imm.bwTotal / 1e6 << ','
              << imm.rasterTime /
                     std::max(1e-9, r.binTime + r.rasterTime) << ','
              << (double)r.bwTotal / std::max(1LL, imm.bwTotal) << '\n';
        }
        std::cout << "wrote " << out << "\n";
        return 0;
    }

    if (cmd == "sweep" || cmd == "matrix") {
        std::string out = pos < argc ? argv[pos++] : "sweep.csv";
        std::ofstream f(out);
        if (cmd == "sweep") {
            f << "tile,macroTiles,totalTiles,emptyTiles,accepted,macroReject,"
                 "fineReject,batches,binTime,rasterTime,totalTime,bwMB,cullPct,"
                 "immTime,immBWMB,speedup,bwRatio\n";
            auto tris = generateScene(cfg);
            Result imm = runImmediate(tris, cfg);
            for (int tile : {8, 16, 32, 64, 128, 256}) {
                if (tile > cfg.width || tile > cfg.height) continue;
                Config c2 = cfg;
                c2.tile = tile;
                Result r = runTiled(tris, c2);
                long long tested = r.macroReject + r.fineReject + r.accepted;
                double cull = 100.0 * (1.0 - (double)r.accepted /
                                               std::max(1LL, tested));
                f << tile << ',' << c2.macroTiles << ',' << r.totalTiles << ','
                  << r.emptyTiles << ',' << r.accepted << ',' << r.macroReject
                  << ',' << r.fineReject << ',' << r.batches << ','
                  << r.binTime << ',' << r.rasterTime << ','
                  << (r.binTime + r.rasterTime) << ',' << r.bwTotal / 1e6 << ','
                  << cull << ',' << imm.rasterTime << ',' << imm.bwTotal / 1e6
                  << ',' << imm.rasterTime /
                         std::max(1e-9, r.binTime + r.rasterTime) << ','
                  << (double)r.bwTotal / std::max(1LL, imm.bwTotal) << '\n';
            }
        } else {
            f << "scale,triangleClass,tile,totalTiles,emptyTiles,accepted,"
                 "macroReject,fineReject,batches,totalTime,bwMB,cullPct,"
                 "submissionsPerTri,bwRatioVsImm\n";
            struct Sc { float s; const char* name; };
            const Sc classes[3] = {{0.35f, "small"}, {1.0f, "medium"},
                                   {3.5f, "large"}};
            for (const Sc& sc : classes) {
                Config base = cfg;
                base.triScale = sc.s;
                auto tris = generateScene(base);
                Result imm = runImmediate(tris, base);
                for (int tile : {8, 16, 32, 64, 128, 256}) {
                    if (tile > cfg.width || tile > cfg.height) continue;
                    Config c2 = base;
                    c2.tile = tile;
                    Result r = runTiled(tris, c2);
                    long long tested = r.macroReject + r.fineReject + r.accepted;
                    double cull = 100.0 * (1.0 - (double)r.accepted /
                                                   std::max(1LL, tested));
                    f << sc.s << ',' << sc.name << ',' << tile << ','
                      << r.totalTiles << ',' << r.emptyTiles << ','
                      << r.accepted << ',' << r.macroReject << ','
                      << r.fineReject << ',' << r.batches << ','
                      << (r.binTime + r.rasterTime) << ',' << r.bwTotal / 1e6
                      << ',' << cull << ','
                      << (double)r.accepted / std::max(1LL, r.totalTris) << ','
                      << (double)r.bwTotal / std::max(1LL, imm.bwTotal) << '\n';
                }
            }
        }
        std::cout << "wrote " << out << "\n";
        return 0;
    }

    usage();
    return 1;
}
