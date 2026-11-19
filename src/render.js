import {
  clamp,
  dot,
  lerp,
  mulberry32,
  normalize,
} from "./math.js";
import {
  integrateLTCAnalytic,
  integrateLTCMC,
  makeDiskLight,
  makeRectLight,
  sampleLTCMatrix,
  sampleLTCMatrixQuantized,
} from "./ltc.js";

export const SURFACE = {
  minX: -1.4,
  maxX: 1.4,
  minY: -0.86,
  maxY: 0.86,
  normal: [0, 0, 1],
  camera: [1.3, -1.65, 2.1],
};

export const LIGHT_CENTER = [-0.3, 0.25, 1.55];
export const RECT_LIGHT = makeRectLight({
  center: LIGHT_CENTER,
  halfWidth: 0.8,
  halfHeight: 0.5,
});
export const DISK_LIGHT = makeDiskLight({
  center: LIGHT_CENTER,
  radius: Math.sqrt(RECT_LIGHT.area / Math.PI),
  segments: 128,
});

export const ROUGHNESS_KNOTS = [
  { u: 0, roughness: 0.045 },
  { u: 0.22, roughness: 0.14 },
  { u: 0.48, roughness: 0.32 },
  { u: 0.74, roughness: 0.58 },
  { u: 1, roughness: 0.82 },
];

export const ROUGHNESS_BOUNDARIES = ROUGHNESS_KNOTS.slice(1, -1);
export const PROBE_POINT = [0.379, -0.557, 0];

export function roughnessAt(u, mode = "gradient", fixedRoughness = 0.24) {
  if (mode === "fixed") return fixedRoughness;
  const t = clamp(u, 0, 1);
  for (let i = 0; i < ROUGHNESS_KNOTS.length - 1; i += 1) {
    const a = ROUGHNESS_KNOTS[i];
    const b = ROUGHNESS_KNOTS[i + 1];
    if (t <= b.u) {
      return lerp(a.roughness, b.roughness, (t - a.u) / (b.u - a.u));
    }
  }
  return ROUGHNESS_KNOTS[ROUGHNESS_KNOTS.length - 1].roughness;
}

export function surfacePoint(u, v) {
  return [
    lerp(SURFACE.minX, SURFACE.maxX, u),
    lerp(SURFACE.minY, SURFACE.maxY, v),
    0,
  ];
}

export function surfaceView(point) {
  return normalize([
    SURFACE.camera[0] - point[0],
    SURFACE.camera[1] - point[1],
    SURFACE.camera[2] - point[2],
  ]);
}

export function lightForType(type) {
  return type === "disk" ? DISK_LIGHT : RECT_LIGHT;
}

function pixelSeed(seed, index) {
  let value = (seed ^ Math.imul(index + 1, 0x9e3779b1)) >>> 0;
  value ^= value >>> 16;
  value = Math.imul(value, 0x7feb352d) >>> 0;
  value ^= value >>> 15;
  return value >>> 0;
}

export function renderSurface({
  width = 320,
  height = 196,
  emitter = "rect",
  roughnessMode = "fixed",
  roughness = 0.24,
  method = "ltc",
  spp = 16,
  seed = 7,
  quantizeRoughness = false,
  quantizeLevels = 8,
} = {}) {
  const light = lightForType(emitter);
  const luminance = new Float32Array(width * height);
  const roughnessMap = new Float32Array(width * height);
  let peak = 0;
  let sum = 0;

  for (let y = 0; y < height; y += 1) {
    const v = 1 - (y + 0.5) / height;
    for (let x = 0; x < width; x += 1) {
      const u = (x + 0.5) / width;
      const point = surfacePoint(u, v);
      const normal = SURFACE.normal;
      const view = surfaceView(point);
      const ndotv = Math.max(0.05, dot(normal, view));
      const localRoughness = roughnessAt(u, roughnessMode, roughness);
      const matrix = quantizeRoughness
        ? sampleLTCMatrixQuantized(localRoughness, ndotv, quantizeLevels)
        : sampleLTCMatrix(localRoughness, ndotv);
      let value;
      if (method === "ltc") {
        value = integrateLTCAnalytic(point, normal, view, light, matrix);
      } else {
        const random = mulberry32(pixelSeed(seed, y * width + x));
        value = integrateLTCMC(point, normal, view, light, matrix, spp, random);
      }
      const index = y * width + x;
      luminance[index] = value;
      roughnessMap[index] = localRoughness;
      peak = Math.max(peak, value);
      sum += value;
    }
  }

  return {
    width,
    height,
    luminance,
    roughnessMap,
    peak,
    mean: sum / luminance.length,
    emitter,
    method,
    spp: method === "mc" ? spp : 0,
  };
}

