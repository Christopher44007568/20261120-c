import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { buildConvergence, buildDirectionSets, buildContinuitySummary, summarizeContinuity } from "../src/analysis.js";
import {
  diskPolygonAreaError,
  initLTCData,
  integrateLTCAnalytic,
  integrateLTCMC,
  inverseLTCBlock,
  ltcMatrix3,
  makeDiskLight,
  makeRectLight,
  sampleLTCMatrix,
} from "../src/ltc.js";
import { length, mulberry32, normalize, dot } from "../src/math.js";
import { validateMesh, validateScene } from "../src/mesh.js";
import {
  compareImages,
  evaluateBoundaryContinuity,
  matrixSweep,
  maxSweepStep,
  renderSurface,
} from "../src/render.js";

const root = resolve(import.meta.dirname, "..");
const table = readFileSync(resolve(root, "src/ltc-data.bin"));
initLTCData(table.buffer.slice(table.byteOffset, table.byteOffset + table.byteLength));

function multiply3(a, b) {
  return a.map((row, i) =>
    [0, 1, 2].map((j) =>
      row[0] * b[0][j] + row[1] * b[1][j] + row[2] * b[2][j],
    ),
  );
}

{
  const matrix = sampleLTCMatrix(0.35, 0.7);
  assert.equal(matrix.length, 4);
  assert(matrix.every(Number.isFinite), "matrix values are finite");
  const inverse = ltcMatrix3(matrix);
  const forward = ltcMatrix3(inverseLTCBlock(matrix));
  const identity = multiply3(inverse, forward);
  for (let i = 0; i < 3; i += 1) {
    for (let j = 0; j < 3; j += 1) {
      assert.ok(Math.abs(identity[i][j] - (i === j ? 1 : 0)) < 1e-4);
    }
  }
}

{
  const rect = makeRectLight({ center: [-0.3, 0.25, 1.55], halfWidth: 0.8, halfHeight: 0.5 });
  const disk = makeDiskLight({
    center: [-0.3, 0.25, 1.55],
    radius: Math.sqrt(rect.area / Math.PI),
    segments: 128,
  });
  assert.ok(diskPolygonAreaError(128) < 5e-4, "disk polygon area converges");
  const point = [0.379, -0.557, 0];
  const normal = [0, 0, 1];
  const view = normalize([1.3 - point[0], -1.65 - point[1], 2.1 - point[2]]);
  const matrix = sampleLTCMatrix(0.24, dot(normal, view));
  for (const light of [rect, disk]) {
    const analytic = integrateLTCAnalytic(point, normal, view, light, matrix);
    const sampled = integrateLTCMC(point, normal, view, light, matrix, 400000, mulberry32(123));
    const relative = Math.abs(sampled - analytic) / analytic;
    assert(relative < 0.02, `${light.type} analytic/sample relative error ${relative}`);
  }
}

{
  const sets = buildDirectionSets(256, 33);
  assert.equal(sets.length, 4);
  for (const entry of sets) {
    assert.equal(entry.directions.length, 256);
    for (const direction of entry.directions) {
      assert.ok(Math.abs(length(direction) - 1) < 1e-9);
      assert.ok(direction[2] > -1e-9, "sampled LTC direction lies above horizon");
    }
  }
}

{
  const summary = buildContinuitySummary();
  const reduced = summarizeContinuity(summary);
  assert.ok(reduced.maxContinuousJump < 0.01, "continuous boundary jump under 1%");
  assert.ok(
    reduced.maxQuantizedJump > 10 * reduced.maxContinuousJump,
    "quantized control exposes a boundary jump",
  );
  const sweep = matrixSweep(0.7, 257);
  assert.ok(maxSweepStep(sweep) < 0.02, "LTC matrix sweep has no discrete step");
}

{
  const rect = buildConvergence("rect", { roughness: 0.24, seeds: 4 });
  const disk = buildConvergence("disk", { roughness: 0.24, seeds: 4 });
  const rectHigh = rect.points[rect.points.length - 1];
  const diskHigh = disk.points[disk.points.length - 1];
  assert.ok(rectHigh.relativeError < 0.02);
  assert.ok(diskHigh.relativeError < 0.02);
  assert.ok(rect.points[0].relativeError > rectHigh.relativeError);
}

{
  const width = 96;
  const height = 60;
  for (const emitter of ["rect", "disk"]) {
    const analytic = renderSurface({
      width,
      height,
      emitter,
      roughnessMode: "fixed",
      roughness: 0.12,
      method: "ltc",
    });
    const sampled = renderSurface({
      width,
      height,
      emitter,
      roughnessMode: "fixed",
      roughness: 0.12,
      method: "mc",
      spp: 128,
      seed: 41,
    });
    const metrics = compareImages(analytic, sampled, 1 / analytic.peak);
    assert.ok(metrics.shapeIoU > 0.85, `${emitter} shape IoU ${metrics.shapeIoU}`);
    assert.ok(metrics.energyError < 0.15, `${emitter} energy error ${metrics.energyError}`);
  }
}

{
  const valid = JSON.parse(readFileSync(resolve(root, "fixtures/valid-scene.json"), "utf8"));
  const invalid = JSON.parse(readFileSync(resolve(root, "fixtures/nonwatertight-scene.json"), "utf8"));
  const validReport = validateScene(valid);
  const invalidReport = validateScene(invalid);
  assert.equal(validReport.valid, true);
  assert.equal(validReport.mesh.stats.boundaryEdges, 0);
  assert.equal(validReport.mesh.stats.euler, 2);
  assert.equal(invalidReport.valid, false);
  assert.equal(invalidReport.mesh.stats.boundaryEdges, 4);
  assert.equal(invalidReport.mesh.stats.euler, 1);
  const nonManifold = structuredClone(valid.mesh);
  nonManifold.triangles.push([0, 1, 2]);
  const nonManifoldReport = validateMesh(nonManifold);
  assert.equal(nonManifoldReport.watertight, false);
  const degenerate = structuredClone(valid);
  degenerate.surface.roughnessMax = 1.4;
  assert.equal(validateScene(degenerate).valid, false);
}

{
  const boundary = evaluateBoundaryContinuity("rect");
  console.log(
    `[ok] continuity max=${(boundary.maxContinuousJump * 100).toFixed(4)}% ` +
    `quantized=${(boundary.maxQuantizedJump * 100).toFixed(2)}%`,
  );
}

console.log("all LTC core tests passed");
