import {
  EPSILON,
  HemisphereTracker,
  add,
  canonicalQuaternion,
  cross,
  mat4FromQuaternionTranslation,
  mat4FromQuaternion,
  mat4Identity,
  mat4InvertRigid,
  mat4Multiply,
  mat4Translation,
  quatConjugate,
  quatDot,
  quatFromAxisAngle,
  quatIdentity,
  quatLength,
  quatMultiply,
  quatNegate,
  quatNormalize,
  quatRotateVector,
  quatScale,
} from "./math.js";

const MAX_BONES = 8;
const ZERO_WEIGHT_EPSILON = 1e-8;

export function createRig(bindMatrices, jointAxis, jointZ, sign = 1) {
  const rootBind = bindMatrices[0] ?? mat4Identity();
  const jointBind = bindMatrices[1] ?? mat4Translation([0, 0, jointZ]);
  const localJoint = mat4Multiply(mat4InvertRigid(rootBind), jointBind);
  return {
    axis: jointAxis,
    jointZ,
    sign,
    parents: [-1, 0],
    bindMatrices: [rootBind, jointBind],
    inverseBinds: [mat4InvertRigid(rootBind), mat4InvertRigid(jointBind)],
    localJoint,
  };
}

export function buildJointTransforms(rig, angle, sign = rig.sign ?? 1) {
  const jointRotation = quatFromAxisAngle(rig.axis, angle);
  const signedJointRotation = sign < 0 ? quatNegate(jointRotation) : jointRotation;
  const rootPose = mat4FromQuaternion(quatIdentity());
  const jointPoseBase = mat4Multiply(rootPose, rig.localJoint);
  const jointPose = mat4Multiply(jointPoseBase, mat4FromQuaternion(signedJointRotation));
  const rootQuaternion = quatIdentity();
  const jointQuaternion = quatMultiply(rootQuaternion, signedJointRotation);
  return {
    worldMatrices: [rootPose, jointPose],
    worldQuaternions: [rootQuaternion, jointQuaternion],
  };
}

export function buildSkinningPalette(rig, angle, options = {}) {
  const sign = options.sign ?? rig.sign ?? 1;
  const tracker = options.tracker ?? new HemisphereTracker();
  const transforms = buildJointTransforms(rig, angle, sign);
  const boneCount = rig.bindMatrices.length;
  const matrices = new Float32Array(MAX_BONES * 16);
  const dualReal = new Float32Array(MAX_BONES * 4);
  const dualDual = new Float32Array(MAX_BONES * 4);
  const rotations = [];

  for (let bone = 0; bone < boneCount; bone += 1) {
    const skinMatrix = mat4Multiply(transforms.worldMatrices[bone], rig.inverseBinds[bone]);
    const skinQuaternion = quatMultiply(
      transforms.worldQuaternions[bone],
      quatConjugate(canonicalQuaternion(readBindQuaternion(rig.bindMatrices[bone]))),
    );
    const aligned = tracker.track(`bone-${bone}`, skinQuaternion);
    const translation = [skinMatrix[12], skinMatrix[13], skinMatrix[14]];
    const stableMatrix = mat4FromQuaternionTranslation(aligned, translation);
    const dual = dualQuaternionFromRigid(aligned, translation);
    matrices.set(stableMatrix, bone * 16);
    dualReal.set(dual.real, bone * 4);
    dualDual.set(dual.dual, bone * 4);
    rotations.push(aligned);
  }

  return {
    matrices,
    dualReal,
    dualDual,
    rotations,
    boneCount,
    angle,
    sign,
  };
}

function readBindQuaternion(bindMatrix) {
  const trace = bindMatrix[0] + bindMatrix[5] + bindMatrix[10];
  if (trace > 0) {
    const s = Math.sqrt(trace + 1) * 2;
    return [(bindMatrix[6] - bindMatrix[9]) / s, (bindMatrix[8] - bindMatrix[2]) / s, (bindMatrix[1] - bindMatrix[4]) / s, 0.25 * s];
  }
  if (bindMatrix[0] > bindMatrix[5] && bindMatrix[0] > bindMatrix[10]) {
    const s = Math.sqrt(1 + bindMatrix[0] - bindMatrix[5] - bindMatrix[10]) * 2;
    return [0.25 * s, (bindMatrix[1] + bindMatrix[4]) / s, (bindMatrix[2] + bindMatrix[8]) / s, (bindMatrix[6] - bindMatrix[9]) / s];
  }
  if (bindMatrix[5] > bindMatrix[10]) {
    const s = Math.sqrt(1 + bindMatrix[5] - bindMatrix[0] - bindMatrix[10]) * 2;
    return [(bindMatrix[1] + bindMatrix[4]) / s, 0.25 * s, (bindMatrix[6] + bindMatrix[9]) / s, (bindMatrix[8] - bindMatrix[2]) / s];
  }
  const s = Math.sqrt(1 + bindMatrix[10] - bindMatrix[0] - bindMatrix[5]) * 2;
  return [(bindMatrix[2] + bindMatrix[8]) / s, (bindMatrix[6] + bindMatrix[9]) / s, 0.25 * s, (bindMatrix[1] - bindMatrix[4]) / s];
}

