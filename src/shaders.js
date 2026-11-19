export const MESH_VERTEX_SHADER = `#version 300 es
precision highp float;
precision highp int;

layout(location = 0) in vec3 aPosition;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec4 aSkinIndex;
layout(location = 3) in vec4 aSkinWeight;
layout(location = 4) in vec3 aTint;

uniform mat4 uViewProj;
uniform mat4 uBoneMatrices[8];
uniform vec4 uDqReal[8];
uniform vec4 uDqDual[8];
uniform int uMode;
uniform float uHeatMax;
uniform vec3 uCameraPosition;
uniform vec3 uBaseColor;

out vec3 vNormal;
out vec3 vWorldPosition;
out vec3 vColor;
out float vError;
out float vTintBand;

vec3 rotateByQuaternion(vec4 q, vec3 v) {
  vec3 t = 2.0 * cross(q.xyz, v);
  return v + q.w * t + cross(q.xyz, t);
}

vec3 applyDualQuaternion(vec4 real, vec4 dual, vec3 point) {
  float len = length(real);
  if (len < 1e-7) return point;
  real /= len;
  dual /= len;
  vec3 rotated = rotateByQuaternion(real, point);
  vec3 translation = 2.0 * (
    real.w * dual.xyz -
    dual.w * real.xyz +
    cross(real.xyz, dual.xyz)
  );
  return rotated + translation;
}

vec3 heatColor(float value) {
  float t = clamp(value, 0.0, 1.0);
  vec3 c0 = vec3(0.055, 0.035, 0.12);
  vec3 c1 = vec3(0.27, 0.13, 0.42);
  vec3 c2 = vec3(0.72, 0.25, 0.36);
  vec3 c3 = vec3(0.96, 0.54, 0.25);
  vec3 c4 = vec3(1.0, 0.96, 0.68);
  if (t < 0.25) return mix(c0, c1, t / 0.25);
  if (t < 0.5) return mix(c1, c2, (t - 0.25) / 0.25);
  if (t < 0.75) return mix(c2, c3, (t - 0.5) / 0.25);
  return mix(c3, c4, (t - 0.75) / 0.25);
}

void main() {
  vec3 lbsPosition = vec3(0.0);
  vec3 lbsNormal = vec3(0.0);
  vec4 realSum = vec4(0.0);
  vec4 dualSum = vec4(0.0);
  float totalWeight = 0.0;

  for (int lane = 0; lane < 4; lane++) {
    float weight = aSkinWeight[lane];
    if (weight <= 0.0) continue;
    int bone = int(aSkinIndex[lane]);
    lbsPosition += weight * (uBoneMatrices[bone] * vec4(aPosition, 1.0)).xyz;
    lbsNormal += weight * (mat3(uBoneMatrices[bone]) * aNormal);
    realSum += weight * uDqReal[bone];
    dualSum += weight * uDqDual[bone];
    totalWeight += weight;
  }

  vec3 dqsPosition;
  vec3 dqsNormal;
  float error = 0.0;
  if (totalWeight <= 1e-7) {
    lbsPosition = aPosition;
    lbsNormal = aNormal;
    dqsPosition = aPosition;
    dqsNormal = aNormal;
  } else {
    lbsPosition /= totalWeight;
    lbsNormal = normalize(lbsNormal);
    realSum /= totalWeight;
    dualSum /= totalWeight;
    float realLength = length(realSum);
    if (realLength < 1e-6) {
      dqsPosition = aPosition;
      dqsNormal = aNormal;
    } else {
      dqsPosition = applyDualQuaternion(realSum, dualSum, aPosition);
      dqsNormal = rotateByQuaternion(normalize(realSum), aNormal);
    }
    error = distance(lbsPosition, dqsPosition);
  }

  vec3 finalPosition = uMode == 0 ? lbsPosition : dqsPosition;
  vec3 finalNormal = uMode == 0 ? lbsNormal : dqsNormal;
  vec3 base = uBaseColor * aTint;
  vec3 finalColor = base;
  if (uMode == 2) {
    finalColor = heatColor(error / max(uHeatMax, 1e-5));
  }

  float light = max(dot(normalize(finalNormal), normalize(vec3(-0.45, -0.72, 0.82))), 0.0);
  float horizon = 0.52 + 0.48 * finalNormal.z;
  float rim = 1.0 - abs(dot(normalize(finalNormal), normalize(uCameraPosition - finalPosition)));
  rim = pow(clamp(rim, 0.0, 1.0), 2.4);
  vec3 lit = finalColor * (0.24 + light * 0.72 + horizon * 0.16);
  lit += finalColor * rim * 0.16;
  if (uMode != 2) {
    lit += vec3(0.25, 0.32, 0.34) * pow(light, 5.0) * 0.12;
  }

  vNormal = normalize(finalNormal);
  vWorldPosition = finalPosition;
  vColor = lit;
  vError = error;
  vTintBand = aTint.y;
  gl_Position = uViewProj * vec4(finalPosition, 1.0);
}
`;

