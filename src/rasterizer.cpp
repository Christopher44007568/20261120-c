#include "rasterizer.h"

#include <algorithm>
#include <cmath>
#include <fstream>

uint8_t toByte(float v) {
    return static_cast<uint8_t>(std::lround(clamp01(v) * 255.0f));
}

Framebuffer::Framebuffer(int width, int height)
    : width_(width), height_(height),
      r_(static_cast<size_t>(width) * height, 0.0f),
      g_(static_cast<size_t>(width) * height, 0.0f),
      b_(static_cast<size_t>(width) * height, 0.0f),
      a_(static_cast<size_t>(width) * height, 0.0f) {}

void Framebuffer::clear(const Color& color) {
    std::fill(r_.begin(), r_.end(), color.r);
    std::fill(g_.begin(), g_.end(), color.g);
    std::fill(b_.begin(), b_.end(), color.b);
    std::fill(a_.begin(), a_.end(), color.a);
}

Color Framebuffer::readPixel(int x, int y) const {
    size_t idx = static_cast<size_t>(y) * static_cast<size_t>(width_) +
                 static_cast<size_t>(x);
    return {r_[idx], g_[idx], b_[idx], a_[idx]};
}

void Framebuffer::blendPixel(int x, int y, const Color& src) {
    if (x < 0 || y < 0 || x >= width_ || y >= height_ || src.a <= 0.0f) {
        return;
    }
    size_t idx = static_cast<size_t>(y) * static_cast<size_t>(width_) +
                 static_cast<size_t>(x);
    float sa = clamp01(src.a);
    float da = a_[idx];
    float outA = sa + da * (1.0f - sa);
    if (outA <= 1e-7f) {
        r_[idx] = g_[idx] = b_[idx] = a_[idx] = 0.0f;
        return;
    }
    float inv = 1.0f / outA;
    r_[idx] = (src.r * sa + r_[idx] * da * (1.0f - sa)) * inv;
    g_[idx] = (src.g * sa + g_[idx] * da * (1.0f - sa)) * inv;
    b_[idx] = (src.b * sa + b_[idx] * da * (1.0f - sa)) * inv;
    a_[idx] = outA;
}

static float edgeFn(const Vec2& a, const Vec2& b, const Vec2& p) {
    return (p.x - a.x) * (b.y - a.y) - (p.y - a.y) * (b.x - a.x);
}

void Framebuffer::drawTriangle(const Vertex& va, const Vertex& vb,
                               const Vertex& vc) {
    float area = edgeFn(va.pos, vb.pos, vc.pos);
    if (std::abs(area) <= 1e-9f) {
        return;
    }
    float minXf = std::min({va.pos.x, vb.pos.x, vc.pos.x});
    float maxXf = std::max({va.pos.x, vb.pos.x, vc.pos.x});
    float minYf = std::min({va.pos.y, vb.pos.y, vc.pos.y});
    float maxYf = std::max({va.pos.y, vb.pos.y, vc.pos.y});
    int minX = std::max(0, static_cast<int>(std::floor(minXf)));
    int maxX = std::min(width_ - 1, static_cast<int>(std::ceil(maxXf)));
    int minY = std::max(0, static_cast<int>(std::floor(minYf)));
    int maxY = std::min(height_ - 1, static_cast<int>(std::ceil(maxYf)));
    float invArea = 1.0f / area;

    for (int y = minY; y <= maxY; ++y) {
        for (int x = minX; x <= maxX; ++x) {
            Vec2 sample{static_cast<float>(x) + 0.5f,
                        static_cast<float>(y) + 0.5f};
            float w0 = edgeFn(vb.pos, vc.pos, sample) * invArea;
            float w1 = edgeFn(vc.pos, va.pos, sample) * invArea;
            float w2 = edgeFn(va.pos, vb.pos, sample) * invArea;
            if (w0 < 0.0f || w1 < 0.0f || w2 < 0.0f) {
                continue;
            }
            Color c;
            c.r = w0 * va.color.r + w1 * vb.color.r + w2 * vc.color.r;
            c.g = w0 * va.color.g + w1 * vb.color.g + w2 * vc.color.g;
            c.b = w0 * va.color.b + w1 * vb.color.b + w2 * vc.color.b;
            c.a = w0 * va.color.a + w1 * vb.color.a + w2 * vc.color.a;
            blendPixel(x, y, c);
        }
    }
}

bool Framebuffer::savePPM(const std::string& path) const {
    std::ofstream out(path, std::ios::binary);
    if (!out) {
        return false;
    }
    out << "P6\n" << width_ << ' ' << height_ << "\n255\n";
    for (int i = 0; i < width_ * height_; ++i) {
        uint8_t px[3] = {toByte(r_[i]), toByte(g_[i]), toByte(b_[i])};
        out.write(reinterpret_cast<const char*>(px), 3);
    }
    return static_cast<bool>(out);
}
