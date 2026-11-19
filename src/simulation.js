import {
  SH_FLOATS,
  UP,
  addPointLight,
  analyticPointLightIrradiance,
  clampIrradiance,
  evaluateIrradiance,
  luminance,
} from "./sh.js";
import { ProbeGrid, unionRects } from "./probe-grid.js";

const TAU = Math.PI * 2;

export function objectPositionAt(time, grid, speed = 0.55, out = new Float64Array(3)) {
  const width = (grid.cols - 1) * grid.spacing;
  const depth = (grid.rows - 1) * grid.spacing;
  out[0] = Math.sin(time * speed + 0.25) * width * 0.44;
  out[1] = grid.y + 0.12;
  out[2] = Math.sin(time * speed * 1.37 + 0.8) * depth * 0.36;
  return out;
}

export function createLightRig(objectPosition, count = 1) {
  const lights = [];
  for (let index = 0; index < count; index += 1) {
    const angle = (index / Math.max(1, count)) * TAU + 0.35;
    const spread = count === 1 ? 0 : 0.55 + 0.14 * (index % 2);
    const warm = index % 3 === 0;
    const cool = index % 3 === 2;
    lights.push({
      position: [
        objectPosition[0] + Math.cos(angle) * spread,
        count === 1 ? 2.25 : 2.05 + (index % 2) * 0.3,
        objectPosition[2] + Math.sin(angle) * spread,
      ],
      color: warm
        ? [1, 0.74, 0.42]
        : cool
          ? [0.48, 0.72, 1]
          : [1, 0.95, 0.82],
      intensity: count === 1 ? 4.8 : 2.35,
      radius: count === 1 ? 4.2 : 3.8,
      softness: 0.28,
    });
  }
  return lights;
}

export function cloneLights(lights) {
  return lights.map((light) => ({
    ...light,
    position: [...light.position],
    color: [...light.color],
  }));
}

export function lightsDiffer(a, b, motionEpsilon = 0.02) {
  if (a.length !== b.length) return true;
  for (let index = 0; index < a.length; index += 1) {
    const left = a[index];
    const right = b[index];
    const distance = Math.hypot(
      left.position[0] - right.position[0],
      left.position[1] - right.position[1],
      left.position[2] - right.position[2],
    );
    const colorDelta =
      Math.abs(left.color[0] - right.color[0]) +
      Math.abs(left.color[1] - right.color[1]) +
      Math.abs(left.color[2] - right.color[2]);
    if (
      distance > motionEpsilon ||
      colorDelta > 0.005 ||
      Math.abs(left.intensity - right.intensity) > 0.01
    ) {
      return true;
    }
  }
  return false;
}

function percentile(values, fraction) {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const position = (sorted.length - 1) * fraction;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  const mix = position - lower;
  return sorted[lower] * (1 - mix) + sorted[upper] * mix;
}

export class DynamicProbeSimulation {
  constructor({
    grid = new ProbeGrid(),
    mode = "ondemand",
    intervalMs = 50,
    smoothingTau = 0.065,
    speed = 0.55,
    lightCount = 1,
    motionEpsilon = 0.025,
    interpolationSamples = 0,
    qualityStride = 12,
  } = {}) {
    this.grid = grid;
    this.mode = mode;
    this.intervalMs = intervalMs;
    this.smoothingTau = smoothingTau;
    this.speed = speed;
    this.lightCount = lightCount;
    this.motionEpsilon = motionEpsilon;
    this.interpolationSamples = interpolationSamples;
    this.qualityStride = qualityStride;

    this.time = 0;
    this.frameIndex = 0;
    this.updateCount = 0;
    this.lastUpdateTime = -Infinity;
    this.objectPosition = objectPositionAt(this.time, grid, speed);
    this.currentLights = createLightRig(this.objectPosition, lightCount);
    this.anchorLights = cloneLights(this.currentLights);
    this.grid.updateAll(this.currentLights);
    this.grid.resetDisplay();

    this.previousRgb = new Float64Array(3);
    this.objectRgb = new Float64Array(3);
    this.objectCoefficients = new Float64Array(SH_FLOATS);
    this.interpolationCoefficients = new Float64Array(SH_FLOATS);
    this.interpolationRgb = new Float64Array(3);
    this.shBasis = new Float64Array(9);
    this.previousCellKey = "";
    this.boundaryEvents = 0;
    this.maxBoundaryJump = 0;
    this.maxObjectJump = 0;
    this.maxLuminanceJump = 0;
    this.history = [];
    this.qualityHistory = [];
    this.lastProbeRows = [];
    this._buildInterpolationPoints();

    this._sampleObject();
    this.previousRgb.set(this.objectRgb);
    const cell = this.grid.cellAt(this.objectPosition);
    this.previousCellKey = `${cell.row0}:${cell.col0}`;
  }

