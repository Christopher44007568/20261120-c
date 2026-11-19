#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

using std::array;
using std::clamp;
using std::cout;
using std::string;
using std::vector;

constexpr float PI = 3.14159265358979323846f;
constexpr float EPS = 1.0e-4f;
constexpr int WIDTH = 480;
constexpr int HEIGHT = 300;
constexpr int SSGI_RAYS = 10;

struct Vec3 {
    float x = 0.0f, y = 0.0f, z = 0.0f;
    Vec3() = default;
    Vec3(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}
    Vec3 operator+(const Vec3& b) const { return {x + b.x, y + b.y, z + b.z}; }
    Vec3 operator-(const Vec3& b) const { return {x - b.x, y - b.y, z - b.z}; }
    Vec3 operator*(float s) const { return {x * s, y * s, z * s}; }
    Vec3 operator*(const Vec3& b) const { return {x * b.x, y * b.y, z * b.z}; }
    Vec3 operator/(float s) const { return {x / s, y / s, z / s}; }
    Vec3& operator+=(const Vec3& b) { x += b.x; y += b.y; z += b.z; return *this; }
    Vec3& operator*=(float s) { x *= s; y *= s; z *= s; return *this; }
};

static float dot(const Vec3& a, const Vec3& b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static float length2(const Vec3& v) { return dot(v, v); }
static float length(const Vec3& v) { return std::sqrt(length2(v)); }
static Vec3 normalize(const Vec3& v) {
    float l = length(v);
    return l > 1.0e-8f ? v / l : Vec3(0, 1, 0);
}
static Vec3 cross(const Vec3& a, const Vec3& b) {
    return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}
static Vec3 clamp01(const Vec3& v) {
    return {clamp(v.x, 0.0f, 1.0f), clamp(v.y, 0.0f, 1.0f), clamp(v.z, 0.0f, 1.0f)};
}
static float luminance(const Vec3& c) { return 0.2126f * c.x + 0.7152f * c.y + 0.0722f * c.z; }

struct Rng {
    uint32_t state;
    explicit Rng(uint32_t seed) : state(seed ? seed : 1u) {}
    uint32_t next() {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        return state;
    }
    float uniform() { return (next() & 0x00ffffffu) / 16777216.0f; }
};

static uint32_t hashU32(uint32_t x) {
    x ^= x >> 16;
    x *= 0x7feb352du;
    x ^= x >> 15;
    x *= 0x846ca68bu;
    x ^= x >> 16;
    return x;
}

static Vec3 sphericalToWorld(const Vec3& n, float u1, float u2) {
    Vec3 helper = std::fabs(n.y) < 0.95f ? Vec3(0, 1, 0) : Vec3(1, 0, 0);
    Vec3 tangent = normalize(cross(helper, n));
    Vec3 bitangent = cross(n, tangent);
    float phi = 2.0f * PI * u1;
    float radius = std::sqrt(u2);
    float z = std::sqrt(std::max(0.0f, 1.0f - u2));
    return normalize(tangent * (std::cos(phi) * radius) +
                     bitangent * (std::sin(phi) * radius) + n * z);
}

struct Ray {
    Vec3 o, d;
};

struct Material {
    Vec3 albedo{0.7f, 0.7f, 0.7f};
    Vec3 emission{0, 0, 0};
};

struct Primitive {
    int type = 0;
    Vec3 lo, hi;
    Vec3 center;
    float radius = 0.0f;
    Material material;
    string name;
    bool dynamic = false;
};

struct Hit {
    bool ok = false;
    float t = std::numeric_limits<float>::max();
    Vec3 p, n;
    int id = -1;
};

struct Camera {
    Vec3 pos{0, 1.55f, 3.7f};
    Vec3 target{0, 1.35f, -1.8f};
    Vec3 up{0, 1, 0};
    float fovDeg = 58.0f;
    Vec3 forward, right, camUp;
    float tanHalf = 0.0f;

    void update() {
        forward = normalize(target - pos);
        right = normalize(cross(forward, up));
        camUp = cross(right, forward);
        tanHalf = std::tan(0.5f * fovDeg * PI / 180.0f);
    }

    Ray ray(float px, float py) const {
        float sx = ((px + 0.5f) / WIDTH * 2.0f - 1.0f) * tanHalf * (float(WIDTH) / HEIGHT);
        float sy = (1.0f - (py + 0.5f) / HEIGHT * 2.0f) * tanHalf;
        Vec3 d = normalize(forward + right * sx + camUp * sy);
        return {pos, d};
    }

    bool project(const Vec3& p, float& px, float& py, float& depth) const {
        Vec3 v = p - pos;
        depth = dot(v, forward);
        if (depth <= 0.01f) return false;
        float x = dot(v, right);
        float y = dot(v, camUp);
        float aspect = float(WIDTH) / HEIGHT;
        px = (x / (depth * tanHalf * aspect) * 0.5f + 0.5f) * WIDTH - 0.5f;
        py = (0.5f - y / (depth * tanHalf) * 0.5f) * HEIGHT - 0.5f;
        return px >= -1.0f && py >= -1.0f && px <= WIDTH && py <= HEIGHT;
    }
};

static bool intersectAabb(const Ray& r, const Primitive& box, float& t, Vec3& n) {
    float tmin = -std::numeric_limits<float>::max();
    float tmax = std::numeric_limits<float>::max();
    int axis = -1;
    for (int i = 0; i < 3; ++i) {
        float o = i == 0 ? r.o.x : (i == 1 ? r.o.y : r.o.z);
        float d = i == 0 ? r.d.x : (i == 1 ? r.d.y : r.d.z);
        float lo = i == 0 ? box.lo.x : (i == 1 ? box.lo.y : box.lo.z);
        float hi = i == 0 ? box.hi.x : (i == 1 ? box.hi.y : box.hi.z);
        if (std::fabs(d) < 1.0e-8f) {
            if (o < lo || o > hi) return false;
            continue;
        }
        float inv = 1.0f / d;
        float t0 = (lo - o) * inv;
        float t1 = (hi - o) * inv;
        if (t0 > t1) std::swap(t0, t1);
        if (t0 > tmin) { tmin = t0; axis = i; }
        tmax = std::min(tmax, t1);
        if (tmax < tmin) return false;
    }
    if (tmax < EPS || tmin < EPS) return false;
    t = tmin;
    if (axis == 0) n = {r.d.x > 0 ? -1.0f : 1.0f, 0, 0};
    else if (axis == 1) n = {0, r.d.y > 0 ? -1.0f : 1.0f, 0};
    else n = {0, 0, r.d.z > 0 ? -1.0f : 1.0f};
    return true;
}

static bool intersectSphere(const Ray& r, const Primitive& s, float& t, Vec3& n) {
    Vec3 oc = r.o - s.center;
    float b = dot(oc, r.d);
    float c = dot(oc, oc) - s.radius * s.radius;
    float disc = b * b - c;
    if (disc < 0.0f) return false;
    float sq = std::sqrt(disc);
    float root = -b - sq;
    if (root < EPS) root = -b + sq;
    if (root < EPS) return false;
    t = root;
    n = normalize(r.o + r.d * t - s.center);
    return true;
}

struct Scene {
    vector<Primitive> objects;
    int lightPanel = -1;
    int dynamicOrb = -1;
};

static Primitive aabb(Vec3 lo, Vec3 hi, Vec3 albedo, const string& name) {
    Primitive p;
    p.type = 0;
    p.lo = lo;
    p.hi = hi;
    p.material.albedo = albedo;
    p.name = name;
    return p;
}

static Primitive sphere(Vec3 center, float radius, Vec3 albedo, const string& name) {
    Primitive p;
    p.type = 1;
    p.center = center;
    p.radius = radius;
    p.material.albedo = albedo;
    p.name = name;
    return p;
}

static Scene buildScene(float orbX, bool showOrb) {
    Scene s;
    s.objects.push_back(aabb({-3.25f, -0.12f, -5.2f}, {3.25f, 0.0f, 4.9f},
                             {0.72f, 0.68f, 0.61f}, "floor"));
    s.objects.push_back(aabb({-3.25f, 0.0f, -5.2f}, {3.25f, 3.55f, -5.0f},
                             {0.76f, 0.73f, 0.67f}, "back_wall"));
    s.objects.push_back(aabb({-3.25f, 0.0f, -5.2f}, {-3.0f, 3.55f, 4.9f},
                             {0.78f, 0.08f, 0.055f}, "red_wall"));
    s.objects.push_back(aabb({3.0f, 0.0f, -5.2f}, {3.25f, 3.55f, 4.9f},
                             {0.055f, 0.66f, 0.14f}, "green_wall"));
    s.objects.push_back(aabb({-3.25f, 3.42f, -5.2f}, {3.25f, 3.56f, 4.9f},
                             {0.83f, 0.81f, 0.76f}, "ceiling"));

    s.objects.push_back(aabb({-1.48f, 0.0f, -2.25f}, {0.15f, 0.63f, -0.72f},
                             {0.88f, 0.87f, 0.83f}, "sofa_base"));
    s.objects.push_back(aabb({-1.48f, 0.63f, -2.25f}, {-1.18f, 1.16f, -0.72f},
                             {0.91f, 0.90f, 0.86f}, "sofa_back"));
    s.objects.push_back(aabb({1.12f, 0.0f, -2.32f}, {2.38f, 0.52f, -1.02f},
                             {0.34f, 0.16f, 0.065f}, "table"));
    s.objects.push_back(aabb({1.22f, 0.52f, -2.22f}, {2.28f, 0.59f, -1.12f},
                             {0.53f, 0.29f, 0.11f}, "table_top"));
    s.objects.push_back(sphere({1.72f, 0.95f, -1.73f}, 0.34f,
                               {0.91f, 0.90f, 0.86f}, "vase"));
    s.objects.push_back(sphere({0.30f, 0.34f, -3.20f}, 0.42f,
                               {0.82f, 0.79f, 0.70f}, "floor_lamp_base"));

    Primitive panel = aabb({-0.82f, 3.36f, -2.10f}, {0.82f, 3.405f, -0.72f},
                           {0.0f, 0.0f, 0.0f}, "area_light");
    panel.material.emission = {8.5f, 7.9f, 6.9f};
    s.lightPanel = int(s.objects.size());
    s.objects.push_back(panel);

    Primitive artRed = aabb({-2.94f, 1.45f, -4.95f}, {-0.18f, 2.55f, -4.88f},
                            {0.82f, 0.18f, 0.08f}, "red_art");
    artRed.material.emission = {0.02f, 0.005f, 0.002f};
    s.objects.push_back(artRed);
    Primitive artGreen = aabb({0.18f, 1.45f, -4.95f}, {2.94f, 2.55f, -4.88f},
                              {0.06f, 0.70f, 0.22f}, "green_art");
    artGreen.material.emission = {0.003f, 0.018f, 0.006f};
    s.objects.push_back(artGreen);

    if (showOrb) {
        Primitive orb = sphere({orbX, 1.20f, -1.65f}, 0.30f,
                               {0.96f, 0.40f, 0.035f}, "projectile_orb");
        orb.material.emission = {3.4f, 0.42f, 0.025f};
        orb.dynamic = true;
        s.dynamicOrb = int(s.objects.size());
        s.objects.push_back(orb);
    }
    return s;
}

static bool intersectScene(const Scene& s, const Ray& r, Hit& out) {
    out = Hit{};
    for (int i = 0; i < int(s.objects.size()); ++i) {
        float t = 0.0f;
        Vec3 n;
        bool hit = s.objects[i].type == 0 ? intersectAabb(r, s.objects[i], t, n)
                                          : intersectSphere(r, s.objects[i], t, n);
        if (hit && t < out.t) {
            out.ok = true;
            out.t = t;
            out.p = r.o + r.d * t;
            out.n = n;
            out.id = i;
        }
    }
    return out.ok;
}

static bool occluded(const Scene& s, const Vec3& origin, const Vec3& target) {
    Vec3 delta = target - origin;
    float dist = length(delta);
    if (dist < EPS) return false;
    Ray shadow{origin + delta / dist * 0.0025f, delta / dist};
    Hit h;
    if (!intersectScene(s, shadow, h)) return false;
    return h.t < dist - EPS * 2.0f;
}

static Vec3 areaLightSample(int index) {
    static const float gx[4] = {0.125f, 0.375f, 0.625f, 0.875f};
    float x = -0.82f + gx[index % 4] * 1.64f;
    float z = -2.10f + gx[(index * 3 + index / 4) % 4] * 1.38f;
    return {x, 3.345f, z};
}

static Vec3 directLighting(const Scene& s, const Hit& h, uint32_t seed) {
    const Material& m = s.objects[h.id].material;
    if (luminance(m.emission) > 0.0f) return m.emission;

    float jitter = (hashU32(seed) & 1023u) / 1024.0f;
    Vec3 sum(0, 0, 0);
    constexpr int samples = 12;
    for (int i = 0; i < samples; ++i) {
        Vec3 lp = areaLightSample((i + int(jitter * 4.0f)) % 4);
        lp.x += (hashU32(seed + i * 17u) & 255u) / 255.0f * 0.08f - 0.04f;
        lp.z += (hashU32(seed + i * 31u) & 255u) / 255.0f * 0.08f - 0.04f;
        Vec3 toLight = lp - h.p;
        float d2 = length2(toLight);
        float dist = std::sqrt(d2);
        Vec3 wi = toLight / dist;
        float ndl = std::max(0.0f, dot(h.n, wi));
        float ndlLight = std::max(0.0f, wi.y);
        if (ndl <= 0.0f || occluded(s, h.p, lp)) continue;
        float attenuation = 1.0f / (0.32f + d2);
        sum += Vec3(8.5f, 7.9f, 6.9f) * (ndl * ndlLight * attenuation);
    }
    sum *= 1.42f / float(samples);
    return m.albedo * sum / PI;
}

struct GBuffer {
    vector<Vec3> pos, normal, albedo, direct, indirect, accum, resolved;
    vector<float> depth;
    vector<int> prim;

    GBuffer() {
        size_t n = size_t(WIDTH) * HEIGHT;
        pos.resize(n);
        normal.resize(n);
        albedo.resize(n, Vec3(0.03f, 0.03f, 0.03f));
        direct.resize(n);
        indirect.resize(n);
        accum.resize(n);
        resolved.resize(n);
        depth.resize(n, 1.0e6f);
        prim.resize(n, -1);
    }
    size_t idx(int x, int y) const { return size_t(y) * WIDTH + x; }
};

static void renderGBuffer(const Scene& s, const Camera& cam, int frame, GBuffer& g) {
    for (int y = 0; y < HEIGHT; ++y) {
        for (int x = 0; x < WIDTH; ++x) {
            size_t i = g.idx(x, y);
            Ray r = cam.ray(float(x), float(y));
            Hit h;
            if (!intersectScene(s, r, h)) {
                g.depth[i] = 1.0e6f;
                g.normal[i] = {0, 1, 0};
                g.prim[i] = -1;
                continue;
            }
            g.pos[i] = h.p;
            g.normal[i] = h.n;
            g.albedo[i] = s.objects[h.id].material.albedo;
            g.depth[i] = dot(h.p - cam.pos, cam.forward);
            g.prim[i] = h.id;
            uint32_t seed = hashU32(uint32_t(i) * 9781u + uint32_t(frame) * 6271u + 17u);
            g.direct[i] = directLighting(s, h, seed);
        }
    }
}

static Vec3 screenIndirect(const Camera& cam, const GBuffer& g, int x, int y,
                           int frame, int samples) {
    size_t src = g.idx(x, y);
    if (g.prim[src] < 0) return {};
    Vec3 n = g.normal[src];
    Vec3 origin = g.pos[src] + n * 0.018f;
    Vec3 sum(0, 0, 0);
    uint32_t pixelSeed = hashU32(uint32_t(src) * 747796405u + uint32_t(frame) * 2891336453u);

    for (int s = 0; s < samples; ++s) {
        uint32_t r0 = hashU32(pixelSeed + uint32_t(s) * 2246822519u);
        uint32_t r1 = hashU32(pixelSeed + uint32_t(s) * 3266489917u + 0x9e3779b9u);
        float u1 = (r0 & 0x00ffffffu) / 16777215.0f;
        float u2 = (r1 & 0x00ffffffu) / 16777216.0f;
        Vec3 dir = sphericalToWorld(n, u1, u2);
        if (dot(dir, n) < 0.0f) dir = dir * -1.0f;

        bool found = false;
        float t = 0.055f;
        for (int step = 0; step < 30; ++step) {
            Vec3 p = origin + dir * t;
            float px, py, rayDepth;
            if (!cam.project(p, px, py, rayDepth)) break;
            int ix = int(std::floor(px + 0.5f));
            int iy = int(std::floor(py + 0.5f));
            if (ix < 0 || iy < 0 || ix >= WIDTH || iy >= HEIGHT) break;
            size_t hi = g.idx(ix, iy);
            float sceneDepth = g.depth[hi];
            float thickness = 0.055f + t * 0.035f;
            if (sceneDepth < 1.0e5f && rayDepth > sceneDepth + thickness &&
                g.prim[hi] != g.prim[src]) {
                Vec3 hitN = g.normal[hi];
                float face = dot(hitN, dir * -1.0f);
                if (face > -0.15f) {
                    float falloff = 1.0f / (1.0f + 0.18f * t * t);
                    float edge = 1.0f;
                    if (px < 3.0f || py < 3.0f || px > WIDTH - 4.0f || py > HEIGHT - 4.0f)
                        edge = 0.35f;
                    sum += g.direct[hi] * (falloff * edge * std::max(0.12f, face + 0.18f));
                    found = true;
                }
                break;
            }
            t += 0.060f + t * 0.050f;
            if (t > 3.6f) break;
        }
        (void)found;
    }
    return g.albedo[src] * (sum / float(samples));
}

static void computeIndirect(const Camera& cam, GBuffer& g, int frame, int samples) {
    for (int y = 0; y < HEIGHT; ++y)
        for (int x = 0; x < WIDTH; ++x)
            g.indirect[g.idx(x, y)] = screenIndirect(cam, g, x, y, frame, samples);
}

enum class HistoryMode { Naive, DepthNormal };

struct TemporalState {
    bool hasHistory = false;
    Camera previousCamera;
    GBuffer previous;
};

struct HistoryTap {
    Vec3 color{};
    float coverage = 0.0f;
};

static HistoryTap sampleReprojectedHistory(const GBuffer& current,
                                            const TemporalState& state, size_t src) {
    HistoryTap result;
    if (!state.hasHistory) return result;
    float px, py, ignoredDepth;
    if (!state.previousCamera.project(current.pos[src], px, py, ignoredDepth)) return result;

    int x0 = int(std::floor(px));
    int y0 = int(std::floor(py));
    float fx = px - float(x0);
    float fy = py - float(y0);
    Vec3 normal = current.normal[src];
    Vec3 expected = current.pos[src];

    for (int dy = 0; dy <= 1; ++dy) {
        for (int dx = 0; dx <= 1; ++dx) {
            int x = x0 + dx;
            int y = y0 + dy;
            if (x < 0 || y < 0 || x >= WIDTH || y >= HEIGHT) continue;
            float wx = dx == 0 ? 1.0f - fx : fx;
            float wy = dy == 0 ? 1.0f - fy : fy;
            float bilinear = wx * wy;
            if (bilinear < 1.0e-4f) continue;
            size_t hi = state.previous.idx(x, y);
            if (state.previous.prim[hi] < 0) continue;
            float expectedDepth = dot(expected - state.previousCamera.pos,
                                      state.previousCamera.forward);
            float tolerance = 0.035f + std::max(0.0f, expectedDepth) * 0.013f;
            if (std::fabs(state.previous.depth[hi] - expectedDepth) > tolerance) continue;
            if (dot(normal, state.previous.normal[hi]) < 0.90f) continue;
            result.color += state.previous.accum[hi] * bilinear;
            result.coverage += bilinear;
        }
    }
    if (result.coverage > 1.0e-4f) result.color = result.color / result.coverage;
    return result;
}

static Vec3 neighborhoodClamp(const GBuffer& g, int x, int y, const Vec3& history) {
    Vec3 mean(0, 0, 0), variance(0, 0, 0);
    int count = 0;
    for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
            int sx = clamp(x + dx, 0, WIDTH - 1);
            int sy = clamp(y + dy, 0, HEIGHT - 1);
            Vec3 c = g.indirect[g.idx(sx, sy)];
            mean += c;
            variance += c * c;
            ++count;
        }
    }
    mean = mean / float(count);
    variance = variance / float(count) - mean * mean;
    Vec3 sigma{std::sqrt(std::max(0.0f, variance.x)),
               std::sqrt(std::max(0.0f, variance.y)),
               std::sqrt(std::max(0.0f, variance.z))};
    constexpr float radius = 2.35f;
    return {clamp(history.x, mean.x - sigma.x * radius, mean.x + sigma.x * radius),
            clamp(history.y, mean.y - sigma.y * radius, mean.y + sigma.y * radius),
            clamp(history.z, mean.z - sigma.z * radius, mean.z + sigma.z * radius)};
}

