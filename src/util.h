#pragma once
#include <cstdint>
#include <cstdio>
#include <cmath>
#include <vector>
#include <string>

struct Vec3 { float x, y, z; };
struct Vec4 { float x, y, z, w; };

static inline Vec3 v3(float x, float y, float z) { return {x, y, z}; }
static inline Vec3 add(Vec3 a, Vec3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
static inline Vec3 sub(Vec3 a, Vec3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
static inline Vec3 mul(Vec3 a, float s) { return {a.x * s, a.y * s, a.z * s}; }
static inline float dot(Vec3 a, Vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static inline Vec3 cross(Vec3 a, Vec3 b) {
    return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}
static inline Vec3 norm(Vec3 a) { float l = std::sqrt(dot(a, a)); return mul(a, 1.0f / l); }

struct Mat4 { float m[16]; }; // column-major

static inline Mat4 mat4Identity() {
    Mat4 r{};
    r.m[0] = r.m[5] = r.m[10] = r.m[15] = 1.0f;
    return r;
}

static inline Mat4 mat4Mul(const Mat4& a, const Mat4& b) {
    Mat4 r{};
    for (int c = 0; c < 4; c++)
        for (int row = 0; row < 4; row++)
            for (int k = 0; k < 4; k++)
                r.m[c * 4 + row] += a.m[k * 4 + row] * b.m[c * 4 + k];
    return r;
}

static inline Mat4 mat4Perspective(float fovY, float aspect, float zn, float zf) {
    Mat4 r{};
    float t = 1.0f / std::tan(fovY * 0.5f);
    r.m[0] = t / aspect;
    r.m[5] = t;
    r.m[10] = zf / (zn - zf);
    r.m[11] = -1.0f;
    r.m[14] = zn * zf / (zn - zf);
    return r;
}

static inline Mat4 mat4LookAt(Vec3 eye, Vec3 center, Vec3 up) {
    Vec3 f = norm(sub(center, eye));
    Vec3 s = norm(cross(f, up));
    Vec3 u = cross(s, f);
    Mat4 r = mat4Identity();
    r.m[0] = s.x;  r.m[4] = s.y;  r.m[8]  = s.z;
    r.m[1] = u.x;  r.m[5] = u.y;  r.m[9]  = u.z;
    r.m[2] = -f.x; r.m[6] = -f.y; r.m[10] = -f.z;
    r.m[12] = -dot(s, eye);
    r.m[13] = -dot(u, eye);
    r.m[14] = dot(f, eye);
    return r;
}

static inline Mat4 mat4Translate(Vec3 t) {
    Mat4 r = mat4Identity();
    r.m[12] = t.x; r.m[13] = t.y; r.m[14] = t.z;
    return r;
}

static inline Mat4 mat4RotateY(float a) {
    Mat4 r = mat4Identity();
    float c = std::cos(a), s = std::sin(a);
    r.m[0] = c; r.m[8] = s; r.m[2] = -s; r.m[10] = c;
    return r;
}

static inline Mat4 mat4RotateX(float a) {
    Mat4 r = mat4Identity();
    float c = std::cos(a), s = std::sin(a);
    r.m[5] = c; r.m[11] = -s; r.m[6] = s; r.m[10] = c;
    return r;
}

static inline Mat4 mat4RotateZ(float a) {
    Mat4 r = mat4Identity();
    float c = std::cos(a), s = std::sin(a);
    r.m[0] = c; r.m[4] = -s; r.m[1] = s; r.m[5] = c;
    return r;
}

static inline Mat4 mat4Scale(float sx, float sy, float sz) {
    Mat4 r = mat4Identity();
    r.m[0] = sx; r.m[5] = sy; r.m[10] = sz;
    return r;
}

// Project world point to pixel coords (viewport uses negative height, y-up NDC).
static inline bool projectPoint(const Mat4& vp, Vec3 p, float w, float h, float& px, float& py) {
    float x = vp.m[0] * p.x + vp.m[4] * p.y + vp.m[8] * p.z + vp.m[12];
    float y = vp.m[1] * p.x + vp.m[5] * p.y + vp.m[9] * p.z + vp.m[13];
    float ww = vp.m[3] * p.x + vp.m[7] * p.y + vp.m[11] * p.z + vp.m[15];
    if (ww <= 1e-6f) return false;
    float nx = x / ww, ny = y / ww;
    px = (nx * 0.5f + 0.5f) * w;
    py = (0.5f - ny * 0.5f) * h;
    return true;
}

// ---------------- minimal PNG writer (RGBA8, zlib stored blocks) ----------------

static inline uint32_t crc32Update(uint32_t crc, const uint8_t* data, size_t len) {
    static uint32_t table[256];
    static bool init = false;
    if (!init) {
        for (uint32_t i = 0; i < 256; i++) {
            uint32_t c = i;
            for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            table[i] = c;
        }
        init = true;
    }
    crc ^= 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) crc = table[(crc ^ data[i]) & 0xFF] ^ (crc >> 8);
    return crc ^ 0xFFFFFFFFu;
}

static inline uint32_t adler32(const uint8_t* data, size_t len) {
    uint32_t a = 1, b = 0;
    for (size_t i = 0; i < len; i++) {
        a = (a + data[i]) % 65521u;
        b = (b + a) % 65521u;
    }
    return (b << 16) | a;
}

static inline void pngChunk(std::vector<uint8_t>& out, const char* type,
                            const uint8_t* data, size_t len) {
    auto put32 = [&](uint32_t v) {
        out.push_back((v >> 24) & 0xFF); out.push_back((v >> 16) & 0xFF);
        out.push_back((v >> 8) & 0xFF); out.push_back(v & 0xFF);
    };
    put32((uint32_t)len);
    size_t typePos = out.size();
    out.insert(out.end(), type, type + 4);
    out.insert(out.end(), data, data + len);
    put32(crc32Update(0, out.data() + typePos, 4 + len));
}

static inline bool writePNG(const std::string& path, int w, int h,
                            const std::vector<uint8_t>& rgba) {
    std::vector<uint8_t> raw;
    raw.reserve((size_t)h * (w * 4 + 1));
    for (int y = 0; y < h; y++) {
        raw.push_back(0); // filter: none
        raw.insert(raw.end(), rgba.begin() + (size_t)y * w * 4,
                   rgba.begin() + (size_t)(y + 1) * w * 4);
    }
    std::vector<uint8_t> z;
    z.push_back(0x78); z.push_back(0x01);
    size_t pos = 0;
    while (pos < raw.size()) {
        size_t n = std::min<size_t>(65535, raw.size() - pos);
        bool last = (pos + n == raw.size());
        z.push_back(last ? 1 : 0);
        z.push_back(n & 0xFF); z.push_back((n >> 8) & 0xFF);
        z.push_back(~n & 0xFF); z.push_back((~n >> 8) & 0xFF);
        z.insert(z.end(), raw.begin() + pos, raw.begin() + pos + n);
        pos += n;
    }
    uint32_t ad = adler32(raw.data(), raw.size());
    z.push_back((ad >> 24) & 0xFF); z.push_back((ad >> 16) & 0xFF);
    z.push_back((ad >> 8) & 0xFF); z.push_back(ad & 0xFF);

    std::vector<uint8_t> png = {0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};
    uint8_t ihdr[13] = {
        (uint8_t)(w >> 24), (uint8_t)(w >> 16), (uint8_t)(w >> 8), (uint8_t)w,
        (uint8_t)(h >> 24), (uint8_t)(h >> 16), (uint8_t)(h >> 8), (uint8_t)h,
        8, 6, 0, 0, 0};
    pngChunk(png, "IHDR", ihdr, 13);
    pngChunk(png, "IDAT", z.data(), z.size());
    pngChunk(png, "IEND", nullptr, 0);
    FILE* f = fopen(path.c_str(), "wb");
    if (!f) return false;
    fwrite(png.data(), 1, png.size(), f);
    fclose(f);
    return true;
}

// ---------------- procedural RGBA atlas (512x512) ----------------
// Region A: x[0,256)   y[0,256)  thin-leaf cluster (fine blades + serration)
// Region B: x[256,512) y[0,256)  perforated metal mesh (circular hole grid)
// Region C: x[0,256)   y[256,512) straight alpha step edge (analytic ground truth)
// Region D: x[256,512) y[256,512) solid white (utility)

static inline std::vector<uint8_t> buildAtlas() {
    const int W = 512, H = 512;
    std::vector<uint8_t> img((size_t)W * H * 4, 0);
    auto put = [&](int x, int y, uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
        size_t i = ((size_t)y * W + x) * 4;
        img[i] = r; img[i + 1] = g; img[i + 2] = b; img[i + 3] = a;
    };
    // Region A: thin leaves. Several tapered curved blades, alpha 1 inside.
    for (int y = 0; y < 256; y++) {
        for (int x = 0; x < 256; x++) {
            float u = x / 255.0f, v = y / 255.0f;
            float alpha = 0.0f, shade = 0.0f;
            for (int blade = 0; blade < 5; blade++) {
                float bu = 0.12f + blade * 0.19f;         // blade base u
                float curve = 0.10f * std::sin(v * 4.0f + blade * 1.7f);
                float halfW = 0.030f * (1.0f - v * 0.85f) + 0.004f; // taper to tip
                float d = std::fabs(u - bu - curve);
                if (d < halfW && v > 0.03f && v < 0.98f) {
                    alpha = 1.0f;
                    float vein = (d < halfW * 0.12f) ? 0.35f : 0.0f; // central vein darker
                    float serr = 0.5f + 0.5f * std::sin(v * 140.0f + blade * 3.0f);
                    if (d > halfW * (0.55f + 0.35f * serr)) alpha = 0.0f; // serrated rim
                    shade = 0.55f + 0.45f * (d / halfW) - vein;
                }
            }
            uint8_t g = (uint8_t)(90 + 110 * shade);
            put(x, y, (uint8_t)(g * 0.45), g, (uint8_t)(g * 0.40), (uint8_t)(alpha * 255));
        }
    }
    // Region B: perforated metal mesh, 8x8 circular holes.
    for (int y = 0; y < 256; y++) {
        for (int x = 256; x < 512; x++) {
            float u = (x - 256) / 255.0f, v = y / 255.0f;
            float cell = 1.0f / 8.0f;
            float cu = (std::fmod(u, cell) - cell * 0.5f) / cell;
            float cv = (std::fmod(v, cell) - cell * 0.5f) / cell;
            float r = std::sqrt(cu * cu + cv * cv);
            float alpha = (r < 0.30f) ? 0.0f : 1.0f; // hole
            float grain = 0.5f + 0.5f * std::sin(u * 40.0f) * std::sin(v * 34.0f);
            float rim = (alpha > 0.5f && r < 0.38f) ? 0.35f : 0.0f; // highlight near hole rim
            uint8_t base = (uint8_t)(120 + 40 * grain + 90 * rim);
            put(x, y, base, (uint8_t)(base * 1.02f), (uint8_t)(base * 1.08f),
                (uint8_t)(alpha * 255));
        }
    }
    // Region C: straight alpha step edge at local v = 0.5 (analytic ground truth).
    for (int y = 256; y < 512; y++) {
        for (int x = 0; x < 256; x++) {
            float v = (y - 256) / 255.0f;
            float alpha = (v < 0.5f) ? 1.0f : 0.0f;
            put(x, y, 230, 60, 160, (uint8_t)(alpha * 255)); // magenta foreground
        }
    }
    // Region D: solid white.
    for (int y = 256; y < 512; y++)
        for (int x = 256; x < 512; x++)
            put(x, y, 255, 255, 255, 255);
    return img;
}
