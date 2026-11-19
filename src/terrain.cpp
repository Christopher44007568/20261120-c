#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <queue>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

using std::cout;
using std::string;
using std::vector;

constexpr int N = 360;
constexpr float PI = 3.14159265358979323846f;

struct V3 {
    float x = 0, y = 0, z = 0;
    V3() = default;
    V3(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}
};

static float clampf(float v, float lo, float hi) { return std::max(lo, std::min(hi, v)); }

static float sharpPeak(float u, float v, float cx, float cy, float sx, float sy) {
    float dx = (u - cx) / sx;
    float dy = (v - cy) / sy;
    return std::exp(-(dx * dx + dy * dy));
}

static float distanceToSegment(float px, float py, float ax, float ay, float bx, float by) {
    float vx = bx - ax, vy = by - ay;
    float wx = px - ax, wy = py - ay;
    float t = clampf((wx * vx + wy * vy) / (vx * vx + vy * vy), 0.0f, 1.0f);
    float dx = px - (ax + vx * t);
    float dy = py - (ay + vy * t);
    return std::sqrt(dx * dx + dy * dy);
}

struct PathSegment {
    float ax, ay, bx, by, depth, width;
};

static float valleyCarve(float u, float v, const vector<PathSegment>& paths) {
    float carve = 0.0f;
    for (const auto& p : paths) {
        float d = distanceToSegment(u, v, p.ax, p.ay, p.bx, p.by);
        carve = std::max(carve, p.depth * std::exp(-0.5f * (d / p.width) * (d / p.width)));
    }
    return carve;
}

static vector<float> makeHeightfield(const vector<PathSegment>& paths) {
    vector<float> h(size_t(N) * N);
    for (int y = 0; y < N; ++y) {
        for (int x = 0; x < N; ++x) {
            float u = float(x) / (N - 1);
            float v = float(y) / (N - 1);
            float elevation = 92.0f * (1.0f - v);
            elevation += 32.0f * sharpPeak(u, v, 0.51f, 0.24f, 0.16f, 0.22f);
            elevation += 20.0f * sharpPeak(u, v, 0.18f, 0.34f, 0.14f, 0.22f);
            elevation += 23.0f * sharpPeak(u, v, 0.83f, 0.36f, 0.13f, 0.24f);
            elevation += 9.0f * sharpPeak(u, v, 0.50f, 0.50f, 0.08f, 0.30f);
            elevation += 2.4f * std::sin(2.0f * PI * (3.0f * u + 1.1f * v)) *
                         std::sin(2.0f * PI * (1.7f * u - 2.6f * v));
            elevation += 1.1f * std::sin(2.0f * PI * (8.0f * u + 3.0f * v));
            elevation -= valleyCarve(u, v, paths);
            h[size_t(y) * N + x] = elevation;
        }
    }
    return h;
}

struct FilledSurface {
    vector<float> height;
    vector<int> parent;
};

static FilledSurface fillDepressions(const vector<float>& source) {
    FilledSurface result;
    result.height = source;
    result.parent.assign(source.size(), -1);
    vector<uint8_t> visited(source.size(), 0);
    using Item = std::pair<float, int>;
    std::priority_queue<Item, vector<Item>, std::greater<Item>> queue;
    const int dx[8] = {-1, 0, 1, -1, 1, -1, 0, 1};
    const int dy[8] = {-1, -1, -1, 0, 0, 1, 1, 1};

    auto seed = [&](int x, int y) {
        int i = y * N + x;
        if (!visited[i]) {
            visited[i] = 1;
            queue.push({source[i], i});
        }
    };
    for (int x = 0; x < N; ++x) { seed(x, 0); seed(x, N - 1); }
    for (int y = 1; y < N - 1; ++y) { seed(0, y); seed(N - 1, y); }

    while (!queue.empty()) {
        auto [level, index] = queue.top();
        queue.pop();
        int x = index % N;
        int y = index / N;
        for (int k = 0; k < 8; ++k) {
            int nx = x + dx[k];
            int ny = y + dy[k];
            if (nx < 0 || ny < 0 || nx >= N || ny >= N) continue;
            int ni = ny * N + nx;
            if (visited[ni]) continue;
            visited[ni] = 1;
            result.height[ni] = std::max(source[ni], level + 0.0015f);
            result.parent[ni] = index;
            queue.push({result.height[ni], ni});
        }
    }
    return result;
}

