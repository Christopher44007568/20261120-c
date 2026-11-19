const DEG = Math.PI / 180;

export const EARTH_RADIUS_KM = 6360;
export const ATMOSPHERE_TOP_KM = 60;
export const DEFAULT_PARAMS = Object.freeze({
  sunElevation: 14,
  sunAzimuth: 16,
  rayleighScale: 1,
  mieScale: 0.82,
  cloudCoverage: 0.58,
  cloudThickness: 1.8,
  cloudShadows: true
});

export const ATMOSPHERE = Object.freeze({
  betaRayleighKm: [0.0058, 0.0135, 0.0331],
  betaMieKm: 0.021,
  rayleighScaleHeightKm: 8,
  mieScaleHeightKm: 1.2,
  observerAltitudeKm: 0.32,
  cloudBaseKm: 1.05,
  sunIlluminanceLux: 128000,
  ozoneOpticalDepth: 0.01,
  effectiveAirMass: 0.8
});

const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
const mix = (a, b, t) => a + (b - a) * t;

export function sunDirection(elevationDeg, azimuthDeg = DEFAULT_PARAMS.sunAzimuth) {
  const elevation = elevationDeg * DEG;
  const azimuth = azimuthDeg * DEG;
  return {
    x: Math.cos(elevation) * Math.sin(azimuth),
    y: Math.sin(elevation),
    z: -Math.cos(elevation) * Math.cos(azimuth)
  };
}

export function airMass(elevationDeg) {
  if (elevationDeg <= -1.5) return 80;
  const elevation = Math.max(-1.5, Math.min(90, elevationDeg));
  return 1 / (Math.sin(Math.max(0, elevation) * DEG) +
    0.50572 * Math.pow(elevation + 6.07995, -1.6364));
}

export function sunTransmittance(elevationDeg, rayleighScale = 1, mieScale = 0.82) {
  const path = ATMOSPHERE.effectiveAirMass * airMass(elevationDeg);
  return ATMOSPHERE.betaRayleighKm.map((beta, index) => {
    const optical = ATMOSPHERE.ozoneOpticalDepth + path * (
      beta * rayleighScale * ATMOSPHERE.rayleighScaleHeightKm +
      ATMOSPHERE.betaMieKm * mieScale * ATMOSPHERE.mieScaleHeightKm
    );
    return Math.exp(-optical);
  });
}

export function luminance(rgb) {
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
}

export function directIlluminance(elevationDeg, rayleighScale = 1, mieScale = 0.82) {
  const horizontal = Math.max(0, Math.sin(elevationDeg * DEG));
  return ATMOSPHERE.sunIlluminanceLux * horizontal *
    luminance(sunTransmittance(elevationDeg, rayleighScale, mieScale));
}

export function sunColor(elevationDeg, rayleighScale = 1, mieScale = 0.82) {
  const transmittance = sunTransmittance(elevationDeg, rayleighScale, mieScale);
  const peak = Math.max(...transmittance, 1e-9);
  const daylight = clamp((peak - 0.08) / 0.64);
  const exponent = 0.18 + 0.75 * (1 - daylight);
  return transmittance.map((channel) => {
    const toned = 0.9 * Math.pow(channel / peak, exponent);
    return Math.round(clamp(toned) * 255);
  });
}

function raySphere(origin, direction, center, radius) {
  const ox = origin.x - center.x;
  const oy = origin.y - center.y;
  const oz = origin.z - center.z;
  const b = ox * direction.x + oy * direction.y + oz * direction.z;
  const c = ox * ox + oy * oy + oz * oz - radius * radius;
  const discriminant = b * b - c;
  if (discriminant < 0) return null;
  const root = Math.sqrt(discriminant);
  return [-b - root, -b + root];
}

function densityAt(altitudeKm, rayleighScale, mieScale) {
  const safeAltitude = Math.max(0, altitudeKm);
  return {
    rayleigh: rayleighScale * Math.exp(-safeAltitude / ATMOSPHERE.rayleighScaleHeightKm),
    mie: mieScale * Math.exp(-safeAltitude / ATMOSPHERE.mieScaleHeightKm)
  };
}

