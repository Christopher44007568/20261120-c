#version 450

layout(set = 0, binding = 0, std140) uniform CameraBlock {
    mat4 viewProj;
    vec4 cameraPos;
} camera;

layout(push_constant) uniform PushBlock {
    mat4 model;
    vec4 tint;
} push;

layout(location = 0) in vec3 inPosition;
layout(location = 1) in vec3 inNormal;
layout(location = 2) in vec2 inTexCoord;

layout(location = 0) out vec3 vWorldPos;
layout(location = 1) out vec3 vNormal;
layout(location = 2) out vec2 vTexCoord;
layout(location = 3) flat out vec4 vTint;

void main() {
    vec4 world = push.model * vec4(inPosition, 1.0);
    vWorldPos = world.xyz;
    vNormal = normalize(mat3(push.model) * inNormal);
    vTexCoord = inTexCoord;
    vTint = push.tint;
    gl_Position = camera.viewProj * world;
}