static void accumulateIndirect(const Camera& cam, GBuffer& current, TemporalState& state,
                               float historyWeight, HistoryMode mode) {
    for (int y = 0; y < HEIGHT; ++y) {
        for (int x = 0; x < WIDTH; ++x) {
            size_t i = current.idx(x, y);
            Vec3 now = current.indirect[i];
            float effectiveHistory = 0.0f;
            Vec3 history = now;
            if (state.hasHistory) {
                if (mode == HistoryMode::Naive) {
                    effectiveHistory = historyWeight;
                    history = state.previous.accum[i];
                } else {
                    HistoryTap tap = sampleReprojectedHistory(current, state, i);
                    if (tap.coverage > 0.05f) {
                        history = neighborhoodClamp(current, x, y, tap.color);
                        float clampConfidence = 0.55f + 0.45f * clamp(tap.coverage, 0.0f, 1.0f);
                        effectiveHistory = historyWeight * clampConfidence;
                    }
                }
            }
            current.accum[i] = now * (1.0f - effectiveHistory) + history * effectiveHistory;
        }
    }
    state.previous = current;
    state.previousCamera = cam;
    state.hasHistory = true;
}

static void bilateralResolve(GBuffer& g) {
    for (int y = 0; y < HEIGHT; ++y) {
        for (int x = 0; x < WIDTH; ++x) {
            size_t center = g.idx(x, y);
            if (g.prim[center] < 0) continue;
            Vec3 sum(0, 0, 0), weightSum(0, 0, 0);
            for (int dy = -2; dy <= 2; ++dy) {
                for (int dx = -2; dx <= 2; ++dx) {
                    int sx = clamp(x + dx, 0, WIDTH - 1);
                    int sy = clamp(y + dy, 0, HEIGHT - 1);
                    size_t sample = g.idx(sx, sy);
                    if (g.prim[sample] != g.prim[center]) continue;
                    float spatial = std::exp(-float(dx * dx + dy * dy) / 5.0f);
                    float dz = std::fabs(g.depth[sample] - g.depth[center]);
                    float depthTol = 0.028f + g.depth[center] * 0.012f;
                    float depthWeight = std::exp(-dz * dz / (2.0f * depthTol * depthTol));
                    float normalWeight = std::pow(std::max(0.0f, dot(g.normal[sample],
                                                                     g.normal[center])), 12.0f);
                    float w = spatial * depthWeight * normalWeight;
                    Vec3 c = g.accum[sample];
                    sum += c * w;
                    weightSum += Vec3(w, w, w);
                }
            }
            g.resolved[center] = {sum.x / std::max(1.0e-4f, weightSum.x),
                                  sum.y / std::max(1.0e-4f, weightSum.y),
                                  sum.z / std::max(1.0e-4f, weightSum.z)};
        }
    }
}

