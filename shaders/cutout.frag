#version 450
layout(set = 0, binding = 0) uniform sampler2D atlas;

layout(push_constant) uniform PC {
    mat4 mvp;
    vec4 tint;
    vec4 params; // x: alphaOverride (<0 = off), y: mode (0=discard, 1=a2c), z: isBackground
    vec4 uvXform;
} pc;

layout(location = 0) in vec2 inUV;
layout(location = 0) out vec4 outColor;

void main() {
    vec4 tex = texture(atlas, inUV);
    vec3 col = tex.rgb * pc.tint.rgb;
    float alpha = tex.a;
    if (pc.params.x >= 0.0) { // uniform-alpha test block / opaque occluder
        alpha = pc.params.x;
        col = pc.tint.rgb;
    }
    if (pc.params.z > 0.5) { // background gradient
        col = mix(vec3(0.05, 0.06, 0.09), vec3(0.16, 0.18, 0.23), inUV.y);
        alpha = 1.0;
    }
    if (pc.params.y < 0.5 && alpha < 0.5)
        discard; // fixed-threshold cutout
    // alpha-to-coverage mode: no discard, pipeline converts alpha to sample mask
    outColor = vec4(col, alpha);
}