function opticalDepth(origin, direction, lengthKm, sampleCount, rayleighScale, mieScale) {
  let rayleigh = 0;
  let mie = 0;
  const step = lengthKm / sampleCount;
  for (let i = 0; i < sampleCount; i += 1) {
    const t = (i + 0.5) * step;
    const point = {
      x: origin.x + direction.x * t,
      y: origin.y + direction.y * t,
      z: origin.z + direction.z * t
    };
    const altitude = Math.hypot(point.x, point.y + EARTH_RADIUS_KM, point.z) - EARTH_RADIUS_KM;
    if (altitude < 0) continue;
    const density = densityAt(altitude, rayleighScale, mieScale);
    rayleigh += density.rayleigh * step;
    mie += density.mie * step;
  }
  return { rayleigh, mie };
}

function sunOpticalDepth(origin, sunDir, rayleighScale, mieScale) {
  const center = { x: 0, y: -EARTH_RADIUS_KM, z: 0 };
  const ground = raySphere(origin, sunDir, center, EARTH_RADIUS_KM);
  const top = raySphere(origin, sunDir, center, EARTH_RADIUS_KM + ATMOSPHERE_TOP_KM);
  if (!top) return { rayleigh: 60, mie: 40 };
  const length = ground && ground[0] > 0 ? Math.min(top[1], ground[0]) : top[1];
  if (ground && ground[0] > 0) {
    return { rayleigh: 18 + top[1] * 0.35, mie: 12 + top[1] * 0.25 };
  }
  return opticalDepth(origin, sunDir, Math.max(0, length), 10, rayleighScale, mieScale);
}

export function rayleighPhase(cosTheta) {
  return 3 / (16 * Math.PI) * (1 + cosTheta * cosTheta);
}

export function miePhase(cosTheta, anisotropy = 0.76) {
  const g2 = anisotropy * anisotropy;
  const denominator = Math.pow(1 + g2 - 2 * anisotropy * cosTheta, 1.5);
  return (1 - g2) / (4 * Math.PI * Math.max(denominator, 1e-5));
}

export function skyRadiance(viewElevationDeg, viewAzimuthDeg, sunElevationDeg, options = {}) {
  const rayleighScale = options.rayleighScale ?? 1;
  const mieScale = options.mieScale ?? 0.82;
  const sunAzimuth = options.sunAzimuth ?? DEFAULT_PARAMS.sunAzimuth;
  const origin = { x: 0, y: ATMOSPHERE.observerAltitudeKm, z: 0 };
  const view = sunDirection(viewElevationDeg, viewAzimuthDeg);
  const sun = sunDirection(sunElevationDeg, sunAzimuth);
  const center = { x: 0, y: -EARTH_RADIUS_KM, z: 0 };
  const top = raySphere(origin, view, center, EARTH_RADIUS_KM + ATMOSPHERE_TOP_KM);
  if (!top) return [0, 0, 0];
  const ground = raySphere(origin, view, center, EARTH_RADIUS_KM);
  const end = ground && ground[0] > 0 ? Math.min(top[1], ground[0]) : top[1];
  const steps = options.steps ?? 28;
  const step = Math.max(0, end) / steps;
  const cosTheta = Math.max(-1, Math.min(1,
    view.x * sun.x + view.y * sun.y + view.z * sun.z));
  const phaseR = rayleighPhase(cosTheta);
  const phaseM = miePhase(cosTheta);
  const result = [0, 0, 0];
  let viewR = 0;
  let viewM = 0;
  for (let i = 0; i < steps; i += 1) {
    const t = (i + 0.5) * step;
    const point = {
      x: origin.x + view.x * t,
      y: origin.y + view.y * t,
      z: origin.z + view.z * t
    };
    const altitude = Math.hypot(point.x, point.y + EARTH_RADIUS_KM, point.z) - EARTH_RADIUS_KM;
    if (altitude < 0) break;
    const density = densityAt(altitude, rayleighScale, mieScale);
    viewR += density.rayleigh * step;
    viewM += density.mie * step;
    const sunOD = sunOpticalDepth(point, sun, rayleighScale, mieScale);
    const sunTrans = ATMOSPHERE.betaRayleighKm.map((beta, channel) =>
      Math.exp(-beta * sunOD.rayleigh - ATMOSPHERE.betaMieKm * mieScale * sunOD.mie -
        ATMOSPHERE.ozoneOpticalDepth * 0.7)
    );
    const viewTrans = ATMOSPHERE.betaRayleighKm.map((beta, channel) =>
      Math.exp(-beta * viewR - ATMOSPHERE.betaMieKm * mieScale * viewM)
    );
    for (let channel = 0; channel < 3; channel += 1) {
      const scattering = ATMOSPHERE.betaRayleighKm[channel] * density.rayleigh * phaseR +
        ATMOSPHERE.betaMieKm * mieScale * density.mie * phaseM;
      result[channel] += viewTrans[channel] * scattering * sunTrans[channel] * step;
    }
  }
  return result;
}

