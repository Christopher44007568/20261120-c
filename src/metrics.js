import {
  DEG,
  f32,
  lookAt,
  multiply,
  perspective,
  transformPoint,
} from "./math.js";
import { ROUTE, localToWorld } from "./scene.js";

function makeMatrix(camera, mode, origin, aspect) {
  const projection = new Float64Array(16);
  const view = new Float64Array(16);
  const combined = new Float64Array(16);
  perspective(projection, 48 * DEG, aspect, 0.45, 1700);

  let eye;
  if (mode === "raw") {
    eye = camera.eye;
  } else if (mode === "relative") {
    eye = [
      camera.eye[0] - origin[0],
      camera.eye[1],
      camera.eye[2] - origin[1],
    ];
  } else {
    eye = camera.eye;
  }

  const target = [
    eye[0] + camera.forward[0],
    eye[1] + camera.forward[1],
    eye[2] + camera.forward[2],
  ];
  lookAt(view, eye, target);
  multiply(combined, projection, view);
  return new Float32Array(combined);
}

export function projectWorld(camera, origin, mode, point, aspect, width, height) {
  const matrix = makeMatrix(camera, mode, origin, aspect);
  let sampled;
  if (mode === "raw") {
    sampled = point.map((value) => f32(value));
  } else if (mode === "relative") {
    sampled = [
      f32(point[0] - origin[0]),
      f32(point[1]),
      f32(point[2] - origin[1]),
    ];
  } else {
    sampled = point;
  }

  const clip = transformPoint(matrix, sampled).map((value) => f32(value));
  if (clip[3] <= 0.02) return null;
  const inverseW = 1 / clip[3];
  const x = (clip[0] * inverseW * 0.5 + 0.5) * width;
  const y = (0.5 - clip[1] * inverseW * 0.5) * height;
  return {
    x,
    y,
    depth: clip[3],
    visible: x >= 0 && x <= width && y >= 0 && y <= height,
  };
}

function exactProjection(camera, point, aspect) {
  const projection = new Float64Array(16);
  const view = new Float64Array(16);
  const combined = new Float64Array(16);
  perspective(projection, 48 * DEG, aspect, 0.45, 1700);
  const eye = camera.eye;
  lookAt(view, eye, [
    eye[0] + camera.forward[0],
    eye[1] + camera.forward[1],
    eye[2] + camera.forward[2],
  ]);
  multiply(combined, projection, view);
  const clip = transformPoint(combined, point);
  if (clip[3] <= 0.02) return null;
  const inverseW = 1 / clip[3];
  return {
    x: (clip[0] * inverseW * 0.5 + 0.5) * 1,
    y: (0.5 - clip[1] * inverseW * 0.5) * 1,
    depth: clip[3],
    clip,
  };
}

export function measureThinLineJitter(
  camera,
  routeDistance,
  origin,
  aspect,
  width,
  height,
) {
  let rawJitter = 0;
  let relativeJitter = 0;
  let samples = 0;

  for (let offset = -40; offset <= 190; offset += 7) {
    const point = ROUTE.pointAt(routeDistance + offset);
    const world = localToWorld(point.x, point.z, 0.055);
    const exact = exactProjection(camera, world, aspect);
    if (!exact || exact.depth < 18 || exact.depth > 380 || exact.x < -20 || exact.x > width + 20 || exact.y < -20 || exact.y > height + 20) {
      continue;
    }
    const exactX = exact.x * width;
    const exactY = exact.y * height;
    const raw = projectWorld(camera, origin, "raw", world, aspect, width, height);
    const relative = projectWorld(camera, origin, "relative", world, aspect, width, height);
    if (raw) rawJitter = Math.max(rawJitter, Math.hypot(raw.x - exactX, raw.y - exactY));
    if (relative) relativeJitter = Math.max(relativeJitter, Math.hypot(relative.x - exactX, relative.y - exactY));
    samples += 1;
  }

  return {
    raw: rawJitter,
    relative: relativeJitter,
    reference: 0,
    samples,
  };
}

function rayGround(eye, direction) {
  if (Math.abs(direction[1]) < 1e-9) return null;
  const distance = -eye[1] / direction[1];
  if (distance < 0) return null;
  return [
    eye[0] + direction[0] * distance,
    0,
    eye[2] + direction[2] * distance,
  ];
}