struct Hydrology {
    vector<float> elevation;
    vector<int> downstream;
    vector<float> accumulated;
    vector<float> slope;
    vector<int> donorCount;
    vector<int> order;
};

static Hydrology computeHydrology(const vector<float>& source) {
    FilledSurface filled = fillDepressions(source);
    Hydrology h;
    h.elevation = filled.height;
    size_t count = source.size();
    h.downstream.assign(count, -1);
    h.accumulated.assign(count, 1.0f);
    h.slope.assign(count, 0.0f);
    h.donorCount.assign(count, 0);
    h.order.resize(count);
    for (size_t i = 0; i < count; ++i) h.order[i] = int(i);

    const int dx[8] = {-1, 0, 1, -1, 1, -1, 0, 1};
    const int dy[8] = {-1, -1, -1, 0, 0, 1, 1, 1};
    const float dist[8] = {1.41421356f, 1.0f, 1.41421356f, 1.0f,
                           1.0f, 1.41421356f, 1.0f, 1.41421356f};
    for (int y = 0; y < N; ++y) {
        for (int x = 0; x < N; ++x) {
            int i = y * N + x;
            bool boundary = x == 0 || y == 0 || x == N - 1 || y == N - 1;
            if (boundary) continue;
            float best = 0.0f;
            int bestNeighbor = -1;
            for (int k = 0; k < 8; ++k) {
                int nx = x + dx[k];
                int ny = y + dy[k];
                int ni = ny * N + nx;
                float s = (h.elevation[i] - h.elevation[ni]) / dist[k];
                if (s > best) {
                    best = s;
                    bestNeighbor = ni;
                }
            }
            h.downstream[i] = bestNeighbor;
            h.slope[i] = best;
            if (bestNeighbor >= 0) h.donorCount[bestNeighbor]++;
        }
    }

    std::sort(h.order.begin(), h.order.end(), [&](int a, int b) {
        if (h.elevation[a] != h.elevation[b]) return h.elevation[a] > h.elevation[b];
        return a < b;
    });
    for (int i : h.order) {
        int d = h.downstream[i];
        if (d >= 0) h.accumulated[d] += h.accumulated[i];
    }
    return h;
}

static void writePpm(const string& path, int width, int height, const vector<V3>& image) {
    std::ofstream out(path, std::ios::binary);
    if (!out) {
        std::cerr << "cannot write " << path << "\n";
        std::exit(2);
    }
    out << "P6\n" << width << " " << height << "\n255\n";
    for (const V3& c : image) {
        unsigned char rgb[3] = {
            static_cast<unsigned char>(clampf(c.x, 0, 1) * 255.0f + 0.5f),
            static_cast<unsigned char>(clampf(c.y, 0, 1) * 255.0f + 0.5f),
            static_cast<unsigned char>(clampf(c.z, 0, 1) * 255.0f + 0.5f)};
        out.write(reinterpret_cast<const char*>(rgb), 3);
    }
}

static V3 terrainBaseColor(float t) {
    V3 low(0.21f, 0.34f, 0.18f);
    V3 mid(0.43f, 0.36f, 0.22f);
    V3 high(0.68f, 0.67f, 0.61f);
    if (t < 0.55f) {
        float b = t / 0.55f;
        return {low.x + (mid.x - low.x) * b,
                low.y + (mid.y - low.y) * b,
                low.z + (mid.z - low.z) * b};
    }
    float b = (t - 0.55f) / 0.45f;
    return {mid.x + (high.x - mid.x) * b,
            mid.y + (high.y - mid.y) * b,
            mid.z + (high.z - mid.z) * b};
}

struct Analysis {
    float riverThreshold = 1.0f;
    float maxAccumulation = 1.0f;
    int riverCells = 0;
    int interiorCells = 0;
    int downhillCells = 0;
    int confluenceCells = 0;
    int correctConfluenceCells = 0;
    int conservationCells = 0;
    int correctConservationCells = 0;
    vector<int> majorConfluences;
    vector<int> valleyWaypoints;
};