struct FrameTiming {
    int frame = 0;
    double gbufferMs = 0.0;
    double indirectMs = 0.0;
    double accumulationMs = 0.0;
    double totalMs = 0.0;
};

struct RunResult {
    GBuffer final;
    GBuffer jump;
    GBuffer beforeJump;
    vector<Vec3> jumpAccum;
    vector<FrameTiming> timings;
    double meanLuminance = 0.0;
    double staticNoise = 0.0;
    int validStaticPixels = 0;
};

constexpr int JUMP_FRAME = 15;

static RunResult runSequence(float historyWeight, HistoryMode mode, int frameCount,
                             bool recordTimings, bool lightingStep = false) {
    RunResult result;
    TemporalState temporal;
    Camera cam;
    cam.update();
    vector<Vec3> stableSum, stableSumSq;
    int stableSamples = 0;

    for (int frame = 0; frame < frameCount; ++frame) {
        float orbX = lightingStep ? -1.25f : (frame < JUMP_FRAME ? -1.25f : 1.25f);
        Scene scene = buildScene(orbX, true);
        if (lightingStep && frame >= JUMP_FRAME && scene.dynamicOrb >= 0) {
            scene.objects[scene.dynamicOrb].material.emission = {0.055f, 0.012f, 0.002f};
        }
        GBuffer g;

        auto t0 = std::chrono::steady_clock::now();
        renderGBuffer(scene, cam, frame, g);
        auto t1 = std::chrono::steady_clock::now();
        computeIndirect(cam, g, frame, SSGI_RAYS);
        auto t2 = std::chrono::steady_clock::now();
        accumulateIndirect(cam, g, temporal, historyWeight, mode);
        auto t3 = std::chrono::steady_clock::now();

        if (recordTimings) {
            FrameTiming timing;
            timing.frame = frame;
            timing.gbufferMs = std::chrono::duration<double, std::milli>(t1 - t0).count();
            timing.indirectMs = std::chrono::duration<double, std::milli>(t2 - t1).count();
            timing.accumulationMs = std::chrono::duration<double, std::milli>(t3 - t2).count();
            timing.totalMs = std::chrono::duration<double, std::milli>(t3 - t0).count();
            result.timings.push_back(timing);
        }

        if (frame == JUMP_FRAME - 1) result.beforeJump = g;
        if (frame == JUMP_FRAME) {
            result.jump = g;
            result.jumpAccum = g.accum;
        }

        if (frame >= frameCount - 14) {
            if (stableSum.empty()) {
                stableSum = g.accum;
                stableSumSq.resize(g.accum.size(), Vec3(0, 0, 0));
            }
            for (size_t i = 0; i < g.accum.size(); ++i) {
                stableSum[i] += g.accum[i];
                stableSumSq[i] += g.accum[i] * g.accum[i];
            }
            ++stableSamples;
        }
    }

    result.final = temporal.previous;
    if (stableSamples > 0) {
        double noise = 0.0, lum = 0.0;
        int count = 0;
        for (size_t i = 0; i < stableSum.size(); ++i) {
            if (result.final.prim[i] < 0) continue;
            Vec3 mean = stableSum[i] / float(stableSamples);
            Vec3 variance = stableSumSq[i] / float(stableSamples) - mean * mean;
            float sd = std::sqrt(std::max(0.0f, luminance(variance)));
            float m = std::max(1.0e-4f, luminance(mean));
            noise += sd / m;
            lum += m;
            ++count;
        }
        if (count > 0) {
            result.staticNoise = noise / double(count);
            result.meanLuminance = lum / double(count);
            result.validStaticPixels = count;
        }
    }
    return result;
}