  _buildInterpolationPoints() {
    this.interpolationPoints = [];
    const count = Math.max(0, this.interpolationSamples);
    for (let index = 0; index < count; index += 1) {
      const col = ((index * 7) % 97) / 96;
      const row = ((index * 17 + 11) % 89) / 88;
      this.interpolationPoints.push([
        this.grid.minX + col * (this.grid.cols - 1) * this.grid.spacing,
        this.grid.y + 0.12,
        this.grid.minZ + row * (this.grid.rows - 1) * this.grid.spacing,
      ]);
    }
  }

  _sampleObject() {
    const sampled = this.grid.sampleCoefficients(
      this.objectPosition,
      this.objectCoefficients,
    );
    evaluateIrradiance(sampled.coefficients, UP, this.objectRgb, this.shBasis);
    clampIrradiance(this.objectRgb);
    return sampled;
  }

  _runInterpolationWorkload() {
    for (const point of this.interpolationPoints) {
      const sampled = this.grid.sampleCoefficients(
        point,
        this.interpolationCoefficients,
      );
      evaluateIrradiance(
        sampled.coefficients,
        UP,
        this.interpolationRgb,
        this.shBasis,
      );
    }
  }

  step(dt = 1 / 60) {
    const safeDt = Math.max(0, Math.min(dt, 0.25));
    this.time += safeDt;
    objectPositionAt(this.time, this.grid, this.speed, this.objectPosition);
    this.currentLights = createLightRig(this.objectPosition, this.lightCount);

    const dirty = lightsDiffer(
      this.anchorLights,
      this.currentLights,
      this.motionEpsilon,
    );
    const elapsedMs = (this.time - this.lastUpdateTime) * 1000;
    const shouldRebuild =
      this.mode === "frame" ||
      (dirty && (this.intervalMs <= 0 || elapsedMs + 1e-6 >= this.intervalMs));

    let rebuildMs = 0;
    let updatedProbes = 0;
    if (shouldRebuild) {
      const start = performance.now();
      if (this.mode === "frame") {
        this.grid.updateAll(this.currentLights);
      } else {
        const rect = unionRects(
          this.grid.rectForLights(this.anchorLights),
          this.grid.rectForLights(this.currentLights),
        );
        this.grid.updateRegion(this.currentLights, rect);
      }
      rebuildMs = performance.now() - start;
      updatedProbes = this.grid.lastStats.updatedProbes;
      this.anchorLights = cloneLights(this.currentLights);
      this.lastUpdateTime = this.time;
      this.updateCount += 1;
    }

    const smoothStart = performance.now();
    const alpha =
      this.smoothingTau <= 0 ? 1 : 1 - Math.exp(-safeDt / this.smoothingTau);
    this.grid.smoothDisplay(alpha);
    const smoothingMs = performance.now() - smoothStart;

    const interpolationStart = performance.now();
    const sampled = this._sampleObject();
    this._runInterpolationWorkload();
    const interpolationMs = performance.now() - interpolationStart;

    const jump = Math.max(
      Math.abs(this.objectRgb[0] - this.previousRgb[0]),
      Math.abs(this.objectRgb[1] - this.previousRgb[1]),
      Math.abs(this.objectRgb[2] - this.previousRgb[2]),
    );
    this.maxObjectJump = Math.max(this.maxObjectJump, jump);
    const luminanceJump = Math.abs(
      luminance(this.objectRgb[0], this.objectRgb[1], this.objectRgb[2]) -
        luminance(this.previousRgb[0], this.previousRgb[1], this.previousRgb[2]),
    );
    this.maxLuminanceJump = Math.max(this.maxLuminanceJump, luminanceJump);

    const cell = this.grid.cellAt(this.objectPosition);
    const cellKey = `${cell.row0}:${cell.col0}`;
    const crossedBoundary = cellKey !== this.previousCellKey;
    if (crossedBoundary) {
      this.boundaryEvents += 1;
      this.maxBoundaryJump = Math.max(this.maxBoundaryJump, jump);
    }
    this.previousCellKey = cellKey;

    const totalMs = rebuildMs + smoothingMs + interpolationMs;
    const record = {
      frame: this.frameIndex,
      time: this.time,
      rebuildMs,
      smoothingMs,
      interpolationMs,
      totalMs,
      updatedProbes,
      rebuild: shouldRebuild,
      rgb: [...this.objectRgb],
      luminance: luminance(this.objectRgb[0], this.objectRgb[1], this.objectRgb[2]),
      jump,
      crossedBoundary,
      weights: { ...sampled.weights },
    };

    if (this.frameIndex % this.qualityStride === 0) {
      record.quality = this.measureQuality();
    }
    this.history.push(record);
    this.previousRgb.set(this.objectRgb);
    this.frameIndex += 1;
    return record;
  }

