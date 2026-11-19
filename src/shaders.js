export const sceneVertex = `#version 300 es
precision highp float;
in vec3 aPosition;
uniform mat4 uViewProjection;
uniform mat4 uModel;
uniform mat4 uLightViewProjection;
out vec3 vWorld;
out vec4 vLightClip;
void main() {
  vec4 world = uModel * vec4(aPosition, 1.0);
  vWorld = world.xyz;
  vLightClip = uLightViewProjection * world;
  gl_Position = uViewProjection * world;
}`;

export const sceneFragment = `#version 300 es
precision highp float;
in vec3 vWorld;
in vec4 vLightClip;
uniform vec3 uColor;
uniform vec3 uCameraPosition;
uniform vec3 uLightDirection;
uniform sampler2D uShadowMap;
uniform float uUseShadowMap;
uniform float uDebugMask;
uniform float uGround;
out vec4 outColor;

float getShadow() {
  vec3 projected = vLightClip.xyz / vLightClip.w;
  projected = projected * 0.5 + 0.5;
  if (projected.x <= 0.0 || projected.x >= 1.0 ||
      projected.y <= 0.0 || projected.y >= 1.0 ||
      projected.z <= 0.0 || projected.z >= 1.0) {
    return 0.0;
  }
  float stored = texture(uShadowMap, projected.xy).r;
  return projected.z - 0.0025 > stored ? 1.0 : 0.0;
}

void main() {
  vec3 normal = normalize(cross(dFdx(vWorld), dFdy(vWorld)));
  if (dot(normal, uCameraPosition - vWorld) < 0.0) normal = -normal;
  float diffuse = max(dot(normal, uLightDirection), 0.0);
  float shadow = uUseShadowMap > 0.5 ? getShadow() : 0.0;
  float rim = pow(1.0 - max(dot(normal, normalize(uCameraPosition - vWorld)), 0.0), 2.0);
  vec2 gridCell = abs(fract(vWorld.xz * 0.5) - 0.5);
  float grid = smoothstep(0.475, 0.5, max(gridCell.x, gridCell.y));
  vec3 base = uColor + vec3(0.045, 0.055, 0.045) * grid * uGround;
  vec3 sky = vec3(0.055, 0.085, 0.075);
  vec3 lightColor = vec3(1.0, 0.87, 0.64);
  vec3 lit = base * (0.18 + diffuse * 0.86) * lightColor;
  lit += base * sky * 1.15;
  lit += vec3(0.08, 0.17, 0.14) * rim * 0.3;
  lit *= mix(1.0, 0.24, shadow);
  float distanceFog = smoothstep(19.0, 48.0, length(vWorld - uCameraPosition));
  lit = mix(lit, vec3(0.027, 0.048, 0.042), distanceFog);
  if (uDebugMask > 0.5) {
    outColor = vec4(vec3(shadow), 1.0);
  } else {
    outColor = vec4(lit, 1.0);
  }
}`;

export const depthVertex = `#version 300 es
precision highp float;
in vec3 aPosition;
uniform mat4 uLightViewProjection;
uniform mat4 uModel;
void main() {
  gl_Position = uLightViewProjection * uModel * vec4(aPosition, 1.0);
}`;

export const depthFragment = `#version 300 es
precision highp float;
void main() {}`;

export const volumeVertex = `#version 300 es
precision highp float;
in vec3 aPosition;
uniform mat4 uViewProjection;
void main() {
  gl_Position = uViewProjection * vec4(aPosition, 1.0);
}`;

export const volumeFragment = `#version 300 es
precision highp float;
uniform vec4 uColor;
out vec4 outColor;
void main() {
  outColor = uColor;
}`;

export const flatVertex = `#version 300 es
precision highp float;
in vec3 aPosition;
uniform mat4 uViewProjection;
uniform mat4 uModel;
void main() {
  gl_Position = uViewProjection * uModel * vec4(aPosition, 1.0);
}`;

export const flatFragment = `#version 300 es
precision highp float;
uniform vec4 uColor;
out vec4 outColor;
void main() {
  outColor = uColor;
}`;

export const fullscreenVertex = `#version 300 es
precision highp float;
out vec2 vUv;
void main() {
  vec2 position = vec2(
    gl_VertexID == 1 ? 3.0 : -1.0,
    gl_VertexID == 2 ? 3.0 : -1.0
  );
  vUv = position * 0.5 + 0.5;
  gl_Position = vec4(position, 0.0, 1.0);
}`;

export const shadowOverlayFragment = `#version 300 es
precision highp float;
uniform vec4 uColor;
out vec4 outColor;
void main() {
  outColor = uColor;
}`;

export const volumeLineFragment = `#version 300 es
precision highp float;
uniform vec4 uColor;
out vec4 outColor;
void main() {
  outColor = uColor;
}`;

export const blitFragment = `#version 300 es
precision highp float;
in vec2 vUv;
uniform sampler2D uTexture;
out vec4 outColor;
void main() {
  outColor = texture(uTexture, vUv);
}`;
