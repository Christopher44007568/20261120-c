import { mulberry32 } from "./math.js";
import {
  integrateLTCAnalytic,
  integrateLTCMC,
  sampleLTCDirections,
  sampleLTCMatrix,
} from "./ltc.js";
import {
  DISK_LIGHT,
  PROBE_POINT,
  RECT_LIGHT,
  ROUGHNESS_BOUNDARIES,
  evaluateBoundaryContinuity,
  probeGeometry,
  surfaceView,
} from "./render.js";

export const CONVERGENCE_SPP = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024];

export function buildDirectionSets(count = 512, seed = 19) {
  const view = surfaceView(PROBE_POINT);
  return [0.08, 0.22, 0.42, 0.72].map((roughness, index) => ({
    roughness,
    directions: sampleLTCDirections(
      count,
      roughness,
      probeGeometry().ndotv,
      seed + index * 101,
      [0, 0, 1],
      view,
    ),
  }));
}

export function buildConvergence(emitter = "rect", {
  roughness = 0.24,
  seeds = 8,
  sppList = CONVERGENCE_SPP,
} = {}) {
  const light = emitter === "disk" ? DISK_LIGHT : RECT_LIGHT;
  const geometry = probeGeometry(roughness);
  const matrix = sampleLTCMatrix(roughness, geometry.ndotv);
  const analytic = integrateLTCAnalytic(
    geometry.point,
    geometry.normal,
    geometry.view,
    light,
    matrix,
  );
  const points = sppList.map((spp) => {
    const estimates = [];
    for (let seed = 0; seed < seeds; seed += 1) {
      estimates.push(integrateLTCMC(
        geometry.point,
        geometry.normal,
        geometry.view,
        light,
        matrix,
        spp,
        mulberry32(1009 + seed * 7919),
      ));
    }
    const mean = estimates.reduce((sum, value) => sum + value, 0) / estimates.length;
    const variance = estimates.reduce((sum, value) => sum + (value - mean) ** 2, 0) /
      Math.max(1, estimates.length - 1);
    return {
      spp,
      mean,
      relativeError: Math.abs(mean - analytic) / Math.max(Math.abs(analytic), 1e-9),
      standardError: Math.sqrt(variance / estimates.length) /
        Math.max(Math.abs(analytic), 1e-9),
      min: Math.min(...estimates),
      max: Math.max(...estimates),
    };
  });
  return {
    emitter,
    roughness,
    ndotv: geometry.ndotv,
    analytic,
    matrix,
    seeds,
    points,
  };
}

export function buildContinuitySummary() {
  const boundaryRoughness = ROUGHNESS_BOUNDARIES.map((entry) => entry.roughness);
  return {
    rect: evaluateBoundaryContinuity("rect"),
    disk: evaluateBoundaryContinuity("disk"),
    boundaryRoughness,
  };
}

export function summarizeContinuity(summary) {
  return {
    maxContinuousJump: Math.max(
      summary.rect.maxContinuousJump,
      summary.disk.maxContinuousJump,
    ),
    maxQuantizedJump: Math.max(
      summary.rect.maxQuantizedJump,
      summary.disk.maxQuantizedJump,
    ),
    maxMatrixDelta: Math.max(
      summary.rect.maxMatrixDelta,
      summary.disk.maxMatrixDelta,
    ),
  };
}