export function normalizeImage(image, scale) {
  const normalized = new Float32Array(image.luminance.length);
  for (let i = 0; i < normalized.length; i += 1) {
    normalized[i] = image.luminance[i] * scale;
  }
  return normalized;
}

const COLOR_STOPS = [
  [0, [7, 9, 15]],
  [0.08, [14, 22, 35]],
  [0.28, [25, 68, 91]],
  [0.55, [55, 155, 166]],
  [0.78, [235, 193, 111]],
  [1, [255, 247, 213]],
];

export function palette(value) {
  const x = clamp(value, 0, 1);
  for (let i = 0; i < COLOR_STOPS.length - 1; i += 1) {
    const a = COLOR_STOPS[i];
    const b = COLOR_STOPS[i + 1];
    if (x <= b[0]) {
      const t = (x - a[0]) / (b[0] - a[0]);
      return [
        Math.round(lerp(a[1][0], b[1][0], t)),
        Math.round(lerp(a[1][1], b[1][1], t)),
        Math.round(lerp(a[1][2], b[1][2], t)),
        255,
      ];
    }
  }
  return [...COLOR_STOPS[COLOR_STOPS.length - 1][1], 255];
}

export function imageToRGBA(image, scale, exposure = 2.7, background = 0.008) {
  const rgba = new Uint8ClampedArray(image.width * image.height * 4);
  for (let i = 0; i < image.luminance.length; i += 1) {
    const linear = background + image.luminance[i] * scale;
    const tone = 1 - Math.exp(-linear * exposure);
    const color = palette(tone);
    rgba[i * 4] = color[0];
    rgba[i * 4 + 1] = color[1];
    rgba[i * 4 + 2] = color[2];
    rgba[i * 4 + 3] = 255;
  }
  return rgba;
}

export function compareImages(analytic, sampled, scale = 1) {
  if (analytic.luminance.length !== sampled.luminance.length) {
    throw new Error("images must have identical dimensions");
  }
  const a = analytic.luminance;
  const b = sampled.luminance;
  let squareError = 0;
  let absError = 0;
  let signedError = 0;
  let sumA = 0;
  let sumB = 0;
  let peakA = 0;
  let peakB = 0;
  for (let i = 0; i < a.length; i += 1) {
    const av = a[i] * scale;
    const bv = b[i] * scale;
    squareError += (bv - av) ** 2;
    absError += Math.abs(bv - av);
    signedError += bv - av;
    sumA += av;
    sumB += bv;
    peakA = Math.max(peakA, av);
    peakB = Math.max(peakB, bv);
  }
  const threshold = Math.max(peakA * 0.14, 1e-9);
  let intersect = 0;
  let union = 0;
  let countA = 0;
  let countB = 0;
  let cxA = 0;
  let cyA = 0;
  let cxB = 0;
  let cyB = 0;
  for (let i = 0; i < a.length; i += 1) {
    const inA = a[i] * scale >= threshold;
    const inB = b[i] * scale >= threshold;
    if (inA) {
      countA += 1;
      cxA += i % analytic.width;
      cyA += Math.floor(i / analytic.width);
    }
    if (inB) {
      countB += 1;
      cxB += i % analytic.width;
      cyB += Math.floor(i / analytic.width);
    }
    if (inA && inB) intersect += 1;
    if (inA || inB) union += 1;
  }
  const centroidA = countA
    ? [cxA / countA, cyA / countA]
    : [0, 0];
  const centroidB = countB
    ? [cxB / countB, cyB / countB]
    : [0, 0];
  const residualMean = signedError / a.length;
  let residualVariance = 0;
  for (let i = 0; i < a.length; i += 1) {
    residualVariance += ((b[i] * scale - a[i] * scale) - residualMean) ** 2;
  }
  return {
    rmse: Math.sqrt(squareError / a.length),
    relativeRmse: Math.sqrt(squareError / a.length) / Math.max(peakA, 1e-9),
    relativeL1: absError / Math.max(sumA, 1e-9),
    energyError: Math.abs(sumB - sumA) / Math.max(sumA, 1e-9),
    residualStd: Math.sqrt(residualVariance / a.length) / Math.max(peakA, 1e-9),
    peakRatio: peakB / Math.max(peakA, 1e-9),
    shapeIoU: union ? intersect / union : 0,
    centroidOffset: Math.hypot(centroidA[0] - centroidB[0], centroidA[1] - centroidB[1]),
    highlightPixels: countA,
  };
}

