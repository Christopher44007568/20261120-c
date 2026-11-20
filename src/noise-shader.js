export const VERTEX_SHADER = `#version 300 es
precision highp float;
in vec2 aPosition;
void main() {
  gl_Position = vec4(aPosition, 0.0, 1.0);
}
`;

export const FRAGMENT_SHADER = `#version 300 es
precision highp float;
precision highp int;

uniform vec2 uResolution;
uniform float uScale;
uniform float uGain;
uniform float uWarp;
uniform float uTime;
uniform vec2 uSeed;
uniform int uOctaves;
uniform int uWarped;
uniform int uNoise;
uniform int uMode;

out vec4 fragColor;

const float TAU = 6.28318530718;
const mat2 OCTAVE_ROTATION = mat2(0.8, 0.6, -0.6, 0.8);

uint hashUint(uint value) {
  value ^= value >> 16;
  value *= 0x7feb352du;
  value ^= value >> 15;
  value *= 0x846ca68bu;
  value ^= value >> 16;
  return value;
}

float hash1(vec2 p) {
  ivec2 cell = ivec2(floor(p)) + ivec2(8191);
  uint x = uint(cell.x + 32768);
  uint y = uint(cell.y + 32768);
  uint h = hashUint(x * 1597334677u ^ hashUint(y * 3812015801u + 0x9e3779b9u));
  return float(h & 0x00ffffffu) / 16777215.0;
}

vec2 hash2(vec2 p) {
  ivec2 cell = ivec2(floor(p)) + ivec2(8191);
  uint x = uint(cell.x + 32768);
  uint y = uint(cell.y + 32768);
  uint a = hashUint(x * 1597334677u ^ hashUint(y * 3812015801u + 0x9e3779b9u));
  uint b = hashUint(a ^ 0x85ebca6bu);
  return vec2(
    float(a & 0x00ffffffu) / 16777215.0,
    float(b & 0x00ffffffu) / 16777215.0
  );
}

vec2 gradientAt(vec2 cell) {
  float angle = hash1(cell * 1.37 + 0.41) * TAU;
  return vec2(cos(angle), sin(angle));
}

float perlinBase(vec2 p) {
  vec2 cell = floor(p);
  vec2 local = fract(p);
  vec2 fade = local * local * local * (local * (local * 6.0 - 15.0) + 10.0);
  float n00 = dot(gradientAt(cell), local);
  float n10 = dot(gradientAt(cell + vec2(1.0, 0.0)), local - vec2(1.0, 0.0));
  float n01 = dot(gradientAt(cell + vec2(0.0, 1.0)), local - vec2(0.0, 1.0));
  float n11 = dot(gradientAt(cell + vec2(1.0, 1.0)), local - vec2(1.0, 1.0));
  float nx0 = mix(n00, n10, fade.x);
  float nx1 = mix(n01, n11, fade.x);
  return clamp(0.5 + 0.82 * mix(nx0, nx1, fade.y), 0.0, 1.0);
}

float simplexBase(vec2 p) {
  const float F2 = 0.36602540378;
  const float G2 = 0.21132486540;
  vec2 cell = floor(p + dot(p, vec2(F2)));
  vec2 local = p - cell + dot(cell, vec2(G2));
  vec2 i1 = local.x > local.y ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
  vec2 x0 = local;
  vec2 x1 = local - i1 + G2;
  vec2 x2 = local - 1.0 + 2.0 * G2;

  float m0 = max(0.5 - dot(x0, x0), 0.0);
  float m1 = max(0.5 - dot(x1, x1), 0.0);
  float m2 = max(0.5 - dot(x2, x2), 0.0);
  m0 *= m0; m1 *= m1; m2 *= m2;
  m0 *= m0; m1 *= m1; m2 *= m2;
  float n = m0 * dot(gradientAt(cell), x0);
  n += m1 * dot(gradientAt(cell + i1), x1);
  n += m2 * dot(gradientAt(cell + vec2(1.0)), x2);
  return clamp(0.5 + 68.0 * n, 0.0, 1.0);
}

vec3 worleyCell(vec2 p) {
  vec2 cell = floor(p);
  vec2 local = fract(p);
  float f1 = 8.0;
  float f2 = 8.0;

  for (int y = -1; y <= 1; y++) {
    for (int x = -1; x <= 1; x++) {
      vec2 offset = vec2(float(x), float(y));
      vec2 feature = offset + hash2(cell + offset) - local;
      float distanceSquared = dot(feature, feature);
      if (distanceSquared < f1) {
        f2 = f1;
        f1 = distanceSquared;
      } else if (distanceSquared < f2) {
        f2 = distanceSquared;
      }
    }
  }
  return vec3(sqrt(f1), sqrt(f2), f2 - f1);
}

float worleyBase(vec2 p) {
  float f1 = worleyCell(p).x;
  float puff = 1.0 - smoothstep(0.0, 0.9, f1);
  return puff * puff * (3.0 - 2.0 * puff);
}

float noiseBase(vec2 p, int noiseId) {
  if (noiseId == 0) return perlinBase(p);
  if (noiseId == 1) return worleyBase(p);
  return simplexBase(p);
}

float fbm(vec2 p, int noiseId, int octaves) {
  float sum = 0.0;
  float amplitude = 1.0;
  float normalization = 0.0;
  for (int octave = 0; octave < 7; octave++) {
    if (octave >= octaves) break;
    float value = noiseBase(p, noiseId);
    sum += amplitude * value;
    normalization += amplitude;
    p = OCTAVE_ROTATION * p * 2.03 + vec2(11.7, 7.3);
    amplitude *= uGain;
  }
  return sum / max(normalization, 0.0001);
}

vec2 warpCoordinate(vec2 p, int noiseId) {
  if (uWarped == 0) return p;
  int warpOctaves = max(2, uOctaves - 2);
  vec2 lowA = vec2(
    fbm(p * 0.62 + vec2(13.7, 4.2), noiseId, warpOctaves),
    fbm(p * 0.62 + vec2(29.1, 51.8), noiseId, warpOctaves)
  );
  vec2 lowB = vec2(
    fbm(p * 1.17 + vec2(73.4, 17.9), noiseId, max(2, uOctaves - 3)),
    fbm(p * 1.17 + vec2(41.2, 88.6), noiseId, max(2, uOctaves - 3))
  );
  vec2 displacement = (lowA - 0.5) * 1.55 + (lowB - 0.5) * 0.45;
  return p + displacement * (uWarp * 2.35);
}

float fieldValue(vec2 p, int noiseId) {
  return fbm(warpCoordinate(p, noiseId), noiseId, uOctaves);
}

vec3 cloudSky(vec2 p) {
  float height = clamp(p.y * 0.34 + 0.48, 0.0, 1.0);
  vec3 low = vec3(0.238, 0.192, 0.151);
  vec3 high = vec3(0.058, 0.105, 0.149);
  float glow = smoothstep(1.3, 0.0, length(p - vec2(-0.55, 0.62)));
  return mix(low, high, height) + vec3(0.22, 0.155, 0.09) * glow * 0.55;
}

vec3 cloudMaterial(vec2 p, int noiseId) {
  vec2 warped = warpCoordinate(p, noiseId);
  float shape = fbm(warped * 0.56 + vec2(17.3, 6.8), noiseId, uOctaves);
  float detail = fbm(warped * 1.75 + vec2(7.2, 3.4), noiseId, min(uOctaves, 3));
  float densityValue = shape + (detail - 0.5) * 0.22;
  float opacity = smoothstep(0.465, 0.56, densityValue);
  float thickness = smoothstep(0.52, 0.76, densityValue);

  vec3 cloudShadow = vec3(0.305, 0.34, 0.35);
  vec3 cloudBody = vec3(0.66, 0.69, 0.675);
  vec3 cloudLight = vec3(0.975, 0.955, 0.895);
  vec3 cloud = mix(cloudShadow, cloudBody, smoothstep(0.5, 0.72, densityValue));
  cloud = mix(cloud, cloudLight, smoothstep(0.74, 0.92, densityValue) * 0.9);
  cloud *= 0.93 + 0.1 * thickness;

  vec3 color = mix(cloudSky(p), cloud, opacity);
  color += vec3(0.31, 0.18, 0.09) * smoothstep(0.55, 0.66, densityValue) *
    (1.0 - smoothstep(0.67, 0.82, densityValue)) * 0.18;
  float wisp = smoothstep(0.52, 0.64, densityValue) * (1.0 - opacity) * 0.22;
  color += vec3(0.48, 0.5, 0.47) * wisp;
  return color;
}

vec3 stoneMaterial(vec2 p, int noiseId) {
  vec2 warped = warpCoordinate(p, noiseId);
  float broad = fbm(warped * 0.82 + vec2(4.1, 9.6), noiseId, uOctaves);
  float grain = fbm(warped * 4.6 + vec2(19.2, 2.8), noiseId, min(uOctaves, 3));
  float veinNoise = fbm(warped * 1.18 + vec2(31.4, 6.1), noiseId, max(2, uOctaves - 1));

  float vein = 1.0 - abs(veinNoise * 2.0 - 1.0);
  vein = pow(clamp(vein, 0.0, 1.0), 9.0);
  float fineVein = 1.0 - abs(grain * 2.0 - 1.0);
  fineVein = pow(clamp(fineVein, 0.0, 1.0), 16.0);
  float strata = 0.5 + 0.5 * sin(warped.y * 10.4 + broad * 6.8 + grain * 1.7);

  vec3 charcoal = vec3(0.084, 0.082, 0.073);
  vec3 stone = vec3(0.315, 0.302, 0.265);
  vec3 warmStone = vec3(0.512, 0.466, 0.374);
  vec3 seam = vec3(0.816, 0.704, 0.528);

  vec3 color = mix(charcoal, stone, smoothstep(0.18, 0.68, broad));
  color = mix(color, warmStone, smoothstep(0.58, 0.88, grain) * 0.5);
  color *= 0.88 + 0.2 * strata;
  color = mix(color, seam, vein * 0.62);
  color = mix(color, seam * 1.08, fineVein * 0.18);

  float cavity = smoothstep(0.08, 0.27, broad) * (1.0 - smoothstep(0.3, 0.44, broad));
  color *= 1.0 - cavity * 0.24;
  return color;
}

vec3 turbulenceMaterial(vec2 p, int noiseId) {
  vec2 warped = warpCoordinate(p, noiseId);
  int colorOctaves = min(uOctaves, 4);
  float broad = fbm(warped * 1.07 + vec2(5.7, 25.4), noiseId, colorOctaves);
  vec2 curl = vec2(
    fbm(warped + vec2(2.3, 8.4), noiseId, min(3, colorOctaves)),
    fbm(warped + vec2(16.1, 4.8), noiseId, min(3, colorOctaves))
  ) - 0.5;
  float flow = fbm(warped + curl * 2.5, noiseId, colorOctaves);
  float braid = 0.5 + 0.5 * sin(flow * 9.5 + broad * 4.2 + warped.x * 1.25);
  float ridge = 1.0 - abs(flow * 2.0 - 1.0);
  float filament = smoothstep(0.74, 0.97, ridge);
  float shear = smoothstep(0.39, 0.71, broad) * smoothstep(0.52, 0.9, braid);

  vec3 deep = vec3(0.027, 0.053, 0.061);
  vec3 ink = vec3(0.085, 0.137, 0.141);
  vec3 ember = vec3(0.734, 0.239, 0.129);
  vec3 flare = vec3(0.965, 0.619, 0.315);
  vec3 cyan = vec3(0.329, 0.745, 0.692);

  vec3 color = mix(deep, ink, smoothstep(0.18, 0.66, broad));
  color = mix(color, ember, smoothstep(0.38, 0.92, shear) * 0.65);
  color = mix(color, flare, smoothstep(0.75, 0.97, braid) * smoothstep(0.46, 0.7, flow) * 0.34);
  color += cyan * filament * 0.24;

  float coolEdge = smoothstep(0.12, 0.42, 1.0 - flow) * smoothstep(0.35, 0.72, broad);
  color += cyan * coolEdge * vec3(0.06, 0.085, 0.095);
  return color;
}

vec3 materialColor(int materialId, vec2 p, int noiseId) {
  if (materialId == 0) return cloudMaterial(p, noiseId);
  if (materialId == 1) return stoneMaterial(p, noiseId);
  return turbulenceMaterial(p, noiseId);
}

void main() {
  vec2 screenUv = gl_FragCoord.xy / uResolution;

  if (uMode == 1) {
    vec2 p = (screenUv - 0.5) * uScale + vec2(3.17, 1.43) + uSeed;
    float value = clamp(fieldValue(p, uNoise), 0.0, 1.0);
    fragColor = vec4(vec3(value), 1.0);
    return;
  }

  vec2 gridUv = screenUv * 3.0;
  int noiseId = int(floor(gridUv.x));
  int materialId = 2 - int(floor(gridUv.y));
  vec2 localUv = fract(gridUv);

  float gutter = min(
    min(localUv.x, 1.0 - localUv.x),
    min(localUv.y, 1.0 - localUv.y)
  );
  if (gutter < 0.004) {
    fragColor = vec4(0.027, 0.029, 0.024, 1.0);
    return;
  }

  vec2 p = (localUv - 0.5) * vec2(1.5, 1.0) * uScale;
  p += vec2(sin(uTime * 0.06), cos(uTime * 0.045)) * 0.16;
  p += vec2(3.17, 1.43) + uSeed;
  vec3 color = materialColor(materialId, p, noiseId);

  float vignette = 1.0 - smoothstep(0.35, 0.85, length(localUv - 0.5));
  color *= 0.88 + 0.12 * vignette;
  color = clamp(color, 0.0, 1.0);
  fragColor = vec4(color, 1.0);
}
`;
