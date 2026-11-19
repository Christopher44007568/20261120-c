#version 450
layout(location = 0) in vec3 inPos;
layout(location = 1) in vec2 inUV;

layout(push_constant) uniform PC {
    mat4 mvp;
    vec4 tint;
    vec4 params; // x: alphaOverride (<0 = off), y: mode (0=discard, 1=a2c), z: isBackground
    vec4 uvXform; // xy = scale, zw = offset (atlas region select)
} pc;

layout(location = 0) out vec2 outUV;

void main() {
    outUV = inUV * pc.uvXform.xy + pc.uvXform.zw;
    gl_Position = pc.mvp * vec4(inPos, 1.0);
}