export function dualQuaternionFromRigid(quaternion, translation) {
  const real = quatNormalize(quaternion);
  const translationQuaternion = [translation[0], translation[1], translation[2], 0];
  return {
    real,
    dual: quatScale(quatMultiply(translationQuaternion, real), 0.5),
  };
}

export function normalizeDualQuaternion(dualQuaternion) {
  const len = quatLength(dualQuaternion.real);
  if (len <= EPSILON) {
    return { real: quatIdentity(), dual: [0, 0, 0, 0] };
  }
  return {
    real: quatScale(dualQuaternion.real, 1 / len),
    dual: quatScale(dualQuaternion.dual, 1 / len),
  };
}

export function transformPointDualQuaternion(dualQuaternion, point) {
  const normalized = normalizeDualQuaternion(dualQuaternion);
  const real = normalized.real;
  const dual = normalized.dual;
  const rotated = quatRotateVector(real, point);
  const translation = [
    2 * (real[3] * dual[0] - dual[3] * real[0] + real[1] * dual[2] - real[2] * dual[1]),
    2 * (real[3] * dual[1] - dual[3] * real[1] + real[2] * dual[0] - real[0] * dual[2]),
    2 * (real[3] * dual[2] - dual[3] * real[2] + real[0] * dual[1] - real[1] * dual[0]),
  ];
  return add(rotated, translation);
}

function accumulateWeights(skinIndex, skinWeight, offset) {
  const entries = [];
  let total = 0;
  for (let lane = 0; lane < 4; lane += 1) {
    const weight = skinWeight[offset + lane] ?? 0;
    if (weight <= 0) continue;
    entries.push([skinIndex[offset + lane] ?? 0, weight]);
    total += weight;
  }
  return { entries, total };
}

export function skinVertexLBS(point, skinIndex, skinWeight, offset, palette, out = [0, 0, 0]) {
  const { entries, total } = accumulateWeights(skinIndex, skinWeight, offset);
  if (total <= ZERO_WEIGHT_EPSILON) {
    out[0] = point[0];
    out[1] = point[1];
    out[2] = point[2];
    return out;
  }
  let x = 0;
  let y = 0;
  let z = 0;
  for (const [bone, weight] of entries) {
    const normalizedWeight = weight / total;
    const matrix = palette.matrices;
    const base = bone * 16;
    x += normalizedWeight * (matrix[base] * point[0] + matrix[base + 4] * point[1] + matrix[base + 8] * point[2] + matrix[base + 12]);
    y += normalizedWeight * (matrix[base + 1] * point[0] + matrix[base + 5] * point[1] + matrix[base + 9] * point[2] + matrix[base + 13]);
    z += normalizedWeight * (matrix[base + 2] * point[0] + matrix[base + 6] * point[1] + matrix[base + 10] * point[2] + matrix[base + 14]);
  }
  out[0] = x;
  out[1] = y;
  out[2] = z;
  return out;
}

export function skinVertexDQS(point, skinIndex, skinWeight, offset, palette, out = [0, 0, 0]) {
  const { entries, total } = accumulateWeights(skinIndex, skinWeight, offset);
  if (total <= ZERO_WEIGHT_EPSILON) {
    out[0] = point[0];
    out[1] = point[1];
    out[2] = point[2];
    return out;
  }
  const real = [0, 0, 0, 0];
  const dual = [0, 0, 0, 0];
  for (const [bone, weight] of entries) {
    const normalizedWeight = weight / total;
    const base = bone * 4;
    for (let component = 0; component < 4; component += 1) {
      real[component] += normalizedWeight * palette.dualReal[base + component];
      dual[component] += normalizedWeight * palette.dualDual[base + component];
    }
  }
  return transformPointDualQuaternion({ real, dual }, point);
}

export function skinVertexNormalLBS(normal, skinIndex, skinWeight, offset, palette) {
  const { entries, total } = accumulateWeights(skinIndex, skinWeight, offset);
  if (total <= ZERO_WEIGHT_EPSILON) return [...normal];
  const out = [0, 0, 0];
  for (const [bone, weight] of entries) {
    const normalizedWeight = weight / total;
    const matrix = palette.matrices;
    const base = bone * 16;
    out[0] += normalizedWeight * (matrix[base] * normal[0] + matrix[base + 4] * normal[1] + matrix[base + 8] * normal[2]);
    out[1] += normalizedWeight * (matrix[base + 1] * normal[0] + matrix[base + 5] * normal[1] + matrix[base + 9] * normal[2]);
    out[2] += normalizedWeight * (matrix[base + 2] * normal[0] + matrix[base + 6] * normal[1] + matrix[base + 10] * normal[2]);
  }
  return out;
}