static void writeTimingsCsv(const string& path, const vector<FrameTiming>& timings) {
    std::ofstream out(path);
    out << "frame,gbuffer_direct_ms,indirect_ssgi_ms,accumulation_ms,total_ms\n";
    out << std::fixed << std::setprecision(3);
    for (const auto& t : timings) {
        out << t.frame << ',' << t.gbufferMs << ',' << t.indirectMs << ','
            << t.accumulationMs << ',' << t.totalMs << '\n';
    }
}

struct BleedMetrics {
    Vec3 left{}, right{}, center{};
    float leftRedness = 0.0f;
    float rightGreenness = 0.0f;
    float separation = 0.0f;
    float centerNeutrality = 0.0f;
    bool natural = false;
    int leftPixels = 0;
    int rightPixels = 0;
    int centerPixels = 0;
};

static BleedMetrics measureColorBleed(const GBuffer& g) {
    Vec3 left(0, 0, 0), right(0, 0, 0), center(0, 0, 0);
    int leftCount = 0, rightCount = 0, centerCount = 0;
    for (int y = 0; y < HEIGHT; ++y) {
        for (int x = 0; x < WIDTH; ++x) {
            size_t i = g.idx(x, y);
            if (g.prim[i] != 0 || g.normal[i].y < 0.92f) continue;
            Vec3 p = g.pos[i];
            if (p.z < -3.55f || p.z > 2.45f) continue;
            if (p.x >= -3.0f && p.x <= -2.75f) {
                left += g.resolved[i];
                ++leftCount;
            } else if (p.x >= 2.75f && p.x <= 3.0f) {
                right += g.resolved[i];
                ++rightCount;
            } else if (p.x >= -0.50f && p.x <= 0.50f && p.z > 0.15f) {
                center += g.resolved[i];
                ++centerCount;
            }
        }
    }
    BleedMetrics m;
    m.leftPixels = leftCount;
    m.rightPixels = rightCount;
    m.centerPixels = centerCount;
    if (leftCount > 0) m.left = left / float(leftCount);
    if (rightCount > 0) m.right = right / float(rightCount);
    if (centerCount > 0) m.center = center / float(centerCount);
    auto redness = [](const Vec3& c) {
        return (c.x - c.y) / std::max(1.0e-5f, c.x + c.y);
    };
    auto greenness = [](const Vec3& c) {
        return (c.y - c.x) / std::max(1.0e-5f, c.x + c.y);
    };
    m.leftRedness = redness(m.left);
    m.rightGreenness = greenness(m.right);
    m.separation = 0.5f * (m.leftRedness + m.rightGreenness);
    m.centerNeutrality = std::fabs(redness(m.center) - greenness(m.center));
    float asymmetry = std::fabs(m.leftRedness - m.rightGreenness);
    m.natural = m.leftRedness > 0.025f && m.rightGreenness > 0.025f &&
                m.leftRedness < 0.90f && m.rightGreenness < 0.90f && asymmetry < 0.22f;
    return m;
}