  _luminanceErrors(referenceTarget) {
    const errors = [];
    const rgb = new Float64Array(3);
    let referenceSum = 0;
    for (let probe = 0; probe < this.grid.count; probe += 1) {
      const offset = probe * SH_FLOATS;
      const displayCoefficients = this.grid.display.subarray(
        offset,
        offset + SH_FLOATS,
      );
      const referenceCoefficients = referenceTarget.subarray(
        offset,
        offset + SH_FLOATS,
      );
      evaluateIrradiance(displayCoefficients, UP, rgb, this.shBasis);
      clampIrradiance(rgb);
      const displayLuminance = luminance(rgb[0], rgb[1], rgb[2]);
      evaluateIrradiance(referenceCoefficients, UP, rgb, this.shBasis);
      clampIrradiance(rgb);
      const referenceLuminance = luminance(rgb[0], rgb[1], rgb[2]);
      const absolute = Math.abs(displayLuminance - referenceLuminance);
      errors.push({
        probe,
        displayLuminance,
        referenceLuminance,
        absoluteError: absolute,
        errorPct: 0,
      });
      referenceSum += referenceLuminance;
    }
    const meanReferenceLuminance = referenceSum / Math.max(1, errors.length);
    const normalization = Math.max(meanReferenceLuminance, 0.015);
    let sum = 0;
    let hardMax = 0;
    for (const entry of errors) {
      entry.errorPct = (entry.absoluteError / normalization) * 100;
      sum += entry.errorPct;
      hardMax = Math.max(hardMax, entry.errorPct);
    }
    const sorted = errors.map((entry) => entry.errorPct).sort((a, b) => a - b);
    return {
      meanPct: sum / Math.max(1, errors.length),
      p95Pct: percentile(sorted, 0.95),
      maxPct: hardMax,
      meanReferenceLuminance,
      errors,
    };
  }

  measureQuality() {
    const referenceTarget = this.grid.computeReference(this.currentLights);
    const result = this._luminanceErrors(referenceTarget);
    const point = {
      time: this.time,
      meanPct: result.meanPct,
      p95Pct: result.p95Pct,
      maxPct: result.maxPct,
    };
    this.qualityHistory.push(point);
    return point;
  }

  probeRows(referenceTarget = this.grid.computeReference(this.currentLights)) {
    const rows = [];
    const rgb = new Float64Array(3);
    const directCoefficients = new Float64Array(SH_FLOATS);
    const exactDirect = new Float64Array(3);
    const shDirect = new Float64Array(3);
    const probePosition = new Float64Array(3);
    const referenceLuminances = new Float64Array(this.grid.count);
    let referenceSum = 0;

    for (let probe = 0; probe < this.grid.count; probe += 1) {
      const offset = probe * SH_FLOATS;
      const reference = referenceTarget.subarray(offset, offset + SH_FLOATS);
      evaluateIrradiance(reference, UP, rgb, this.shBasis);
      clampIrradiance(rgb);
      referenceLuminances[probe] = luminance(rgb[0], rgb[1], rgb[2]);
      referenceSum += referenceLuminances[probe];
    }
    const normalization = Math.max(referenceSum / Math.max(1, this.grid.count), 0.015);

    for (let probe = 0; probe < this.grid.count; probe += 1) {
      const offset = probe * SH_FLOATS;
      this.grid.probePosition(probe, probePosition);
      const display = this.grid.display.subarray(offset, offset + SH_FLOATS);
      evaluateIrradiance(display, UP, rgb, this.shBasis);
      clampIrradiance(rgb);
      const displayLuminance = luminance(rgb[0], rgb[1], rgb[2]);
      const referenceLuminance = referenceLuminances[probe];

      directCoefficients.fill(0);
      exactDirect.fill(0);
      for (const light of this.currentLights) {
        addPointLight(directCoefficients, probePosition, light, this.shBasis);
        analyticPointLightIrradiance(
          probePosition,
          light,
          UP,
          rgb,
        );
        exactDirect[0] += rgb[0];
        exactDirect[1] += rgb[1];
        exactDirect[2] += rgb[2];
      }
      evaluateIrradiance(directCoefficients, UP, shDirect, this.shBasis);
      clampIrradiance(shDirect);
      const exactDirectLuminance = luminance(
        exactDirect[0],
        exactDirect[1],
        exactDirect[2],
      );
      const projectedDirectLuminance = luminance(shDirect[0], shDirect[1], shDirect[2]);
      const projectionErrorPct =
        exactDirectLuminance < 1e-5
          ? 0
          : (Math.abs(projectedDirectLuminance - exactDirectLuminance) /
              exactDirectLuminance) *
            100;
      const errorPct =
        (Math.abs(displayLuminance - referenceLuminance) / normalization) * 100;

      rows.push({
        probe,
        row: Math.floor(probe / this.grid.cols),
        col: probe % this.grid.cols,
        x: probePosition[0],
        y: probePosition[1],
        z: probePosition[2],
        coefficients: Array.from(display),
        displayLuminance,
        referenceLuminance,
        absoluteError: Math.abs(displayLuminance - referenceLuminance),
        errorPct,
        projectionErrorPct,
        updateAgeMs: Math.max(0, (this.time - this.lastUpdateTime) * 1000),
      });
    }
    this.lastProbeRows = rows;
    return rows;
  }

