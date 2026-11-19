#version 450

layout(set = 0, binding = 0, std140) uniform CameraBlock {
    mat4 viewProj;
    vec4 cameraPos;
} camera;

struct Light {
    vec4 dir;
    vec4 color;
    float intensity;
};

struct Material {
    vec4 baseColor;
    vec4 params;
};

layout(set = 0, binding = 1, std140) uniform MaterialBlock {
    Light lights[3];
    Material mat;
    vec4 curve[4];
    float roughness;
} material;

struct Item {
    vec4 pos;
    vec4 weight;
};

layout(set = 0, binding = 2, std430) buffer ItemBlock {
    Item items[4];
    float weights[];
} ssbo;

layout(set = 1, binding = 0) uniform sampler2D baseMap;
layout(set = 1, binding = 1) uniform samplerCube envMap;
layout(set = 1, binding = 2) uniform texture2D detailTex;
layout(set = 1, binding = 3) uniform sampler detailSamp;

layout(push_constant) uniform FragPush {
    layout(offset = 80) vec4 tint;
} fragPush;

layout(location = 0) in vec3 vWorldPos;
layout(location = 1) in vec3 vNormal;
layout(location = 2) in vec2 vTexCoord;
layout(location = 3) flat in vec4 vTint;

layout(location = 0) out vec4 fragColor;

void main() {
    vec3 normal = normalize(vNormal);
    vec3 viewDir = normalize(camera.cameraPos.xyz - vWorldPos);

    vec3 albedo = material.mat.baseColor.rgb * texture(baseMap, vTexCoord).rgb;
    vec4 detail = texture(sampler2D(detailTex, detailSamp), vTexCoord * 2.0);
    albedo = mix(albedo, detail.rgb, material.mat.params.x);

    vec3 lighting = vec3(0.0);
    for (int i = 0; i < 3; ++i) {
        vec3 lightDir = normalize(material.lights[i].dir.xyz);
        float diffuse = max(dot(normal, lightDir), 0.0);
        vec3 halfDir = normalize(lightDir + viewDir);
        float shininess = material.roughness * 64.0;
        float specular = pow(max(dot(normal, halfDir), 0.0), shininess);
        lighting += material.lights[i].color.rgb
                  * (diffuse * material.lights[i].intensity + specular);
    }

    vec3 reflectDir = reflect(-viewDir, normal);
    vec3 env = textureLod(envMap, reflectDir, 0.0).rgb;
    vec3 color = albedo * (lighting + 0.15) + env * material.mat.params.y;
    color += vec3(ssbo.weights[0]) + ssbo.items[0].weight.xyz;
    color *= fragPush.tint.rgb * vTint.rgb;

    fragColor = vec4(clamp(color, 0.0, 1.0), 1.0);
}