static GBuffer makeHighQuality(const Camera& cam, const GBuffer& source, int frame, int samples) {
    GBuffer ref = source;
    computeIndirect(cam, ref, 10000 + frame, samples);
    ref.accum = ref.indirect;
    bilateralResolve(ref);
    return ref;
}

static vector<Vec3> resolveAccum(const GBuffer& source, const vector<Vec3>& accum) {
    GBuffer copy = source;
    copy.accum = accum;
    bilateralResolve(copy);
    return copy.resolved;
}

struct GhostMetrics {
    double normalizedError = 0.0;
    double meanReference = 0.0;
    int maskPixels = 0;
};

static GhostMetrics measureGhost(const vector<Vec3>& accum, const vector<Vec3>& reference,
                                 const vector<uint8_t>& mask) {
    double error = 0.0, refSum = 0.0;
    int count = 0;
    for (size_t i = 0; i < mask.size(); ++i) {
        if (!mask[i]) continue;
        float a = luminance(accum[i]);
        float r = luminance(reference[i]);
        error += std::fabs(a - r);
        refSum += r;
        ++count;
    }
    GhostMetrics m;
    m.maskPixels = count;
    m.meanReference = count > 0 ? refSum / count : 0.0;
    m.normalizedError = count > 0 ? error / std::max(1.0e-5, refSum) : 0.0;
    return m;
}