export function skinVertexNormalDQS(normal, skinIndex, skinWeight, offset, palette) {
  const { entries, total } = accumulateWeights(skinIndex, skinWeight, offset);
  if (total <= ZERO_WEIGHT_EPSILON) return [...normal];
  const real = [0, 0, 0, 0];
  for (const [bone, weight] of entries) {
    const normalizedWeight = weight / total;
    const base = bone * 4;
    for (let component = 0; component < 4; component += 1) {
      real[component] += normalizedWeight * palette.dualReal[base + component];
    }
  }
  return quatRotateVector(quatNormalize(real), normal);
}

export function skinAllVertices(model, palette, algorithm) {
  const positions = new Float32Array(model.vertexCount * 3);
  const skin = algorithm === "dqs" ? skinVertexDQS : skinVertexLBS;
  for (let vertex = 0; vertex < model.vertexCount; vertex += 1) {
    const offset = vertex * 4;
    const result = skin(
      [model.positions[vertex * 3], model.positions[vertex * 3 + 1], model.positions[vertex * 3 + 2]],
      model.skinIndex,
      model.skinWeight,
      offset,
      palette,
    );
    positions[vertex * 3] = result[0];
    positions[vertex * 3 + 1] = result[1];
    positions[vertex * 3 + 2] = result[2];
  }
  return positions;
}

export function transformedRing(model, positions, ring) {
  const points = [];
  const start = ring * model.radialSegments;
  for (let radial = 0; radial < model.radialSegments; radial += 1) {
    const index = start + radial;
    points.push([positions[index * 3], positions[index * 3 + 1], positions[index * 3 + 2]]);
  }
  return points;
}

export function polygonArea3D(points) {
  if (points.length < 3) return 0;
  const origin = points[0];
  let area = 0;
  for (let index = 1; index < points.length - 1; index += 1) {
    const a = [points[index][0] - origin[0], points[index][1] - origin[1], points[index][2] - origin[2]];
    const b = [points[index + 1][0] - origin[0], points[index + 1][1] - origin[1], points[index + 1][2] - origin[2]];
    area += 0.5 * Math.hypot(...cross(a, b));
  }
  return area;
}

export function maxVertexSeparation(a, b) {
  let maximum = 0;
  for (let index = 0; index < a.length; index += 3) {
    const dx = a[index] - b[index];
    const dy = a[index + 1] - b[index + 1];
    const dz = a[index + 2] - b[index + 2];
    maximum = Math.max(maximum, Math.hypot(dx, dy, dz));
  }
  return maximum;
}

export function bindPoseDeviation(model, palette, algorithm) {
  const bind = new Float32Array(model.vertexCount * 3);
  for (let vertex = 0; vertex < model.vertexCount; vertex += 1) {
    bind[vertex * 3] = model.positions[vertex * 3];
    bind[vertex * 3 + 1] = model.positions[vertex * 3 + 1];
    bind[vertex * 3 + 2] = model.positions[vertex * 3 + 2];
  }
  return maxVertexSeparation(bind, skinAllVertices(model, palette, algorithm));
}

export function weightedCentroid(points) {
  if (!points.length) return [0, 0, 0];
  const sum = points.reduce((acc, point) => add(acc, point), [0, 0, 0]);
  return [sum[0] / points.length, sum[1] / points.length, sum[2] / points.length];
}

export function meanRadius(points, center) {
  if (!points.length) return 0;
  return points.reduce((sum, point) => {
    const delta = [point[0] - center[0], point[1] - center[1], point[2] - center[2]];
    return sum + Math.hypot(delta[0], delta[1], delta[2]);
  }, 0) / points.length;
}

export function pointToAxisDistance(point, jointZ) {
  return Math.hypot(point[0], point[1], point[2] - jointZ);
}

export function vertexDifferenceAt(a, b, vertex) {
  const offset = vertex * 3;
  return Math.hypot(a[offset] - b[offset], a[offset + 1] - b[offset + 1], a[offset + 2] - b[offset + 2]);
}

export function maxSignJump(model, rig, angle) {
  const positive = buildSkinningPalette(rig, angle, { sign: 1, tracker: new HemisphereTracker() });
  const negative = buildSkinningPalette(rig, angle, { sign: -1, tracker: new HemisphereTracker() });
  const a = skinAllVertices(model, positive, "dqs");
  const b = skinAllVertices(model, negative, "dqs");
  return maxVertexSeparation(a, b);
}

export function boneAxis(rig, jointZ) {
  return {
    root: [0, 0, 0],
    joint: [0, 0, jointZ],
    tip: [0, 0, 4],
  };
}

export { MAX_BONES, ZERO_WEIGHT_EPSILON };
