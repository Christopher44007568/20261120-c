export const SH_COUNT = 9;
export const SH_FLOATS = SH_COUNT * 3;
export const Y00 = 0.5 / Math.sqrt(Math.PI);
export const SH_CONVOLUTION = new Float64Array([
  Math.PI,
  2 * Math.PI / 3,
  2 * Math.PI / 3,
  2 * Math.PI / 3,
  Math.PI / 4,
  Math.PI / 4,
  Math.PI / 4,
  Math.PI / 4,
  Math.PI / 4,
]);

export const UP = new Float64Array([0, 1, 0]);

export function luminance(r, g, b) {
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function rgbLuminance(rgb) {
  return luminance(rgb[0], rgb[1], rgb[2]);
}

export function clamp01(value) {
  return Math.max(0, Math.min(1, value));
}

export function smoothstep(value) {
  const x = clamp01(value);
  return x * x * (3 - 2 * x);
}

export function shBasisNormalized(x, y, z, out = new Float64Array(SH_COUNT)) {
  out[0] = 0.28209479177387814;
  out[1] = 0.4886025119029199 * y;
  out[2] = 0.4886025119029199 * z;
  out[3] = 0.4886025119029199 * x;
  out[4] = 1.0925484305920792 * x * y;
  out[5] = 1.0925484305920792 * y * z;
  out[6] = 0.31539156525252005 * (3 * z * z - 1);
  out[7] = 1.0925484305920792 * x * z;
  out[8] = 0.5462742152960396 * (x * x - y * y);
  return out;
}

export function shBasis(x, y, z, out = new Float64Array(SH_COUNT)) {
  const length = Math.hypot(x, y, z) || 1;
  return shBasisNormalized(x / length, y / length, z / length, out);
}

export function ambientCoefficients(rgb, out = new Float64Array(SH_FLOATS)) {
  out.fill(0);
  out[0] = rgb[0] / Y00;
  out[1] = rgb[1] / Y00;
  out[2] = rgb[2] / Y00;
  return out;
}

export function pointLightAttenuation(distanceSq, light) {
  const radiusSq = light.radius * light.radius;
  if (distanceSq >= radiusSq) return 0;
  const edge = 1 - distanceSq / radiusSq;
  const window = edge * edge;
  const softness = light.softness ?? 0.25;
  return light.intensity * window / (softness + distanceSq);
}

/**
 * Adds the directional point-light contribution to pre-convolved L2 SH
 * irradiance coefficients. Coefficients are RGB-interleaved.
 */
export function addPointLight(
  coefficients,
  probePosition,
  light,
  basis = new Float64Array(SH_COUNT),
) {
  const dx = light.position[0] - probePosition[0];
  const dy = light.position[1] - probePosition[1];
  const dz = light.position[2] - probePosition[2];
  const distanceSq = dx * dx + dy * dy + dz * dz;
  const energy = pointLightAttenuation(distanceSq, light);
  if (energy === 0) return 0;

  const invDistance = 1 / Math.sqrt(distanceSq);
  shBasisNormalized(dx * invDistance, dy * invDistance, dz * invDistance, basis);
  for (let sh = 0; sh < SH_COUNT; sh += 1) {
    const weight = energy * SH_CONVOLUTION[sh] * basis[sh];
    const offset = sh * 3;
    coefficients[offset] += light.color[0] * weight;
    coefficients[offset + 1] += light.color[1] * weight;
    coefficients[offset + 2] += light.color[2] * weight;
  }
  return energy;
}

export function evaluateIrradiance(
  coefficients,
  normal,
  out = new Float64Array(3),
  basis = new Float64Array(SH_COUNT),
) {
  shBasis(normal[0], normal[1], normal[2], basis);
  let r = 0;
  let g = 0;
  let b = 0;
  for (let sh = 0; sh < SH_COUNT; sh += 1) {
    const y = basis[sh];
    const offset = sh * 3;
    r += coefficients[offset] * y;
    g += coefficients[offset + 1] * y;
    b += coefficients[offset + 2] * y;
  }
  out[0] = r;
  out[1] = g;
  out[2] = b;
  return out;
}

export function clampIrradiance(rgb) {
  rgb[0] = Math.max(0, rgb[0]);
  rgb[1] = Math.max(0, rgb[1]);
  rgb[2] = Math.max(0, rgb[2]);
  return rgb;
}

export function analyticPointLightIrradiance(
  probePosition,
  light,
  normal,
  out = new Float64Array(3),
) {
  const dx = light.position[0] - probePosition[0];
  const dy = light.position[1] - probePosition[1];
  const dz = light.position[2] - probePosition[2];
  const distanceSq = dx * dx + dy * dy + dz * dz;
  const invDistance = distanceSq > 1e-12 ? 1 / Math.sqrt(distanceSq) : 0;
  const cosine = Math.max(
    0,
    normal[0] * dx * invDistance +
      normal[1] * dy * invDistance +
      normal[2] * dz * invDistance,
  );
  const energy = pointLightAttenuation(distanceSq, light) * cosine;
  out[0] = light.color[0] * energy;
  out[1] = light.color[1] * energy;
  out[2] = light.color[2] * energy;
  return out;
}

export function addScaled(destination, source, scale, length = SH_FLOATS) {
  for (let index = 0; index < length; index += 1) {
    destination[index] += source[index] * scale;
  }
}