function rayDirection(camera, ndcX, ndcY, aspect) {
  const tangent = Math.tan(24 * DEG);
  const x = camera.forward[0] + camera.right[0] * ndcX * aspect * tangent + camera.up[0] * ndcY * tangent;
  const y = camera.forward[1] + camera.right[1] * ndcX * aspect * tangent + camera.up[1] * ndcY * tangent;
  const z = camera.forward[2] + camera.right[2] * ndcX * aspect * tangent + camera.up[2] * ndcY * tangent;
  const length = Math.hypot(x, y, z) || 1;
  return [x / length, y / length, z / length];
}

export function samplePick(camera, origin, aspect, ndcX = 0, ndcY = -0.48) {
  const direction = rayDirection(camera, ndcX, ndcY, aspect);
  const reference = rayGround(camera.eye, direction);
  if (!reference) return null;

  const rawEye = camera.eye.map((value) => f32(value));
  const rawDirection = direction.map((value) => f32(value));
  const raw = rayGround(rawEye, rawDirection);

  const relativeEye = [
    f32(camera.eye[0] - origin[0]),
    f32(camera.eye[1]),
    f32(camera.eye[2] - origin[1]),
  ];
  const relativeDirection = direction.map((value) => f32(value));
  const relativeLocal = rayGround(relativeEye, relativeDirection);
  const relative = relativeLocal
    ? [relativeLocal[0] + origin[0], 0, relativeLocal[2] + origin[1]]
    : null;

  return {
    reference,
    raw,
    relative,
    rawError: raw ? Math.hypot(raw[0] - reference[0], raw[2] - reference[2]) : Infinity,
    relativeError: relative
      ? Math.hypot(relative[0] - reference[0], relative[2] - reference[2])
      : Infinity,
  };
}

function projectBoth(camera, origin, mode, point, aspect, width, height) {
  const exact = exactProjection(camera, point, aspect);
  if (!exact) return null;
  const projected = projectWorld(camera, origin, mode, point, aspect, width, height);
  if (!projected) return null;
  return {
    exact: { x: exact.x * width, y: exact.y * height },
    mode: projected,
  };
}

export function measureRelocationJump(
  cameraBefore,
  cameraAfter,
  oldOrigin,
  newOrigin,
  anchors,
  aspect,
  width,
  height,
) {
  let rawJump = 0;
  let relativeJump = 0;
  let measured = 0;

  for (const point of anchors) {
    const rawBefore = projectBoth(cameraBefore, oldOrigin, "raw", point, aspect, width, height);
    const rawAfter = projectBoth(cameraAfter, oldOrigin, "raw", point, aspect, width, height);
    const relBefore = projectBoth(cameraBefore, oldOrigin, "relative", point, aspect, width, height);
    const relAfter = projectBoth(cameraAfter, newOrigin, "relative", point, aspect, width, height);
    if (!rawBefore || !rawAfter || !relBefore || !relAfter) continue;

    const exactDeltaX = rawAfter.exact.x - rawBefore.exact.x;
    const exactDeltaY = rawAfter.exact.y - rawBefore.exact.y;
    const rawDeltaX = rawAfter.mode.x - rawBefore.mode.x;
    const rawDeltaY = rawAfter.mode.y - rawBefore.mode.y;
    const relDeltaX = relAfter.mode.x - relBefore.mode.x;
    const relDeltaY = relAfter.mode.y - relBefore.mode.y;
    rawJump = Math.max(rawJump, Math.hypot(rawDeltaX - exactDeltaX, rawDeltaY - exactDeltaY));
    relativeJump = Math.max(relativeJump, Math.hypot(relDeltaX - exactDeltaX, relDeltaY - exactDeltaY));
    measured += 1;
  }

  return {
    raw: rawJump,
    relative: relativeJump,
    reference: 0,
    anchors: measured,
  };
}

export function projectPickToScreen(camera, origin, pick, aspect, width, height) {
  if (!pick) return null;
  const projected = projectWorld(camera, origin, "relative", pick, aspect, width, height);
  if (!projected || !projected.visible) return null;
  return projected;
}