static Vec3 exposureColor(const Vec3& c, float exposure, float gamma) {
    float r = std::pow(std::max(0.0f, c.x * exposure), 1.0f / gamma);
    float g = std::pow(std::max(0.0f, c.y * exposure), 1.0f / gamma);
    float b = std::pow(std::max(0.0f, c.z * exposure), 1.0f / gamma);
    return {r, g, b};
}

static void writePpm(const string& path, const vector<Vec3>& image,
                     float exposure = 1.0f, float gamma = 2.2f) {
    std::ofstream out(path, std::ios::binary);
    if (!out) {
        std::cerr << "cannot write " << path << "\n";
        std::exit(2);
    }
    out << "P6\n" << WIDTH << " " << HEIGHT << "\n255\n";
    for (const Vec3& raw : image) {
        Vec3 c = clamp01(exposureColor(raw, exposure, gamma));
        unsigned char rgb[3] = {
            static_cast<unsigned char>(c.x * 255.0f + 0.5f),
            static_cast<unsigned char>(c.y * 255.0f + 0.5f),
            static_cast<unsigned char>(c.z * 255.0f + 0.5f)};
        out.write(reinterpret_cast<const char*>(rgb), 3);
    }
}

static vector<Vec3> visualNormalBuffer(const GBuffer& g) {
    vector<Vec3> out(size_t(WIDTH) * HEIGHT);
    for (size_t i = 0; i < out.size(); ++i) out[i] = g.normal[i] * 0.5f + Vec3(0.5f, 0.5f, 0.5f);
    return out;
}

static vector<Vec3> visualDepthBuffer(const GBuffer& g) {
    vector<Vec3> out(size_t(WIDTH) * HEIGHT);
    for (size_t i = 0; i < out.size(); ++i) {
        float d = clamp((g.depth[i] - 0.5f) / 8.5f, 0.0f, 1.0f);
        float v = 1.0f - d;
        out[i] = {v * 0.20f, v * 0.66f, 0.25f + v * 0.65f};
    }
    return out;
}