static vector<int> findConfluences(const Hydrology& h, float threshold) {
    vector<int> points;
    for (int i = 0; i < N * N; ++i) {
        if (h.accumulated[i] >= threshold && h.donorCount[i] >= 2)
            points.push_back(i);
    }
    std::sort(points.begin(), points.end(), [&](int a, int b) {
        return h.accumulated[a] > h.accumulated[b];
    });
    vector<int> selected;
    for (int p : points) {
        int px = p % N;
        int py = p / N;
        bool close = false;
        for (int q : selected) {
            int qx = q % N;
            int qy = q / N;
            if ((px - qx) * (px - qx) + (py - qy) * (py - qy) < 34 * 34) {
                close = true;
                break;
            }
        }
        if (!close) selected.push_back(p);
        if (selected.size() >= 8) break;
    }
    return selected;
}

static int largestOutlet(const Hydrology& h) {
    int best = -1;
    float bestFlow = -1.0f;
    for (int y = 0; y < N; ++y) {
        for (int x = 0; x < N; ++x) {
            if (x != 0 && y != 0 && x != N - 1 && y != N - 1) continue;
            int i = y * N + x;
            if (h.accumulated[i] > bestFlow) {
                bestFlow = h.accumulated[i];
                best = i;
            }
        }
    }
    return best;
}

static vector<int> traceMainValley(const Hydrology& h) {
    vector<int> path;
    int current = largestOutlet(h);
    vector<uint8_t> seen(size_t(N) * N, 0);
    while (current >= 0 && !seen[current]) {
        seen[current] = 1;
        path.push_back(current);
        int x = current % N;
        int y = current / N;
        int best = -1;
        float bestFlow = -1.0f;
        for (int dy = -1; dy <= 1; ++dy) {
            for (int dx = -1; dx <= 1; ++dx) {
                if (dx == 0 && dy == 0) continue;
                int nx = x + dx, ny = y + dy;
                if (nx < 0 || ny < 0 || nx >= N || ny >= N) continue;
                int ni = ny * N + nx;
                if (h.downstream[ni] != current) continue;
                if (h.accumulated[ni] > bestFlow) {
                    bestFlow = h.accumulated[ni];
                    best = ni;
                }
            }
        }
        current = best;
    }
    return path;
}

static Analysis analyze(const Hydrology& h, float threshold) {
    Analysis a;
    a.riverThreshold = threshold;
    for (int i = 0; i < N * N; ++i) {
        a.maxAccumulation = std::max(a.maxAccumulation, h.accumulated[i]);
        if (h.accumulated[i] >= threshold) ++a.riverCells;
        int x = i % N, y = i / N;
        if (x > 0 && y > 0 && x < N - 1 && y < N - 1) {
            ++a.interiorCells;
            if (h.downstream[i] >= 0 &&
                h.elevation[i] > h.elevation[h.downstream[i]] + 1.0e-7f)
                ++a.downhillCells;
            float inflow = 1.0f;
            for (int dy = -1; dy <= 1; ++dy) {
                for (int dx = -1; dx <= 1; ++dx) {
                    if (dx == 0 && dy == 0) continue;
                    int ni = (y + dy) * N + (x + dx);
                    if (h.downstream[ni] == i) inflow += h.accumulated[ni];
                }
            }
            ++a.conservationCells;
            if (std::fabs(inflow - h.accumulated[i]) < 1.0e-3f * std::max(1.0f, inflow))
                ++a.correctConservationCells;
        }
        if (h.accumulated[i] >= threshold && h.donorCount[i] >= 2) {
            ++a.confluenceCells;
            bool downhill = h.downstream[i] < 0 ||
                            h.elevation[i] > h.elevation[h.downstream[i]];
            if (downhill) ++a.correctConfluenceCells;
        }
    }
    a.majorConfluences = findConfluences(h, threshold * 3.0f);
    vector<int> path = traceMainValley(h);
    int step = std::max(1, int(path.size()) / 14);
    for (size_t i = 0; i < path.size(); i += size_t(step)) a.valleyWaypoints.push_back(path[i]);
    if (!path.empty() && (a.valleyWaypoints.empty() || a.valleyWaypoints.back() != path.back()))
        a.valleyWaypoints.push_back(path.back());
    return a;
}

