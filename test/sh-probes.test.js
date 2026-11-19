import test from "node:test";
import assert from "node:assert/strict";
import {
  UP,
  ambientCoefficients,
  addPointLight,
  analyticPointLightIrradiance,
  evaluateIrradiance,
  luminance,
} from "../src/sh.js";
import { ProbeGrid, unionRects } from "../src/probe-grid.js";
import { DynamicProbeSimulation } from "../src/simulation.js";

const close = (actual, expected, tolerance, message) => {
  assert.ok(
    Math.abs(actual - expected) <= tolerance,
    `${message}: expected ${expected}, got ${actual}`,
  );
};

function pointLight(position = [0, 2, 0], intensity = 1, radius = 12) {
  return {
    position,
    color: [1, 1, 1],
    intensity,
    radius,
    softness: 0.25,
  };
}

test("ambient SH evaluates to the requested constant irradiance", () => {
  const coefficients = ambientCoefficients([0.2, 0.3, 0.4]);
  const rgb = evaluateIrradiance(coefficients, UP, new Float64Array(3));
  close(rgb[0], 0.2, 1e-12, "red");
  close(rgb[1], 0.3, 1e-12, "green");
  close(rgb[2], 0.4, 1e-12, "blue");
});

test("L2 point-light projection is close to analytic Lambert irradiance", () => {
  const probe = [0, 0, 0];
  const light = pointLight([0, 1, 0], 1, 12);
  const coefficients = new Float64Array(27);
  addPointLight(coefficients, probe, light);
  const projected = evaluateIrradiance(coefficients, UP, new Float64Array(3));
  const analytic = analyticPointLightIrradiance(
    probe,
    light,
    UP,
    new Float64Array(3),
  );
  const error = Math.abs(projected[0] - analytic[0]) / analytic[0];
  assert.ok(error < 0.08, `projection error ${error}`);
});

test("neighbor propagation contributes light beyond direct lighting", () => {
  const grid = new ProbeGrid({ cols: 5, rows: 5, ambient: [0, 0, 0] });
  const light = pointLight([0, 2, 0], 8, 8);
  grid.updateAll([light]);
  const center = grid.probeLuminance(2 * 5 + 2, "target");
  const neighbor = grid.probeLuminance(2 * 5 + 3, "target");
  const corner = grid.probeLuminance(0, "target");
  assert.ok(center > neighbor);
  assert.ok(neighbor > corner);
  assert.ok(neighbor > 0);
});

test("dirty-region rebuild matches a full rebuild", () => {
  const oldLight = pointLight([-1.5, 2, 0.4], 4, 4.2);
  const newLight = pointLight([1.25, 2, -0.35], 4, 4.2);
  const incremental = new ProbeGrid({ cols: 16, rows: 12 });
  incremental.updateAll([oldLight]);
  const rect = unionRects(
    incremental.rectForLights([oldLight]),
    incremental.rectForLights([newLight]),
  );
  incremental.updateRegion([newLight], rect);

  const reference = new ProbeGrid({ cols: 16, rows: 12 });
  reference.updateAll([newLight]);
  let maximumDifference = 0;
  for (let index = 0; index < incremental.target.length; index += 1) {
    maximumDifference = Math.max(
      maximumDifference,
      Math.abs(incremental.target[index] - reference.target[index]),
    );
  }
  assert.ok(maximumDifference < 1e-9, `max field difference ${maximumDifference}`);
});

test("bilinear probe interpolation is continuous across cell boundaries", () => {
  const grid = new ProbeGrid({ cols: 9, rows: 7 });
  grid.updateAll([pointLight([0.7, 2, 0.15], 4.8, 4.2)]);
  grid.resetDisplay();
  let previous = null;
  let maximumJump = 0;
  for (let step = 0; step <= 2000; step += 1) {
    const x = -4 + (8 * step) / 2000;
    const sampled = grid.sampleIrradiance([x, grid.y, 0.2], UP);
    const value = luminance(...sampled.rgb);
    if (previous !== null) maximumJump = Math.max(maximumJump, Math.abs(value - previous));
    previous = value;
  }
  assert.ok(maximumJump < 0.01, `maximum sampled luminance jump ${maximumJump}`);
});

test("on-demand updates stay continuous when interpolation weights cross probes", () => {
  const grid = new ProbeGrid({ cols: 14, rows: 10 });
  const simulation = new DynamicProbeSimulation({
    grid,
    mode: "ondemand",
    intervalMs: 120,
    smoothingTau: 0.065,
    speed: 0.72,
    lightCount: 1,
    qualityStride: 30,
  });
  for (let frame = 0; frame < 720; frame += 1) simulation.step(1 / 60);
  const summary = simulation.summary();
  assert.ok(summary.updateCount > 10);
  assert.ok(summary.boundaryEvents > 5);
  assert.ok(
    summary.maxBoundaryChannelJump < 0.08,
    `boundary jump ${summary.maxBoundaryChannelJump}`,
  );
  assert.ok(
    summary.boundaryJumpRatio < 1.6,
    `boundary/non-boundary jump ratio ${summary.boundaryJumpRatio}`,
  );
});

test("per-probe output contains complete SH coefficients and finite errors", () => {
  const simulation = new DynamicProbeSimulation({
    grid: new ProbeGrid({ cols: 8, rows: 6 }),
    mode: "ondemand",
    intervalMs: 50,
    qualityStride: 100,
  });
  for (let frame = 0; frame < 90; frame += 1) simulation.step(1 / 60);
  const rows = simulation.probeRows();
  assert.equal(rows.length, 48);
  for (const row of rows) {
    assert.equal(row.coefficients.length, 27);
    assert.ok(row.coefficients.every(Number.isFinite));
    assert.ok(Number.isFinite(row.displayLuminance));
    assert.ok(Number.isFinite(row.errorPct));
    assert.ok(Number.isFinite(row.projectionErrorPct));
  }
});

test("update plus interpolation p95 stays inside a 60 Hz frame budget", () => {
  const simulation = new DynamicProbeSimulation({
    grid: new ProbeGrid({ cols: 24, rows: 18 }),
    mode: "ondemand",
    intervalMs: 50,
    lightCount: 4,
    interpolationSamples: 128,
    qualityStride: 100,
  });
  for (let frame = 0; frame < 120; frame += 1) simulation.step(1 / 60);
  simulation.resetMetrics();
  for (let frame = 0; frame < 360; frame += 1) simulation.step(1 / 60);
  const summary = simulation.summary();
  assert.ok(summary.p95TotalMs < 1000 / 60, `p95 ${summary.p95TotalMs} ms`);
  assert.ok(summary.withinFrameBudget);
});

test("a one-frame update interval is not skipped by floating-point rounding", () => {
  const simulation = new DynamicProbeSimulation({
    grid: new ProbeGrid({ cols: 10, rows: 8 }),
    mode: "ondemand",
    intervalMs: 1000 / 60,
    speed: 1,
    qualityStride: 1000,
  });
  simulation.resetMetrics();
  for (let frame = 0; frame < 90; frame += 1) simulation.step(1 / 60);
  const summary = simulation.summary();
  assert.ok(summary.updateCount >= 88, `updates ${summary.updateCount}`);
});
