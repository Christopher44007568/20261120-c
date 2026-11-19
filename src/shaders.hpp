#pragma once

namespace hzb {

inline constexpr const char* kDepthVertexShader = R"GLSL(
#version 450 core
layout(location = 0) in vec3 aPosition;
uniform mat4 uViewProj;
void main() {
    gl_Position = uViewProj * vec4(aPosition, 1.0);
}
)GLSL";

inline constexpr const char* kDepthFragmentShader = R"GLSL(
#version 450 core
void main() {
}
)GLSL";

inline constexpr const char* kHzbBuildShader = R"GLSL(
#version 450 core
layout(local_size_x = 8, local_size_y = 8) in;

uniform sampler2D uSource;
uniform int uSourceLevel;
uniform int uCopyMode;
uniform ivec2 uSourceSize;
uniform ivec2 uDestSize;
layout(r32f, binding = 0) writeonly uniform image2D uDest;

float sourceTexel(ivec2 pixel) {
    pixel = clamp(pixel, ivec2(0), uSourceSize - ivec2(1));
    return texelFetch(uSource, pixel, uSourceLevel).r;
}

void main() {
    ivec2 pixel = ivec2(gl_GlobalInvocationID.xy);
    if (pixel.x >= uDestSize.x || pixel.y >= uDestSize.y) {
        return;
    }

    float depth;
    if (uCopyMode != 0) {
        depth = sourceTexel(pixel);
    } else {
        ivec2 base = pixel * 2;
        depth = max(max(sourceTexel(base), sourceTexel(base + ivec2(1, 0))),
                    max(sourceTexel(base + ivec2(0, 1)),
                        sourceTexel(base + ivec2(1, 1))));
    }
    imageStore(uDest, pixel, vec4(depth, 0.0, 0.0, 1.0));
}
)GLSL";

inline constexpr const char* kHzbTestShader = R"GLSL(
#version 450 core
layout(local_size_x = 64) in;

struct Box {
    float minX;
    float minY;
    float minZ;
    float maxX;
    float maxY;
    float maxZ;
};

layout(std430, binding = 0) readonly buffer Boxes {
    Box boxes[];
};
layout(std430, binding = 1) writeonly buffer CulledFlags {
    uint culled[];
};

uniform mat4 uViewProj;
uniform sampler2D uHzb;
uniform uvec2 uFullSize;
uniform int uMaxLevel;
uniform float uDepthBias;

vec4 projectCorner(vec3 corner) {
    return uViewProj * vec4(corner, 1.0);
}

void main() {
    uint index = gl_GlobalInvocationID.x;
    if (index >= uint(boxes.length())) {
        return;
    }

    Box box = boxes[index];
    vec3 corners[8] = vec3[](
        vec3(box.minX, box.minY, box.minZ), vec3(box.maxX, box.minY, box.minZ),
        vec3(box.minX, box.maxY, box.minZ), vec3(box.maxX, box.maxY, box.minZ),
        vec3(box.minX, box.minY, box.maxZ), vec3(box.maxX, box.minY, box.maxZ),
        vec3(box.minX, box.maxY, box.maxZ), vec3(box.maxX, box.maxY, box.maxZ)
    );

    vec2 low = vec2(1.0e30);
    vec2 high = vec2(-1.0e30);
    float nearestDepth = 1.0e30;
    for (int cornerIndex = 0; cornerIndex < 8; ++cornerIndex) {
        vec4 clip = projectCorner(corners[cornerIndex]);
        if (clip.w <= 1.0e-5) {
            culled[index] = 0u;
            return;
        }
        vec3 ndc = clip.xyz / clip.w;
        if (ndc.z < -1.0 || ndc.z > 1.0) {
            culled[index] = 0u;
            return;
        }
        low = min(low, ndc.xy);
        high = max(high, ndc.xy);
        nearestDepth = min(nearestDepth, ndc.z * 0.5 + 0.5);
    }

    if (low.x > 1.0 || high.x < -1.0 || low.y > 1.0 || high.y < -1.0) {
        culled[index] = 0u;
        return;
    }

    vec2 pixelLow = (low * 0.5 + 0.5) * vec2(uFullSize);
    vec2 pixelHigh = (high * 0.5 + 0.5) * vec2(uFullSize);
    pixelLow = clamp(pixelLow, vec2(0.0), vec2(uFullSize) - vec2(1.0));
    pixelHigh = clamp(pixelHigh, vec2(0.0), vec2(uFullSize) - vec2(1.0));

    float largestSpan = max(pixelHigh.x - pixelLow.x + 1.0,
                            pixelHigh.y - pixelLow.y + 1.0);
    int level = 0;
    while (level < uMaxLevel && float(1 << level) < largestSpan) {
        ++level;
    }

    int tileSize = 1 << level;
    ivec2 levelSize = max(ivec2(1), ivec2(uFullSize) >> level);
    ivec2 tileLow = ivec2(floor(pixelLow)) / tileSize;
    ivec2 tileHigh = ivec2(floor(pixelHigh)) / tileSize;
    tileHigh = min(tileHigh, levelSize - ivec2(1));
    tileLow = clamp(tileLow, ivec2(0), levelSize - ivec2(1));

    float occluderDepth = 0.0;
    for (int y = tileLow.y; y <= tileHigh.y; ++y) {
        for (int x = tileLow.x; x <= tileHigh.x; ++x) {
            occluderDepth = max(occluderDepth,
                                texelFetch(uHzb, ivec2(x, y), level).r);
        }
    }

    culled[index] = (nearestDepth > occluderDepth + uDepthBias) ? 1u : 0u;
}
)GLSL";

}  // namespace hzb