function toneMap(rgb, exposure) {
  return rgb.map((channel) => {
    const mapped = 1 - Math.exp(-Math.max(0, channel) * exposure);
    return Math.round(Math.pow(clamp(mapped), 1 / 2.2) * 255);
  });
}

export function skyColor(viewElevationDeg, sunElevationDeg, options = {}) {
  const radiance = skyRadiance(
    viewElevationDeg,
    options.viewAzimuth ?? DEFAULT_PARAMS.sunAzimuth,
    sunElevationDeg,
    options
  );
  const daylight = clamp((Math.sin(sunElevationDeg * DEG) + 0.05) / 0.55);
  const horizonHaze = Math.exp(-Math.max(0, viewElevationDeg) / 2.6) *
    (0.0015 + 0.052 * daylight);
  radiance[0] += horizonHaze * 0.95;
  radiance[1] += horizonHaze;
  radiance[2] += horizonHaze * 1.04;
  const exposure = options.exposure ?? 21;
  return toneMap(radiance, exposure);
}

export function cloudOpticalDepth(coverage, thicknessKm) {
  const coverageFactor = 0.16 + 3.15 * clamp(coverage);
  return Math.max(0, thicknessKm) * coverageFactor;
}

export function cloudShadowFraction(coverage, thicknessKm, shadows = true) {
  if (!shadows) return 0;
  return 1 - Math.exp(-cloudOpticalDepth(coverage, thicknessKm));
}

export function cloudProfile(params = DEFAULT_PARAMS) {
  const coverage = clamp(params.cloudCoverage);
  const thickness = Math.max(0.1, params.cloudThickness);
  const opticalDepth = cloudOpticalDepth(coverage, thickness);
  return {
    coverage,
    thickness,
    baseKm: ATMOSPHERE.cloudBaseKm,
    topKm: ATMOSPHERE.cloudBaseKm + thickness,
    opticalDepth,
    shadowFraction: cloudShadowFraction(coverage, thickness, params.cloudShadows)
  };
}

export function rgbToHex(rgb) {
  return `#${rgb.map((value) => Math.round(clamp(value, 0, 255))
    .toString(16).padStart(2, '0')).join('')}`;
}

export function elevationSweep(start = -6, end = 90, step = 3, options = {}) {
  const rows = [];
  for (let elevation = start; elevation <= end + 1e-9; elevation += step) {
    const zenith = skyColor(89.5, elevation, options);
    const horizon = skyColor(0.8, elevation, options);
    const direction = sunDirection(elevation, options.sunAzimuth ?? DEFAULT_PARAMS.sunAzimuth);
    const transmittance = sunTransmittance(elevation, options.rayleighScale, options.mieScale);
    rows.push({
      elevation,
      direction,
      sunColor: sunColor(elevation, options.rayleighScale, options.mieScale),
      zenith,
      horizon,
      transmittance: luminance(transmittance),
      directIlluminance: directIlluminance(elevation, options.rayleighScale, options.mieScale)
    });
  }
  return rows;
}

export function colorDistance(a, b) {
  return Math.max(...a.map((value, index) => Math.abs(value - b[index]))) / 255;
}

export { DEG, clamp, mix };
