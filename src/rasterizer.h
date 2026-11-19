#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "math_util.h"

struct Color {
    float r = 1.0f;
    float g = 1.0f;
    float b = 1.0f;
    float a = 1.0f;
};

struct Vertex {
    Vec2 pos;
    Color color;
};

class Framebuffer {
public:
    Framebuffer(int width, int height);

    void clear(const Color& color);

    // Straight-alpha "over" compositing: dst = src over dst.
    void blendPixel(int x, int y, const Color& src);

    void drawTriangle(const Vertex& a, const Vertex& b, const Vertex& c);

    Color readPixel(int x, int y) const;

    bool savePPM(const std::string& path) const;

    int width() const { return width_; }
    int height() const { return height_; }

private:
    int width_;
    int height_;
    std::vector<float> r_;
    std::vector<float> g_;
    std::vector<float> b_;
    std::vector<float> a_;
};

uint8_t toByte(float v);