static void drawMarker(vector<V3>& image, int x, int y, V3 color, int radius = 2) {
    for (int dy = -radius; dy <= radius; ++dy) {
        for (int dx = -radius; dx <= radius; ++dx) {
            int sx = x + dx, sy = y + dy;
            if (sx < 0 || sy < 0 || sx >= N || sy >= N) continue;
            if (std::abs(dx) + std::abs(dy) > radius + 1) continue;
            image[size_t(sy) * N + sx] = color;
        }
    }
}

static void renderMaps(const Hydrology& h, const Analysis& a, const string& outDir) {
    vector<V3> base(size_t(N) * N), hydrology(size_t(N) * N), flowMap(size_t(N) * N),
        slopeMap(size_t(N) * N);
    float lo = h.elevation[0], hi = h.elevation[0];
    for (float e : h.elevation) {
        lo = std::min(lo, e);
        hi = std::max(hi, e);
    }
    V3 light = [] {
        V3 v(-0.62f, -0.58f, 0.54f);
        float l = std::sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
        return V3(v.x / l, v.y / l, v.z / l);
    }();
    float cellX = 1800.0f / (N - 1);
    float cellY = 2400.0f / (N - 1);

    for (int y = 0; y < N; ++y) {
        for (int x = 0; x < N; ++x) {
            int i = y * N + x;
            int xm = std::max(1, x - 1), xp = std::min(N - 2, x + 1);
            int ym = std::max(1, y - 1), yp = std::min(N - 2, y + 1);
            float dzdx = (h.elevation[y * N + xp] - h.elevation[y * N + xm]) / (2.0f * cellX);
            float dzdy = (h.elevation[yp * N + x] - h.elevation[ym * N + x]) / (2.0f * cellY);
            V3 normal(-dzdx * 6.0f, -dzdy * 6.0f, 1.0f);
            float nl = std::sqrt(normal.x * normal.x + normal.y * normal.y + normal.z * normal.z);
            normal = V3(normal.x / nl, normal.y / nl, normal.z / nl);
            float shade = clampf(normal.x * light.x + normal.y * light.y + normal.z * light.z,
                                 0.22f, 1.0f);
            if ((x % 45 == 0) || (y % 45 == 0)) shade *= 0.86f;
            float t = (h.elevation[i] - lo) / std::max(0.001f, hi - lo);
            V3 color = terrainBaseColor(t);
            base[i] = {color.x * shade, color.y * shade, color.z * shade};
            hydrology[i] = base[i];
            flowMap[i] = {base[i].x * 0.55f, base[i].y * 0.55f, base[i].z * 0.55f};
            float sn = clampf(h.slope[i] / 2.2f, 0.0f, 1.0f);
            slopeMap[i] = {0.12f + 0.80f * sn, 0.28f + 0.38f * (1.0f - sn),
                           0.18f + 0.30f * (1.0f - sn)};
        }
    }

    for (int y = 0; y < N; ++y) {
        for (int x = 0; x < N; ++x) {
            int i = y * N + x;
            if (h.accumulated[i] < a.riverThreshold) continue;
            float strength = clampf(std::log(h.accumulated[i] / a.riverThreshold) /
                                    std::log(std::max(2.0f, a.maxAccumulation / a.riverThreshold)),
                                    0.0f, 1.0f);
            V3 river(0.035f + 0.04f * strength, 0.28f + 0.28f * strength,
                     0.78f + 0.18f * strength);
            int width = h.accumulated[i] > a.riverThreshold * 6.0f ? 2 : 1;
            for (int dy = -width; dy <= width; ++dy) {
                for (int dx = -width; dx <= width; ++dx) {
                    int sx = x + dx, sy = y + dy;
                    if (sx < 0 || sy < 0 || sx >= N || sy >= N) continue;
                    hydrology[size_t(sy) * N + sx] = river;
                }
            }
            flowMap[i] = {0.03f + 0.92f * strength, 0.30f + 0.60f * strength,
                          0.42f + 0.55f * strength};
            slopeMap[i] = {0.08f, 0.48f + 0.22f * strength, 0.90f};
        }
    }

    for (int point : a.valleyWaypoints) {
        drawMarker(hydrology, point % N, point / N, {1.0f, 0.90f, 0.12f}, 1);
    }
    for (int point : a.majorConfluences) {
        drawMarker(hydrology, point % N, point / N, {1.0f, 0.18f, 0.04f}, 2);
    }
    writePpm(outDir + "/terrain_base.ppm", N, N, base);
    writePpm(outDir + "/terrain_hydrology.ppm", N, N, hydrology);
    writePpm(outDir + "/terrain_flow.ppm", N, N, flowMap);
    writePpm(outDir + "/terrain_slope.ppm", N, N, slopeMap);
}