export function probeGeometry(roughness = 0.3) {
  const point = PROBE_POINT;
  const view = surfaceView(point);
  const ndotv = dot(SURFACE.normal, view);
  return {
    point,
    normal: SURFACE.normal,
    view,
    ndotv,
    roughness,
    matrix: sampleLTCMatrix(roughness, ndotv),
  };
}

export function evaluateBoundaryContinuity(emitter = "rect", delta = 1e-4) {
  const geometry = probeGeometry();
  const light = lightForType(emitter);
  const k = 1 / delta;
  const rows = [];
  for (const boundary of ROUGHNESS_BOUNDARIES) {
    const left = boundary.roughness - delta;
    const right = boundary.roughness + delta;
    const matrixLeft = sampleLTCMatrix(left, geometry.ndotv);
    const matrixRight = sampleLTCMatrix(right, geometry.ndotv);
    const quantLeft = sampleLTCMatrixQuantized(left, geometry.ndotv, 8);
    const quantRight = sampleLTCMatrixQuantized(right, geometry.ndotv, 8);
    const ltcLeft = integrateLTCAnalytic(
      geometry.point,
      geometry.normal,
      geometry.view,
      light,
      matrixLeft,
    );
    const ltcRight = integrateLTCAnalytic(
      geometry.point,
      geometry.normal,
      geometry.view,
      light,
      matrixRight,
    );
    const quantizedLeft = integrateLTCAnalytic(
      geometry.point,
      geometry.normal,
      geometry.view,
      light,
      quantLeft,
    );
    const quantizedRight = integrateLTCAnalytic(
      geometry.point,
      geometry.normal,
      geometry.view,
      light,
      quantRight,
    );
    const denominator = Math.max(Math.abs(ltcLeft), Math.abs(ltcRight), 1e-9);
    rows.push({
      u: boundary.u,
      roughness: boundary.roughness,
      continuousJump: Math.abs(ltcRight - ltcLeft) / denominator,
      quantizedJump: Math.abs(quantizedRight - quantizedLeft) /
        Math.max(Math.abs(quantizedLeft), Math.abs(quantizedRight), 1e-9),
      leftLuminance: ltcLeft,
      rightLuminance: ltcRight,
      slope: (ltcRight - ltcLeft) / (2 * delta),
      matrixDelta: matrixRight.map((value, index) => value - matrixLeft[index]),
      quantizedMatrixDelta: quantRight.map((value, index) => value - quantLeft[index]),
    });
  }
  let quantizedMaxJump = 0;
  let quantizedAt = 0;
  let previousQuantized = null;
  for (let i = 0; i <= 4000; i += 1) {
    const r = i / 4000;
    const matrix = sampleLTCMatrixQuantized(r, geometry.ndotv, 8);
    const value = integrateLTCAnalytic(
      geometry.point,
      geometry.normal,
      geometry.view,
      light,
      matrix,
    );
    if (previousQuantized !== null) {
      const jump = Math.abs(value - previousQuantized) /
        Math.max(Math.abs(value), Math.abs(previousQuantized), 1e-9);
      if (jump > quantizedMaxJump) {
        quantizedMaxJump = jump;
        quantizedAt = r;
      }
    }
    previousQuantized = value;
  }
  return {
    emitter,
    delta,
    rows,
    maxContinuousJump: Math.max(...rows.map((row) => row.continuousJump)),
    maxQuantizedJump: quantizedMaxJump,
    quantizedJumpAt: quantizedAt,
    maxMatrixDelta: Math.max(
      ...rows.flatMap((row) => row.matrixDelta.map((value) => Math.abs(value))),
    ),
    normalizer: k,
  };
}

export function matrixSweep(ndotv = 0.7, samples = 257) {
  const result = [];
  for (let i = 0; i < samples; i += 1) {
    const roughness = i / (samples - 1);
    result.push({
      roughness,
      values: sampleLTCMatrix(roughness, ndotv),
    });
  }
  return result;
}

export function maxSweepStep(sweep) {
  let maxStep = 0;
  for (let i = 1; i < sweep.length; i += 1) {
    for (let channel = 0; channel < 4; channel += 1) {
      maxStep = Math.max(
        maxStep,
        Math.abs(sweep[i].values[channel] - sweep[i - 1].values[channel]),
      );
    }
  }
  return maxStep;
}
