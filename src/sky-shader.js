export const VERTEX_SHADER = `#version 300 es
in vec2 aPosition;
void main() {
  gl_Position = vec4(aPosition, 0.0, 1.0);
}
`;

export const FRAGMENT_SHADER = `#version 300 es
precision highp float;

out vec4 fragColor;

uniform vec2 uResolution;
uniform float uTime;
uniform vec3 uSunDirection;
uniform float uSunElevation;
uniform float uRayleighScale;
uniform float uMieScale;
uniform float uCloudCoverage;
uniform float uCloudThickness;
uniform float uCloudShadows;

const float PI = 3.14159265359;
const float EARTH_RADIUS = 6360.0;
const float ATMOSPHERE_TOP = 60.0;
const float OBSERVER_HEIGHT = 0.32;
const float CLOUD_BASE = 1.05;
const float HR = 8.0;
const float HM = 1.2;
const vec3 BETA_R = vec3(0.0058, 0.0135, 0.0331);
const float BETA_M = 0.021;

float saturate(float value) {
  return clamp(value, 0.0, 1.0);
}

vec2 raySphere(vec3 origin, vec3 direction, float radius) {
  vec3 center = vec3(0.0, -EARTH_RADIUS, 0.0);
  vec3 oc = origin - center;
  float b = dot(oc, direction);
  float c = dot(oc, oc) - radius * radius;
  float h = b * b - c;
  if (h < 0.0) return vec2(-1.0);
  h = sqrt(h);
  return vec2(-b - h, -b + h);
}

float altitudeAt(vec3 point) {
  return length(point - vec3(0.0, -EARTH_RADIUS, 0.0)) - EARTH_RADIUS;
}

float rayleighPhase(float mu) {
  return 3.0 / (16.0 * PI) * (1.0 + mu * mu);
}

float miePhase(float mu, float g) {
  float g2 = g * g;
  return (1.0 - g2) / (4.0 * PI * pow(max(1.0 + g2 - 2.0 * g * mu, 0.0001), 1.5));
}

vec3 sunTransmittance(vec3 point, vec3 sunDir) {
  float altitude = max(altitudeAt(point), 0.0);
  float densityR = exp(-altitude / HR);
  float densityM = exp(-altitude / HM);
  float mu = max(sunDir.y, -0.015);
  float airMass = 1.0 / max(0.02, mu + 0.15 * pow(altitude + 3.885, -1.253));
  float opticalR = densityR * HR * airMass * uRayleighScale;
  float opticalM = densityM * HM * airMass * uMieScale;
  vec3 transmittance = exp(-BETA_R * opticalR * 0.78 - BETA_M * opticalM * 0.78);
  float visibility = smoothstep(-0.035, 0.02, sunDir.y + altitude * 0.0035);
  return transmittance * visibility;
}

vec3 skyRadiance(vec3 rayDir, vec3 sunDir) {
  vec3 origin = vec3(0.0, OBSERVER_HEIGHT, 0.0);
  vec2 top = raySphere(origin, rayDir, EARTH_RADIUS + ATMOSPHERE_TOP);
  if (top.y <= 0.0) return vec3(0.0);
  vec2 ground = raySphere(origin, rayDir, EARTH_RADIUS);
  float rayLength = top.y;
  if (ground.x > 0.0) rayLength = min(rayLength, ground.x);
  float mu = dot(rayDir, sunDir);
  float phaseR = rayleighPhase(mu);
  float phaseM = miePhase(mu, 0.76);
  vec3 inscatter = vec3(0.0);
  vec3 viewTransmittance = vec3(1.0);
  float previous = 0.0;
  const int VIEW_STEPS = 18;
  for (int i = 0; i < VIEW_STEPS; i++) {
    float f = (float(i) + 0.55) / float(VIEW_STEPS);
    float t = rayLength * f * f;
    float segment = max(0.001, t - previous);
    previous = t;
    vec3 point = origin + rayDir * t;
    float altitude = altitudeAt(point);
    if (altitude < 0.0) break;
    float densityR = exp(-altitude / HR);
    float densityM = exp(-altitude / HM);
    vec3 extinction = BETA_R * densityR * uRayleighScale +
      BETA_M * densityM * uMieScale;
    vec3 stepTransmittance = exp(-extinction * segment);
    vec3 sunLight = sunTransmittance(point, sunDir);
    vec3 scattering = BETA_R * densityR * uRayleighScale * phaseR +
      BETA_M * densityM * uMieScale * phaseM;
    inscatter += viewTransmittance * scattering * sunLight * segment;
    viewTransmittance *= stepTransmittance;
  }
  return inscatter * 0.42;
}

float hash12(vec2 point) {
  vec3 p3 = fract(vec3(point.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

float noise2(vec2 point) {
  vec2 i = floor(point);
  vec2 f = fract(point);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(hash12(i), hash12(i + vec2(1.0, 0.0)), u.x),
    mix(hash12(i + vec2(0.0, 1.0)), hash12(i + vec2(1.0, 1.0)), u.x),
    u.y
  );
}

float fbm(vec2 point) {
  float value = 0.0;
  float amplitude = 0.54;
  mat2 rotate = mat2(0.80, -0.60, 0.60, 0.80);
  for (int i = 0; i < 4; i++) {
    value += amplitude * noise2(point);
    point = rotate * point * 2.03 + 7.13;
    amplitude *= 0.49;
  }
  return value;
}

float cloudDensity(vec3 point, out float cloudHeight) {
  cloudHeight = (point.y - CLOUD_BASE) / max(uCloudThickness, 0.1);
  if (cloudHeight < 0.0 || cloudHeight > 1.0) return 0.0;
  vec2 wind = vec2(uTime * 0.0021, uTime * 0.0007);
  vec2 position = point.xz * 0.15 + wind;
  float warp = fbm(position * 0.27 + point.y * 0.1);
  float broad = fbm(position * 0.46 + vec2(warp * 1.55, -warp * 0.9));
  float detail = fbm(position * 0.94 + vec2(broad * 1.7 - point.y * 0.38));
  float field = broad * 0.72 + detail * 0.28;
  float cluster = smoothstep(0.22, 0.56, fbm(position * 0.18 + 11.3));
  float threshold = mix(0.86, 0.47, saturate(uCloudCoverage));
  float mask = smoothstep(threshold, threshold + 0.1, field) *
    mix(0.36, 1.0, cluster);
  float bottom = smoothstep(0.0, 0.2, cloudHeight);
  float top = 1.0 - smoothstep(0.42, 1.0, cloudHeight);
  float billow = 0.7 + 0.3 * smoothstep(0.18, 0.6, cloudHeight);
  return mask * bottom * top * billow;
}

float cloudShadow(vec3 point, vec3 sunDir) {
  if (uCloudShadows < 0.5 || sunDir.y < 0.025) return 0.0;
  float tBottom = (CLOUD_BASE - point.y) / max(sunDir.y, 0.025);
  float tTop = (CLOUD_BASE + uCloudThickness - point.y) / max(sunDir.y, 0.025);
  if (tTop <= 0.0) return 0.0;
  float start = max(0.0, tBottom);
  float tau = 0.0;
  const int SHADOW_STEPS = 5;
  for (int i = 0; i < SHADOW_STEPS; i++) {
    float f = (float(i) + 0.5) / float(SHADOW_STEPS);
    float t = mix(start, tTop, f);
    float height;
    tau += cloudDensity(point + sunDir * t, height) * max(0.05, tTop - start) / float(SHADOW_STEPS);
  }
  return 1.0 - exp(-tau * 2.2);
}

vec3 oceanColor(vec3 rayDir, vec3 sunDir, vec3 skyAmbient) {
  vec3 origin = vec3(0.0, OBSERVER_HEIGHT, 0.0);
  float t = OBSERVER_HEIGHT / max(-rayDir.y, 0.0005);
  vec3 point = origin + rayDir * t;
  vec2 ripple = vec2(
    noise2(point.xz * 0.23 + uTime * 0.01),
    noise2(point.xz * 0.31 - uTime * 0.008 + 5.2)
  ) - 0.5;
  vec3 normal = normalize(vec3(ripple.x * 0.065, 1.0, ripple.y * 0.065));
  vec3 reflected = reflect(rayDir, normal);
  vec3 reflectedSky = skyRadiance(reflected, sunDir);
  float fresnel = 0.025 + 0.975 * pow(1.0 - max(0.0, -rayDir.y), 5.0);
  float shadow = cloudShadow(point, sunDir) * (0.65 + 0.35 * uCloudCoverage);
  float glint = pow(max(dot(reflected, sunDir), 0.0), 620.0);
  vec3 direct = sunTransmittance(point, sunDir) * (1.0 - shadow);
  vec3 water = mix(vec3(0.006, 0.020, 0.028), skyAmbient * 0.55, fresnel);
  water += direct * glint * 0.85;
  water += reflectedSky * fresnel * 0.42;
  water *= 0.58 * (1.0 - shadow * 0.58);
  float distanceFade = smoothstep(1.0, 48.0, t);
  water = mix(water, skyAmbient * 0.92, distanceFade);
  return water;
}

vec3 renderClouds(vec3 rayDir, vec3 sunDir, vec3 skyAmbient, out float cloudAlpha) {
  cloudAlpha = 0.0;
  float layerBottom = CLOUD_BASE - OBSERVER_HEIGHT;
  float layerTop = CLOUD_BASE + uCloudThickness - OBSERVER_HEIGHT;
  if (rayDir.y <= 0.002 || uCloudCoverage <= 0.001) return vec3(0.0);
  float start = max(0.3, layerBottom / rayDir.y);
  float end = min(58.0, layerTop / rayDir.y);
  if (end <= start) return vec3(0.0);
  float travel = end - start;
  float extinction = 5.5;
  float transmittance = 1.0;
  vec3 scattered = vec3(0.0);
  float mu = dot(rayDir, sunDir);
  float forward = 0.42 + 0.58 * pow(max(mu, 0.0), 4.0);
  const int CLOUD_STEPS = 28;
  float jitter = hash12(gl_FragCoord.xy);
  for (int i = 0; i < CLOUD_STEPS; i++) {
    float f = (float(i) + jitter) / float(CLOUD_STEPS);
    float t = start + travel * f;
    vec3 point = vec3(0.0, OBSERVER_HEIGHT, 0.0) + rayDir * t;
    float height;
    float density = cloudDensity(point, height);
    if (density <= 0.006) continue;
    float shadow = cloudShadow(point, sunDir);
    vec3 sunlight = sunTransmittance(point, sunDir) * (1.0 - shadow * 0.96);
    vec3 ambient = skyAmbient * (0.22 + 0.32 * height);
    vec3 cloudRadiance = sunlight * forward * 0.82 + ambient * 0.42;
    float stepOptical = density * extinction * travel / float(CLOUD_STEPS);
    float stepTransmittance = exp(-stepOptical);
    scattered += transmittance * cloudRadiance * (1.0 - stepTransmittance);
    transmittance *= stepTransmittance;
    if (transmittance < 0.01) break;
  }
  cloudAlpha = 1.0 - transmittance;
  return scattered + skyAmbient * cloudAlpha * 0.04;
}

vec3 toneMap(vec3 color, float exposure) {
  return pow(1.0 - exp(-max(color, vec3(0.0)) * exposure), vec3(1.0 / 2.2));
}

void main() {
  vec2 uv = gl_FragCoord.xy / uResolution;
  float aspect = uResolution.x / uResolution.y;
  vec2 screen = uv * 2.0 - 1.0;
  float tanHalfFov = tan(radians(52.0) * 0.5);
  vec3 sunDir = normalize(uSunDirection);
  vec3 rayDir = normalize(vec3(
    screen.x * tanHalfFov * aspect,
    screen.y * tanHalfFov + 0.12,
    -1.0
  ));
  float sunElevation = radians(uSunElevation);
  vec3 ambient = skyRadiance(normalize(vec3(0.0, 0.45, -1.0)), sunDir);
  vec3 hdr;

  if (rayDir.y > 0.0) {
    hdr = skyRadiance(rayDir, sunDir);
    float cosSun = dot(rayDir, sunDir);
    float disk = smoothstep(0.99994, 0.999975, cosSun);
    float glow = pow(max(cosSun, 0.0), 720.0) * 0.08 +
      pow(max(cosSun, 0.0), 80.0) * 0.012;
    vec3 sunLight = sunTransmittance(vec3(0.0, OBSERVER_HEIGHT, 0.0), sunDir);
    vec3 solarTint = sunLight / max(max(sunLight.r, sunLight.g), max(sunLight.b, 0.001));
    vec3 sunEnergy = solarTint * (disk * 7.5 + glow * (0.4 + sunElevation));
    hdr += sunEnergy;

    float horizonHaze = exp(-max(rayDir.y, 0.0) * 28.0);
    float daylight = smoothstep(-0.06, 0.35, sunDir.y);
    vec3 hazeTint = mix(vec3(1.0, 0.52, 0.20), vec3(0.92, 0.95, 0.98), daylight);
    hdr += horizonHaze * hazeTint * (0.003 + 0.015 * daylight) *
      (0.7 + 0.3 * sunElevation);

    float cloudAlpha;
    vec3 cloud = renderClouds(rayDir, sunDir, ambient * 0.5 + hdr * 0.16, cloudAlpha);
    hdr = mix(hdr, cloud, cloudAlpha);
    hdr += sunEnergy * 0.24 * (1.0 - cloudAlpha * 0.72);
  } else {
    hdr = oceanColor(rayDir, sunDir, ambient);
    float horizon = smoothstep(-0.035, 0.0, rayDir.y);
    vec3 skyAtHorizon = skyRadiance(normalize(vec3(0.0, 0.004, -1.0)), sunDir);
    hdr = mix(hdr, skyAtHorizon, horizon * 0.35);
  }

  float exposure = mix(20.0, 24.0, smoothstep(-0.08, 0.9, sunDir.y));
  vec3 color = toneMap(hdr, exposure);
  float vignette = 1.0 - 0.18 * pow(length(screen * vec2(0.72, 0.62)), 2.2);
  color *= vignette;
  fragColor = vec4(color, 1.0);
}
`;