static void writeNetworkCsv(const Hydrology& h, const Analysis& a, const string& outDir) {
    std::ofstream river(outDir + "/river_network.csv");
    river << "px,py,x_m,y_m,elevation_m,flow_cells,slope,downstream_px,downstream_py\n";
    river << std::fixed << std::setprecision(4);
    for (int y = 0; y < N; ++y) {
        for (int x = 0; x < N; ++x) {
            int i = y * N + x;
            if (h.accumulated[i] < a.riverThreshold) continue;
            int d = h.downstream[i];
            int dx = d >= 0 ? d % N : -1;
            int dy = d >= 0 ? d / N : -1;
            river << x << ',' << y << ',' << (x * 1800.0f / (N - 1)) << ','
                  << (y * 2400.0f / (N - 1)) << ',' << h.elevation[i] << ','
                  << h.accumulated[i] << ',' << h.slope[i] << ',' << dx << ',' << dy << '\n';
        }
    }

    std::ofstream valleys(outDir + "/valleys.csv");
    valleys << "id,type,px,py,x_m,y_m,elevation_m,flow_cells\n";
    valleys << std::fixed << std::setprecision(4);
    int id = 1;
    for (int p : a.majorConfluences) {
        int x = p % N, y = p / N;
        valleys << id++ << ",confluence," << x << ',' << y << ','
                << (x * 1800.0f / (N - 1)) << ',' << (y * 2400.0f / (N - 1)) << ','
                << h.elevation[p] << ',' << h.accumulated[p] << '\n';
    }
    for (int p : a.valleyWaypoints) {
        int x = p % N, y = p / N;
        valleys << id++ << ",trunk," << x << ',' << y << ','
                << (x * 1800.0f / (N - 1)) << ',' << (y * 2400.0f / (N - 1)) << ','
                << h.elevation[p] << ',' << h.accumulated[p] << '\n';
    }
}

