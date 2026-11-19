export const WAVELENGTHS = Array.from({ length: 81 }, (_, index) => 380 + index * 5);
export const PAINT_ANGLES = Array.from({ length: 16 }, (_, index) => index * 5);

export const PAINT_PRESETS = {
  cobalt: {
    name: "Cobalt Flux",
    shortName: "深钴蓝",
    peaks: [
      [454, 38, 0.54],
      [505, 52, 0.15],
      [640, 70, 0.04],
    ],
    neutral: 0.055,
  },
  ember: {
    name: "Ember Phase",
    shortName: "熔岩橙",
    peaks: [
      [612, 55, 0.63],
      [565, 42, 0.23],
      [460, 60, 0.03],
    ],
    neutral: 0.065,
  },
  silver: {
    name: "Titan Silver",
    shortName: "钛银",
    peaks: [
      [468, 72, 0.16],
      [604, 100, 0.08],
    ],
    neutral: 0.48,
  },
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function gaussian(x, center, sigma) {
  return Math.exp(-0.5 * ((x - center) / sigma) ** 2);
}

function baseReflectance(wavelength, preset) {
  const p = PAINT_PRESETS[preset];
  let value = p.neutral;
  for (const [center, width, amplitude] of p.peaks) {
    value += amplitude * gaussian(wavelength, center, width);
  }
  return clamp(value, 0.025, 0.88);
}

function fresnel(cosIncident, n1, n2) {
  const eta = n1 / n2;
  const sin2Transmitted = eta * eta * Math.max(0, 1 - cosIncident * cosIncident);
  if (sin2Transmitted >= 1) return 1;
  const cosTransmitted = Math.sqrt(1 - sin2Transmitted);
  const rs = (n1 * cosIncident - n2 * cosTransmitted)
    / (n1 * cosIncident + n2 * cosTransmitted);
  const rp = (n2 * cosIncident - n1 * cosTransmitted)
    / (n2 * cosIncident + n1 * cosTransmitted);
  return clamp((rs * rs + rp * rp) * 0.5, 0, 1);
}

function cieColor(wavelength) {
  const lobe = (x, center, left, right) => {
    const width = x < center ? left : right;
    return Math.exp(-0.5 * ((x - center) / width) ** 2);
  };
  const x = 1.056 * lobe(wavelength, 599.8, 37.9, 31.0)
    + 0.362 * lobe(wavelength, 442.0, 16.0, 26.7)
    - 0.065 * lobe(wavelength, 501.1, 20.4, 26.2);
  const y = 0.821 * lobe(wavelength, 568.8, 46.9, 40.5)
    + 0.286 * lobe(wavelength, 530.9, 16.3, 31.1);
  const z = 1.217 * lobe(wavelength, 437.0, 11.8, 36.0)
    + 0.681 * lobe(wavelength, 459.0, 26.0, 13.8);
  return [x, y, z];
}

function toSrgb(xyz) {
  let r = 3.2406 * xyz[0] - 1.5372 * xyz[1] - 0.4986 * xyz[2];
  let g = -0.9689 * xyz[0] + 1.8758 * xyz[1] + 0.0415 * xyz[2];
  let b = 0.0557 * xyz[0] - 0.204 * xyz[1] + 1.057 * xyz[2];
  const peak = Math.max(r, g, b, 1e-6);
  r /= peak;
  g /= peak;
  b /= peak;
  return [r, g, b].map((value) => {
    const linear = clamp(value, 0, 1);
    return linear <= 0.0031308
      ? 12.92 * linear
      : 1.055 * linear ** (1 / 2.4) - 0.055;
  });
}

function rgbToHex(rgb) {
  return `#${rgb.map((value) => (
    Math.round(clamp(value, 0, 1) * 255).toString(16).padStart(2, "0")
  )).join("")}`;
}

export function paintSpectrum(preset = "cobalt", angleDeg = 35) {
  const angle = clamp(angleDeg, 0, 78);
  const radians = (angle * Math.PI) / 180;
  const cosIncident = Math.max(0.08, Math.cos(radians));
  const nAir = 1;
  const nCoat = 1.52;
  const r0 = fresnel(cosIncident, nAir, nCoat);
  const t0 = 1 - r0;
  const eta = nAir / nCoat;
  const cosCoat = Math.sqrt(Math.max(0.01, 1 - (eta * Math.sin(radians)) ** 2));
  const coatDistance = 45 / cosCoat;
  const primerDistance = 25 / cosCoat;
  const wavelengths = [];
  const reflectances = [];
  const transmissions = [];
  const absorptions = [];
  const coatAbsorptions = [];
  const baseAbsorptions = [];
  const primerAbsorptions = [];
  const surfaceReflections = [];
  const baseReflections = [];
  const multiReflections = [];
  const totals = {
    R: 0, T: 0, A: 0, surface: 0, firstBounce: 0, multiple: 0,
    coatAbs: 0, baseAbs: 0, primerAbs: 0,
  };
  const xyz = [0, 0, 0];

  for (const wavelength of WAVELENGTHS) {
    const alphaCoat = 0.0008 + 0.00045 * ((wavelength - 380) / 400) ** 2;
    const alphaPrimer = 0.0065 + 0.0015 * gaussian(wavelength, 520, 90);
    const coatAttenuation = Math.exp(-alphaCoat * coatDistance);
    const primerAttenuation = Math.exp(-alphaPrimer * primerDistance);
    const rb = baseReflectance(wavelength, preset);
    const tb = 0.042 * (1 - rb);
    const transmitted = t0 * coatAttenuation;
    let incident = transmitted;
    let reflection = r0;
    let transmission = 0;
    let firstBounce = 0;
    let multiple = 0;
    let coatAbs = t0 * (1 - coatAttenuation);
    let baseAbs = 0;
    let primerAbs = 0;

    for (let bounce = 0; bounce < 12; bounce += 1) {
      const baseReflection = incident * rb;
      const baseTransmission = incident * tb;
      baseAbs += Math.max(0, incident - baseReflection - baseTransmission);
      transmission += baseTransmission * primerAttenuation;
      primerAbs += baseTransmission * (1 - primerAttenuation);

      const returning = baseReflection * coatAttenuation;
      const escaped = returning * t0;
      if (bounce === 0) firstBounce = escaped;
      else multiple += escaped;
      reflection += escaped;

      const internal = returning * r0;
      coatAbs += internal * (1 - coatAttenuation);
      incident = internal * coatAttenuation;
    }

    transmission = clamp(transmission, 0, 1);
    reflection = clamp(reflection, 0, 1);
    const absorption = clamp(1 - reflection - transmission, 0, 1);
    wavelengths.push(wavelength);
    reflectances.push(reflection);
    transmissions.push(transmission);
    absorptions.push(absorption);
    coatAbsorptions.push(coatAbs);
    baseAbsorptions.push(baseAbs);
    primerAbsorptions.push(primerAbs);
    surfaceReflections.push(r0);
    baseReflections.push(firstBounce);
    multiReflections.push(multiple);

    totals.R += reflection;
    totals.T += transmission;
    totals.A += absorption;
    totals.surface += r0;
    totals.firstBounce += firstBounce;
    totals.multiple += multiple;
    totals.coatAbs += coatAbs;
    totals.baseAbs += baseAbs;
    totals.primerAbs += primerAbs;
    const cie = cieColor(wavelength);
    xyz[0] += reflection * cie[0];
    xyz[1] += reflection * cie[1];
    xyz[2] += reflection * cie[2];
  }

  const count = WAVELENGTHS.length;
  for (const key of Object.keys(totals)) totals[key] /= count;
  const rgb = toSrgb(xyz);
  const energyTotal = totals.R + totals.T + totals.A;
  return {
    preset,
    angle,
    wavelengths,
    reflectances,
    transmissions,
    absorptions,
    coatAbsorptions,
    baseAbsorptions,
    primerAbsorptions,
    surfaceReflections,
    baseReflections,
    multiReflections,
    totals,
    energyTotal,
    energyError: Math.abs(energyTotal - 1),
    rgb,
    hex: rgbToHex(rgb),
  };
}

export function colorResponse(preset = "cobalt") {
  return PAINT_ANGLES.map((angle) => {
    const spectrum = paintSpectrum(preset, angle);
    return {
      angle,
      rgb: spectrum.rgb,
      hex: spectrum.hex,
      reflectance: spectrum.totals.R,
      chroma: Math.max(...spectrum.rgb) - Math.min(...spectrum.rgb),
    };
  });
}

export function energyAudit(preset = "cobalt") {
  let maxError = 0;
  let maxTotalDeviation = 0;
  for (const angle of PAINT_ANGLES) {
    const spectrum = paintSpectrum(preset, angle);
    maxError = Math.max(maxError, spectrum.energyError);
    maxTotalDeviation = Math.max(maxTotalDeviation, Math.abs(spectrum.energyTotal - 1));
  }
  return { maxError: Math.max(maxError, maxTotalDeviation) };
}

export function spectrumColorAt(wavelength) {
  const bands = [
    [380, 440, [0.24, 0.18, 0.82]],
    [440, 490, [0.1, 0.48, 0.95]],
    [490, 540, [0.15, 0.84, 0.74]],
    [540, 590, [0.74, 0.94, 0.26]],
    [590, 640, [1, 0.66, 0.18]],
    [640, 700, [1, 0.26, 0.15]],
    [700, 781, [0.68, 0.12, 0.18]],
  ];
  const band = bands.find(([start, end]) => wavelength >= start && wavelength < end) ?? bands[6];
  return band[2];
}
