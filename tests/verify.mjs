import assert from "node:assert/strict";
import {
  HANGARS,
  ROUTE,
  createCamera,
  localToWorld,
  routeStartDistance,
  worldTileOrigin,
} from "../src/scene.js";
import {
  measureRelocationJump,
  measureThinLineJitter,
  samplePick,
} from "../src/metrics.js";

const aspect = 360 / 560;
const width = 360;
const height = 560;
const start = routeStartDistance();

let previousCamera = createCamera(start, -0.11, 0);
let previousOrigin = worldTileOrigin(previousCamera.eye[0], previousCamera.eye[2]);
let crossings = 0;
let maxRelativeJump = 0;
let maxRelativeJitter = 0;
let minRawJitter = Infinity;
const probe = samplePick(previousCamera, previousOrigin, aspect);
const target = localToWorld(HANGARS[1].x, HANGARS[1].z);
const anchorPoints = HANGARS.slice(0, 3).map((hangar) => (
  localToWorld(hangar.x, hangar.z, hangar.height * 0.7)
));

assert.ok(probe, "programmatic ground pick should hit the plane");
assert.ok(probe.relativeError < 0.001, "camera-relative pick error should be sub-millimeter");
assert.ok(probe.rawError > probe.relativeError * 20, "raw FP32 should show a materially larger pick error");

for (
  let distance = start;
  distance < start + ROUTE.length * 3;
  distance += 3
) {
  const camera = createCamera(distance, -0.11, 0);
  const origin = worldTileOrigin(camera.eye[0], camera.eye[2]);
  const crossed = origin[0] !== previousOrigin[0] || origin[1] !== previousOrigin[1];

  if (crossed) {
    crossings += 1;
    const jump = measureRelocationJump(
      previousCamera,
      camera,
      previousOrigin,
      origin,
      anchorPoints,
      aspect,
      width,
      height,
    );
    maxRelativeJump = Math.max(maxRelativeJump, jump.relative);
    assert.ok(
      jump.relative < 0.1,
      `relative relocation jump should stay below 0.1 px, got ${jump.relative}`,
    );
  }

  if (crossings % 3 === 0 && crossings > 0) {
    const jitter = measureThinLineJitter(camera, distance, origin, aspect, width, height);
    maxRelativeJitter = Math.max(maxRelativeJitter, jitter.relative);
    minRawJitter = Math.min(minRawJitter, jitter.raw);
  }

  const pickRelX = Math.fround(probe.reference[0] - origin[0]);
  const pickRelZ = Math.fround(probe.reference[2] - origin[1]);
  const targetRelX = Math.fround(target[0] - origin[0]);
  const targetRelZ = Math.fround(target[2] - origin[1]);
  const quantizedSpan = Math.hypot(targetRelX - pickRelX, targetRelZ - pickRelZ);
  const exactSpan = Math.hypot(target[0] - probe.reference[0], target[2] - probe.reference[2]);
  assert.ok(
    Math.abs(quantizedSpan - exactSpan) < 0.0001,
    "relative pick-to-hangar vector should stay continuous across origins",
  );

  previousCamera = camera;
  previousOrigin = origin;
}

assert.ok(crossings >= 8, `route should cross at least 8 partition edges, got ${crossings}`);
assert.ok(maxRelativeJitter < 0.02, `relative line jitter should stay tiny, got ${maxRelativeJitter}`);
assert.ok(minRawJitter > 0.5, `raw FP32 jitter should remain visible, got ${minRawJitter}`);

console.log("ORIGIN SHIFT verification passed");
console.log(`  partition crossings: ${crossings}`);
console.log(`  max relative line jitter: ${maxRelativeJitter.toFixed(6)} px`);
console.log(`  min raw FP32 line jitter: ${minRawJitter.toFixed(3)} px`);
console.log(`  max relative relocation jump: ${maxRelativeJump.toFixed(6)} px`);
console.log(`  pick error (relative): ${probe.relativeError.toExponential(2)} m`);
console.log(`  pick error (raw FP32): ${probe.rawError.toExponential(2)} m`);