static void writeAnalysisJson(const Hydrology& h, const Analysis& a, const string& outDir) {
    int outlet = largestOutlet(h);
    auto pct = [](int good, int total) {
        return total > 0 ? 100.0 * double(good) / double(total) : 0.0;
    };
    std::ofstream out(outDir + "/terrain_analysis.json");
    out << std::fixed << std::setprecision(5);
    out << "{\n";
    out << "  \"grid\": " << N << ",\n";
    out << "  \"domain_m\": [1800.0, 2400.0],\n";
    out << "  \"river_threshold_cells\": " << a.riverThreshold << ",\n";
    out << "  \"river_cells\": " << a.riverCells << ",\n";
    out << "  \"max_accumulation_cells\": " << a.maxAccumulation << ",\n";
    out << "  \"downhill_ratio_percent\": " << pct(a.downhillCells, a.interiorCells) << ",\n";
    out << "  \"flow_conservation_ratio_percent\": "
        << pct(a.correctConservationCells, a.conservationCells) << ",\n";
    out << "  \"confluence_cells\": " << a.confluenceCells << ",\n";
    out << "  \"confluence_correct_ratio_percent\": "
        << pct(a.correctConfluenceCells, a.confluenceCells) << ",\n";
    out << "  \"outlet\": {\"px\": " << outlet % N << ", \"py\": " << outlet / N
        << ", \"x_m\": " << ((outlet % N) * 1800.0f / (N - 1))
        << ", \"y_m\": " << ((outlet / N) * 2400.0f / (N - 1))
        << ", \"elevation_m\": " << h.elevation[outlet]
        << ", \"flow_cells\": " << h.accumulated[outlet] << "},\n";
    out << "  \"confluences\": [\n";
    for (size_t i = 0; i < a.majorConfluences.size(); ++i) {
        int p = a.majorConfluences[i];
        int x = p % N, y = p / N;
        float inflow = 0.0f;
        int branches = 0;
        for (int dy = -1; dy <= 1; ++dy) {
            for (int dx = -1; dx <= 1; ++dx) {
                if (dx == 0 && dy == 0) continue;
                int ni = (y + dy) * N + (x + dx);
                if (h.downstream[ni] == p) {
                    inflow += h.accumulated[ni];
                    ++branches;
                }
            }
        }
        out << "    {\"id\": " << i + 1 << ", \"px\": " << x << ", \"py\": " << y
            << ", \"x_m\": " << (x * 1800.0f / (N - 1))
            << ", \"y_m\": " << (y * 2400.0f / (N - 1))
            << ", \"elevation_m\": " << h.elevation[p]
            << ", \"flow_cells\": " << h.accumulated[p]
            << ", \"upstream_branches\": " << branches
            << ", \"upstream_flow_sum\": " << inflow
            << ", \"downstream_drop_m\": "
            << (h.downstream[p] >= 0 ? h.elevation[p] - h.elevation[h.downstream[p]] : 0.0f)
            << "}" << (i + 1 < a.majorConfluences.size() ? "," : "") << "\n";
    }
    out << "  ],\n";
    out << "  \"valley_waypoints\": [\n";
    for (size_t i = 0; i < a.valleyWaypoints.size(); ++i) {
        int p = a.valleyWaypoints[i];
        int x = p % N, y = p / N;
        out << "    {\"id\": " << i + 1 << ", \"px\": " << x << ", \"py\": " << y
            << ", \"x_m\": " << (x * 1800.0f / (N - 1))
            << ", \"y_m\": " << (y * 2400.0f / (N - 1))
            << ", \"elevation_m\": " << h.elevation[p]
            << ", \"flow_cells\": " << h.accumulated[p] << "}"
            << (i + 1 < a.valleyWaypoints.size() ? "," : "") << "\n";
    }
    out << "  ]\n";
    out << "}\n";
}

int main(int argc, char** argv) {
    string outDir = argc > 1 ? argv[1] : "artifacts/raw";
    vector<PathSegment> paths = {
        {0.19f, 0.06f, 0.44f, 0.70f, 19.0f, 0.038f},
        {0.84f, 0.05f, 0.56f, 0.70f, 19.0f, 0.038f},
        {0.44f, 0.70f, 0.53f, 1.02f, 23.0f, 0.050f},
        {0.56f, 0.70f, 0.53f, 1.02f, 23.0f, 0.050f},
    };
    vector<float> source = makeHeightfield(paths);
    float minimum = *std::min_element(source.begin(), source.end());
    for (float& value : source) value += 8.0f - minimum;
    Hydrology h = computeHydrology(source);
    float threshold = argc > 2 ? std::atof(argv[2]) : 350.0f;
    Analysis analysis = analyze(h, threshold);
    renderMaps(h, analysis, outDir);
    writeNetworkCsv(h, analysis, outDir);
    writeAnalysisJson(h, analysis, outDir);

    int outlet = largestOutlet(h);
    cout << "Terrain grid: " << N << " x " << N << "\n";
    cout << "River cells: " << analysis.riverCells << "\n";
    cout << "Downhill ratio: " << std::fixed << std::setprecision(3)
         << (100.0 * analysis.downhillCells / std::max(1, analysis.interiorCells)) << "%\n";
    cout << "Flow conservation ratio: "
         << (100.0 * analysis.correctConservationCells /
             std::max(1, analysis.conservationCells)) << "%\n";
    cout << "Confluence correctness: "
         << (100.0 * analysis.correctConfluenceCells /
             std::max(1, analysis.confluenceCells)) << "% over "
         << analysis.confluenceCells << " cells\n";
    cout << "Main outlet: (" << outlet % N << ", " << outlet / N
         << ") flow=" << h.accumulated[outlet] << "\n";
    return 0;
}



