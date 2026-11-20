import { drawReferenceRaster } from "./canvas-utils.js";
import { nearestPointOnSegments } from "./geometry.js";
import { reconstructCoverage } from "./msdf.js";

function percentile(values, ratio) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.round((sorted.length - 1) * ratio)));
  return sorted[index];
}

function evaluateChannel(specimen, field, reference, channelMode) {
  const { coverage, width, height, paddingPx, sizePx, shiftX, shiftY } = reference;
  const predictions = new Float32Array(width * height);
  const errorMap = new Uint8Array(width * height);
  const distances = [];
  let biasSum = 0;
  let mismatchCount = 0;
  let brokenCount = 0;
  let sampledErrorCount = 0;
  let absoluteCoverageError = 0;
  let comparedPixels = 0;

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x;
      const u = (x + 0.5 - paddingPx - shiftX) / sizePx;
      const v = (y + 0.5 - paddingPx - shiftY) / sizePx;
      const reconstruction = reconstructCoverage(field, u, v, sizePx, channelMode);
      const predicted = reconstruction.coverage;
      const actual = coverage[index];
      predictions[index] = predicted;

      const difference = Math.abs(predicted - actual);
      if (actual > 0.01 || predicted > 0.01) {
        absoluteCoverageError += difference;
        comparedPixels += 1;
      }

      const trueInside = actual >= 0.5;
      const renderedInside = predicted >= 0.5;
      const boundaryBand = actual > 0.04 && actual < 0.96;
      const mismatch = trueInside !== renderedInside;
      const broken = actual >= 0.82 && predicted < 0.35;

      if (broken) {
        brokenCount += 1;
        errorMap[index] = 2;
      } else if (mismatch && boundaryBand) {
        errorMap[index] = 1;
      } else if (difference > 0.28) {
        errorMap[index] = 3;
      }

      if (difference > 0.2) sampledErrorCount += 1;

      if (mismatch && boundaryBand) {
        const distancePx = nearestPointOnSegments(specimen.analysis.edges, u, v) * sizePx;
        const sign = trueInside ? -1 : 1;
        biasSum += sign * distancePx;
        distances.push(distancePx);
        mismatchCount += 1;
      }
    }
  }

  return {
    coverageMae: comparedPixels ? absoluteCoverageError / comparedPixels : 0,
    biasPx: mismatchCount ? biasSum / mismatchCount : 0,
    boundaryMaePx: distances.length
      ? distances.reduce((sum, value) => sum + value, 0) / distances.length
      : 0,
    boundaryP95Px: percentile(distances, 0.95),
    boundaryMismatch: mismatchCount,
    brokenPixels: brokenCount,
    sampledErrorPixels: sampledErrorCount,
    predictions,
    errorMap,
  };
}

export function evaluateSample(specimen, field, options = {}) {
  const {
    sizePx = 48,
    shiftX = 0,
    shiftY = 0,
    modes = ["msdf", "sdf"],
  } = options;
  const reference = drawReferenceRaster(specimen, sizePx, shiftX, shiftY);
  const msdf = modes.includes("msdf")
    ? evaluateChannel(specimen, field, reference, "msdf")
    : null;
  const sdf = modes.includes("sdf")
    ? evaluateChannel(specimen, field, reference, "sdf")
    : null;

  return {
    reference,
    msdf,
    sdf,
    settings: { sizePx, shiftX, shiftY, fieldSize: field.size },
  };
}

export function summarizeSweep(results) {
  if (!results.length) {
    return {
      worstBias: 0,
      maxBroken: 0,
      meanBias: 0,
      unstable: false,
    };
  }

  const biases = results.map((result) => result.msdf.biasPx);
  const broken = results.map((result) => result.msdf.brokenPixels);
  const worstBias = Math.max(...biases.map(Math.abs));
  const maxBroken = Math.max(...broken);
  const meanBias = biases.reduce((sum, value) => sum + value, 0) / biases.length;
  return {
    worstBias,
    maxBroken,
    meanBias,
    unstable: worstBias > 0.4 || maxBroken > 0,
  };
}