  resetMetrics() {
    this.updateCount = 0;
    this.frameIndex = 0;
    this.boundaryEvents = 0;
    this.maxBoundaryJump = 0;
    this.maxObjectJump = 0;
    this.maxLuminanceJump = 0;
    this.history = [];
    this.qualityHistory = [];
    this.lastProbeRows = [];
  }

  summary() {
    const rebuild = this.history.map((entry) => entry.rebuildMs);
    const smoothing = this.history.map((entry) => entry.smoothingMs);
    const interpolation = this.history.map((entry) => entry.interpolationMs);
    const total = this.history.map((entry) => entry.totalMs);
    const sum = (values) => values.reduce((value, next) => value + next, 0);
    const mean = (values) => (values.length ? sum(values) / values.length : 0);
    const quality = this.qualityHistory;
    const meanLumErrorPct = mean(quality.map((point) => point.meanPct));
    const maxLumErrorPct = quality.length
      ? Math.max(...quality.map((point) => point.maxPct))
      : 0;
    const meanP95LumErrorPct = mean(quality.map((point) => point.p95Pct));
    const p95TotalMs = percentile(total, 0.95);
    const nonBoundaryJumps = this.history
      .filter((entry) => !entry.crossedBoundary)
      .map((entry) => entry.jump);
    const maxNonBoundaryJump = nonBoundaryJumps.length
      ? Math.max(...nonBoundaryJumps)
      : 0;

    return {
      mode: this.mode,
      intervalMs: this.intervalMs,
      smoothingTauMs: this.smoothingTau * 1000,
      frames: this.history.length,
      updateCount: this.updateCount,
      rebuildFrames: this.history.filter((entry) => entry.rebuild).length,
      totalRebuildMs: sum(rebuild),
      totalSmoothingMs: sum(smoothing),
      totalInterpolationMs: sum(interpolation),
      totalMeasuredMs: sum(total),
      meanRebuildMs: mean(rebuild),
      meanSmoothingMs: mean(smoothing),
      meanInterpolationMs: mean(interpolation),
      meanTotalMs: mean(total),
      p95RebuildMs: percentile(rebuild, 0.95),
      p95TotalMs,
      maxTotalMs: total.length ? Math.max(...total) : 0,
      meanLumErrorPct,
      meanP95LumErrorPct,
      maxLumErrorPct,
      maxObjectChannelJump: this.maxObjectJump,
      maxLuminanceJump: this.maxLuminanceJump,
      boundaryEvents: this.boundaryEvents,
      maxBoundaryChannelJump: this.maxBoundaryJump,
      maxNonBoundaryChannelJump: maxNonBoundaryJump,
      boundaryJumpRatio:
        maxNonBoundaryJump > 0
          ? this.maxBoundaryJump / maxNonBoundaryJump
          : 1,
      interpolationSamplesPerFrame: this.interpolationSamples + 1,
      frameBudgetMs: 1000 / 60,
      withinFrameBudget: p95TotalMs < 1000 / 60,
      grid: {
        cols: this.grid.cols,
        rows: this.grid.rows,
        probeCount: this.grid.count,
        lightCount: this.lightCount,
      },
      lastStats: { ...this.grid.lastStats },
    };
  }
}