export const MESH_FRAGMENT_SHADER = `#version 300 es
precision highp float;
precision highp int;

in vec3 vNormal;
in vec3 vWorldPosition;
in vec3 vColor;
in float vError;
in float vTintBand;

uniform int uMode;
uniform float uHeatMax;
uniform vec3 uCameraPosition;

out vec4 outColor;

vec3 heatColor(float value) {
  float t = clamp(value, 0.0, 1.0);
  vec3 c0 = vec3(0.055, 0.035, 0.12);
  vec3 c1 = vec3(0.27, 0.13, 0.42);
  vec3 c2 = vec3(0.72, 0.25, 0.36);
  vec3 c3 = vec3(0.96, 0.54, 0.25);
  vec3 c4 = vec3(1.0, 0.96, 0.68);
  if (t < 0.25) return mix(c0, c1, t / 0.25);
  if (t < 0.5) return mix(c1, c2, (t - 0.25) / 0.25);
  if (t < 0.75) return mix(c2, c3, (t - 0.5) / 0.25);
  return mix(c3, c4, (t - 0.75) / 0.25);
}

void main() {
  vec3 normal = normalize(vNormal);
  vec3 viewDirection = normalize(uCameraPosition - vWorldPosition);
  float fresnel = pow(1.0 - max(dot(normal, viewDirection), 0.0), 2.2);
  vec3 color = vColor;
  if (uMode == 2) {
    float bands = 0.94 + 0.06 * sin(vWorldPosition.z * 58.0 + vWorldPosition.x * 18.0);
    color = heatColor(vError / max(uHeatMax, 1e-5)) * bands;
  } else {
    color += vec3(fresnel) * 0.045;
  }
  float fog = smoothstep(10.0, 18.0, distance(vWorldPosition, uCameraPosition));
  color = mix(color, vec3(0.035, 0.055, 0.065), fog * 0.42);
  outColor = vec4(color, 1.0);
}
`;

export const LINE_VERTEX_SHADER = `#version 300 es
precision highp float;

layout(location = 0) in vec3 aPosition;
uniform mat4 uViewProj;
uniform float uPointSize;

void main() {
  gl_Position = uViewProj * vec4(aPosition, 1.0);
  gl_PointSize = uPointSize;
}
`;

export const LINE_FRAGMENT_SHADER = `#version 300 es
precision highp float;
precision highp int;

uniform vec4 uColor;
uniform float uIsPoint;
out vec4 outColor;

void main() {
  if (uIsPoint > 0.5) {
    vec2 point = gl_PointCoord - vec2(0.5);
    float radius = length(point);
    if (radius > 0.5) discard;
    float edge = smoothstep(0.5, 0.38, radius);
    outColor = vec4(uColor.rgb, uColor.a * edge);
  } else {
    outColor = uColor;
  }
}
`;