int main(int argc, char** argv) {
    string outDir = argc > 1 ? argv[1] : "artifacts/raw";
    Camera cam;
    cam.update();
    cout << "Running baseline temporal sequence...\n" << std::flush;
    RunResult baseline = runSequence(0.92f, HistoryMode::DepthNormal, 48, true);
    bilateralResolve(baseline.final);
    writePpm(outDir + "/direct.ppm", baseline.final.direct, 1.0f, 2.2f);
    writePpm(outDir + "/indirect.ppm", baseline.final.resolved, 5.5f, 2.2f);
    writePpm(outDir + "/indirect_pre_resolve.ppm", baseline.final.accum, 5.5f, 2.2f);
    writePpm(outDir + "/indirect_raw.ppm", baseline.final.indirect, 5.5f, 2.2f);
    writePpm(outDir + "/jump_indirect.ppm", baseline.jump.accum, 5.5f, 2.2f);
    writePpm(outDir + "/jump_raw.ppm", baseline.jump.indirect, 5.5f, 2.2f);
    vector<Vec3> composite(baseline.final.direct.size());
    for (size_t i = 0; i < composite.size(); ++i)
        composite[i] = baseline.final.direct[i] + baseline.final.resolved[i];
    writePpm(outDir + "/composite.ppm", composite, 1.05f, 2.2f);
    writePpm(outDir + "/albedo.ppm", baseline.final.albedo, 1.0f, 2.2f);
    writePpm(outDir + "/normal.ppm", visualNormalBuffer(baseline.final), 1.0f, 1.0f);
    writePpm(outDir + "/depth.ppm", visualDepthBuffer(baseline.final), 1.0f, 1.0f);
    writeTimingsCsv(outDir + "/frame_times.csv", baseline.timings);

    cout << "Building high-sample validation references...\n" << std::flush;
    GBuffer ghostReference = makeHighQuality(cam, baseline.jump, JUMP_FRAME, 256);
    GBuffer bleedReference = makeHighQuality(cam, baseline.final, 48, 512);
    BleedMetrics targetBleed = measureColorBleed(bleedReference);

    int orbId = buildScene(0.0f, true).dynamicOrb;
    vector<uint8_t> ghostMask(baseline.jump.accum.size(), 0);
    for (size_t i = 0; i < ghostMask.size(); ++i) {
        if (baseline.beforeJump.prim[i] == orbId && baseline.jump.prim[i] != orbId)
            ghostMask[i] = 1;
    }

    cout << "Building lighting-step ghost reference...\n" << std::flush;
    RunResult lightStepBaseline = runSequence(0.92f, HistoryMode::DepthNormal,
                                              JUMP_FRAME + 2, false, true);
    GBuffer lightStepReference = makeHighQuality(cam, lightStepBaseline.jump, JUMP_FRAME + 60,
                                                 256);
    vector<uint8_t> lightStepMask(baseline.jump.accum.size(), 0);
    for (size_t i = 0; i < lightStepMask.size(); ++i) {
        if (lightStepBaseline.jump.prim[i] == orbId) lightStepMask[i] = 1;
    }

    cout << "Running naive-history ghost control...\n" << std::flush;
    RunResult naive = runSequence(0.92f, HistoryMode::Naive, JUMP_FRAME + 1, false);
    vector<Vec3> proposedGhostImage = resolveAccum(baseline.jump, baseline.jumpAccum);
    vector<Vec3> naiveGhostImage = resolveAccum(naive.jump, naive.jumpAccum);
    GhostMetrics proposedGhost = measureGhost(proposedGhostImage, ghostReference.resolved,
                                               ghostMask);
    GhostMetrics naiveGhost = measureGhost(naiveGhostImage, ghostReference.resolved, ghostMask);
    writePpm(outDir + "/ghost_proposed.ppm", proposedGhostImage, 5.5f, 2.2f);
    writePpm(outDir + "/ghost_naive.ppm", naiveGhostImage, 5.5f, 2.2f);
    writePpm(outDir + "/ghost_reference.ppm", ghostReference.resolved, 5.5f, 2.2f);
    writePpm(outDir + "/bleed_reference.ppm", bleedReference.resolved, 5.5f, 2.2f);
    writePpm(outDir + "/ghost_mask.ppm", [&] {
        vector<Vec3> image(ghostMask.size(), Vec3(0.01f, 0.01f, 0.015f));
        for (size_t i = 0; i < ghostMask.size(); ++i) {
            if (ghostMask[i]) image[i] = {0.95f, 0.18f, 0.02f};
            else if (baseline.jump.prim[i] >= 0) image[i] = baseline.jump.albedo[i] * 0.35f;
        }
        return image;
    }(), 1.0f, 2.2f);

    BleedMetrics baselineBleed = measureColorBleed(baseline.final);
    {
        std::ofstream csv(outDir + "/color_bleed.csv");
        csv << "region,mean_r,mean_g,mean_b,redness,greenness,pixels\n";
        csv << std::fixed << std::setprecision(5);
        csv << "left_floor," << baselineBleed.left.x << ',' << baselineBleed.left.y << ','
            << baselineBleed.left.z << ',' << baselineBleed.leftRedness << ",,"
            << baselineBleed.leftPixels << '\n';
        csv << "right_floor," << baselineBleed.right.x << ',' << baselineBleed.right.y << ','
            << baselineBleed.right.z << ",," << baselineBleed.rightGreenness << ','
            << baselineBleed.rightPixels << '\n';
        csv << "center_floor," << baselineBleed.center.x << ',' << baselineBleed.center.y << ','
            << baselineBleed.center.z << ",,," << baselineBleed.centerPixels << '\n';
        csv << "high_sample_target,0,0,0," << targetBleed.leftRedness << ','
            << targetBleed.rightGreenness << ',' << targetBleed.separation << '\n';
    }

    const vector<float> weights = {0.0f, 0.50f, 0.75f, 0.88f, 0.92f, 0.95f, 0.98f};
    struct SweepRow {
        float weight;
        double noise;
        double ghostAdaptive;
        double ghostNaive;
        double ghostLightStep;
        BleedMetrics bleed;
    };
    vector<SweepRow> rows;
    for (float weight : weights) {
        cout << "History sweep h=" << std::fixed << std::setprecision(2) << weight << "...\n"
             << std::flush;
        RunResult proposed;
        if (std::fabs(weight - 0.92f) < 1.0e-5f) {
            proposed = baseline;
        } else {
            proposed = runSequence(weight, HistoryMode::DepthNormal, 34, false);
            bilateralResolve(proposed.final);
        }
        RunResult rawNaive = runSequence(weight, HistoryMode::Naive, JUMP_FRAME + 1, false);
        vector<Vec3> proposedGhostResolved = resolveAccum(proposed.jump, proposed.jumpAccum);
        vector<Vec3> naiveGhostResolved = resolveAccum(rawNaive.jump, rawNaive.jumpAccum);
        GhostMetrics ga = measureGhost(proposedGhostResolved, ghostReference.resolved, ghostMask);
        GhostMetrics gn = measureGhost(naiveGhostResolved, ghostReference.resolved, ghostMask);
        RunResult lightStep = runSequence(weight, HistoryMode::DepthNormal,
                                          JUMP_FRAME + 2, false, true);
        vector<Vec3> lightStepResolved = resolveAccum(lightStep.jump, lightStep.jumpAccum);
        GhostMetrics gl = measureGhost(lightStepResolved, lightStepReference.resolved,
                                       lightStepMask);
        rows.push_back({weight, proposed.staticNoise, ga.normalizedError,
                        gn.normalizedError, gl.normalizedError,
                        measureColorBleed(proposed.final)});

        std::ostringstream name;
        name << outDir << "/sweep_h" << std::fixed << std::setprecision(2) << weight << ".ppm";
        writePpm(name.str(), proposed.final.resolved, 5.5f, 2.2f);
        std::ostringstream lightName;
        lightName << outDir << "/lightstep_h" << std::fixed << std::setprecision(2)
                  << weight << ".ppm";
        writePpm(lightName.str(), lightStepResolved, 5.5f, 2.2f);
    }

    auto minmax = [](const vector<SweepRow>& data, double SweepRow::*member) {
        double lo = 1.0e30, hi = -1.0e30;
        for (const auto& row : data) {
            lo = std::min(lo, row.*member);
            hi = std::max(hi, row.*member);
        }
        return std::pair<double, double>{lo, hi};
    };
    auto normInv = [](double value, std::pair<double, double> range) {
        if (range.second - range.first < 1.0e-9) return 1.0;
        return 1.0 - (value - range.first) / (range.second - range.first);
    };
    auto noiseRange = minmax(rows, &SweepRow::noise);
    auto lightGhostRange = minmax(rows, &SweepRow::ghostLightStep);
    vector<double> scores;
    for (const auto& row : rows) {
        double naturalScore = row.bleed.natural ? 1.0 : 0.40;
        double separationScore = clamp(row.bleed.separation / 0.75, 0.0, 1.0);
        double bleedScore = 0.70 * naturalScore + 0.30 * separationScore;
        double score = 100.0 * (0.50 * normInv(row.noise, noiseRange) +
                                0.35 * normInv(row.ghostLightStep, lightGhostRange) +
                                0.15 * bleedScore);
        scores.push_back(score);
    }
    int best = int(std::max_element(scores.begin(), scores.end()) - scores.begin());
    {
        std::ofstream csv(outDir + "/history_weight_sweep.csv");
        csv << "history_weight,temporal_noise,ghost_error_adaptive,ghost_error_naive,"
               "ghost_error_lightstep,"
               "bleed_left_redness,bleed_right_greenness,bleed_separation,bleed_natural,"
               "bleed_target,"
               "quality_score,recommended\n";
        csv << std::fixed << std::setprecision(6);
        for (size_t i = 0; i < rows.size(); ++i) {
            const auto& r = rows[i];
            csv << r.weight << ',' << r.noise << ',' << r.ghostAdaptive << ','
                << r.ghostNaive << ',' << r.ghostLightStep << ','
                << r.bleed.leftRedness << ','
                << r.bleed.rightGreenness << ',' << r.bleed.separation << ','
                << (r.bleed.natural ? 1 : 0) << ',' << targetBleed.separation << ','
                << scores[i] << ','
                << (int(i) == best ? 1 : 0) << '\n';
        }
    }
    {
        std::ofstream csv(outDir + "/ghost_metrics.csv");
        csv << "method,history_weight,ghost_error,mask_pixels,mean_reference_luminance\n";
        csv << std::fixed << std::setprecision(6);
        csv << "naive,0.9200," << naiveGhost.normalizedError << ',' << naiveGhost.maskPixels
            << ',' << naiveGhost.meanReference << '\n';
        csv << "depth_normal_adaptive,0.9200," << proposedGhost.normalizedError << ','
            << proposedGhost.maskPixels << ',' << proposedGhost.meanReference << '\n';
    }

    cout << "Color bleed L/R separation: " << std::fixed << std::setprecision(4)
         << baselineBleed.separation << " target " << targetBleed.separation
         << " natural=" << (baselineBleed.natural ? "yes" : "no") << "\n";
    cout << "Ghost error naive/adaptive: " << naiveGhost.normalizedError << " / "
         << proposedGhost.normalizedError << " over " << proposedGhost.maskPixels
         << " pixels\n";
    cout << "Light-step ghost error by weight:";
    for (const auto& row : rows) cout << ' ' << std::setprecision(3) << row.ghostLightStep;
    cout << "\n";
    cout << "Best history weight: " << weights[best] << " score " << scores[best] << "\n";
    return 0;
}


