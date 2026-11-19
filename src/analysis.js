import { HemisphereTracker, distance } from "./math.js";
import {
  bindPoseDeviation,
  buildSkinningPalette,
  polygonArea3D,
  skinAllVertices,
  skinVertexDQS,
  skinVertexLBS,
  transformedRing,
  vertexDifferenceAt,
} from "./skinning.js";

const AREA_EPSILON = 1e-5;
const MOTION_EPSILON = 1e-5;

export function analyzePose(model, lbsPalette, dqsPalette) {
  const lbsPositions = skinAllVertices(model, lbsPalette, "lbs");
  const dqsPositions = skinAllVertices(model, dqsPalette, "dqs");
  const ringZ = [];
  const lbsAreaRatio = [];
  const dqsAreaRatio = [];
  const lbsMotion = [];
  const dqsMotion = [];
  let maxError = 0;
  let errorSum = 0;
  let blendErrorMax = 0;
  let pureErrorMax = 0;
  let blendCount = 0;

  for (let vertex = 0; vertex < model.vertexCount; vertex += 1) {
    const error = vertexDifferenceAt(lbsPositions, dqsPositions, vertex);
    maxError = Math.max(maxError, error);
    errorSum += error;
    const sourceOffset = vertex * 4;
    const weightTotal = model.skinWeight[sourceOffset] + model.skinWeight[sourceOffset + 1];
    const isMixed = weightTotal > 1e-8 && model.skinWeight[sourceOffset + 1] > 1e-6 && model.skinWeight[sourceOffset + 1] < 1 - 1e-6;
    if (isMixed) {
      blendErrorMax = Math.max(blendErrorMax, error);
      blendCount += 1;
    } else {
      pureErrorMax = Math.max(pureErrorMax, error);
    }
  }

  for (let ring = 0; ring < model.ringCount; ring += 1) {
    const z = (ring / (model.ringCount - 1)) * model.height;
    const ringLbs = transformedRing(model, lbsPositions, ring);
    const ringDqs = transformedRing(model, dqsPositions, ring);
    ringZ.push(z);
    lbsAreaRatio.push(polygonArea3D(ringLbs) / model.bindArea);
    dqsAreaRatio.push(polygonArea3D(ringDqs) / model.bindArea);
    lbsMotion.push(maxRingMotion(model, lbsPositions, ring));
    dqsMotion.push(maxRingMotion(model, dqsPositions, ring));
  }

  const midRing = model.midRing;
  return {
    positions: { lbs: lbsPositions, dqs: dqsPositions },
    ringZ,
    lbsAreaRatio,
    dqsAreaRatio,
    lbsMotion,
    dqsMotion,
    mid: {
      lbsArea: model.bindArea * lbsAreaRatio[midRing],
      dqsArea: model.bindArea * dqsAreaRatio[midRing],
      lbsAreaRatio: lbsAreaRatio[midRing],
      dqsAreaRatio: dqsAreaRatio[midRing],
    },
    maxError,
    meanError: errorSum / model.vertexCount,
    blendErrorMax,
    pureErrorMax,
    blendCount,
    intervals: {
      lbsArea: findInterval(ringZ, lbsAreaRatio, (value) => Math.abs(value - 1) > AREA_EPSILON),
      dqsArea: findInterval(ringZ, dqsAreaRatio, (value) => Math.abs(value - 1) > AREA_EPSILON),
      lbsMotion: findInterval(ringZ, lbsMotion, (value) => value > MOTION_EPSILON),
      dqsMotion: findInterval(ringZ, dqsMotion, (value) => value > MOTION_EPSILON),
      lbsSevere: findInterval(ringZ, lbsAreaRatio, (value) => value < 0.9),
    },
  };
}

function maxRingMotion(model, positions, ring) {
  let maximum = 0;
  const start = ring * model.radialSegments;
  for (let radial = 0; radial < model.radialSegments; radial += 1) {
    const vertex = start + radial;
    const offset = vertex * 3;
    const bindOffset = vertex * 3;
    maximum = Math.max(
      maximum,
      Math.hypot(
        positions[offset] - model.positions[bindOffset],
        positions[offset + 1] - model.positions[bindOffset + 1],
        positions[offset + 2] - model.positions[bindOffset + 2],
      ),
    );
  }
  return maximum;
}

function findInterval(zValues, values, predicate) {
  let start = null;
  let end = null;
  for (let index = 0; index < values.length; index += 1) {
    if (predicate(values[index])) {
      if (start === null) start = zValues[index];
      end = zValues[index];
    }
  }
  return start === null ? null : { start, end };
}

export function precomputeProofs(model, sampleCount = 37) {
  const bindLbs = buildSkinningPalette(model.rig, 0, { sign: 1, tracker: new HemisphereTracker() });
  const bindDqs = buildSkinningPalette(model.rig, 0, { sign: -1, tracker: new HemisphereTracker() });
  const angles = Array.from({ length: sampleCount }, (_, index) => (index / (sampleCount - 1)) * Math.PI);
  const signJumps = [];
  let signJumpMax = 0;

  for (const angle of angles) {
    const plus = buildSkinningPalette(model.rig, angle, { sign: 1, tracker: new HemisphereTracker() });
    const minus = buildSkinningPalette(model.rig, angle, { sign: -1, tracker: new HemisphereTracker() });
    const a = skinAllVertices(model, plus, "dqs");
    const b = skinAllVertices(model, minus, "dqs");
    let jump = 0;
    for (let vertex = 0; vertex < model.vertexCount; vertex += 1) {
      jump = Math.max(jump, vertexDifferenceAt(a, b, vertex));
    }
    signJumps.push(jump);
    signJumpMax = Math.max(signJumpMax, jump);
  }

  const orphan = orphanConsistency(model);
  return {
    angles,
    signJumps,
    signJumpMax,
    bindLbs: bindPoseDeviation(model, bindLbs, "lbs"),
    bindDqs: bindPoseDeviation(model, bindDqs, "dqs"),
    bindSeparation: maxSeparation(
      skinAllVertices(model, bindLbs, "lbs"),
      skinAllVertices(model, bindDqs, "dqs"),
    ),
    orphan,
  };
}

export function maxSeparation(a, b) {
  let maximum = 0;
  for (let index = 0; index < a.length; index += 1) {
    maximum = Math.max(maximum, Math.abs(a[index] - b[index]));
  }
  return maximum;
}

function orphanConsistency(model) {
  let maximum = 0;
  const angles = [0, Math.PI * 0.5, Math.PI];
  for (const angle of angles) {
    for (const sign of [-1, 1]) {
      const palette = buildSkinningPalette(model.rig, angle, { sign, tracker: new HemisphereTracker() });
      for (let vertex = model.orphanStart; vertex < model.vertexCount; vertex += 1) {
        const offset = vertex * 4;
        const point = [model.positions[vertex * 3], model.positions[vertex * 3 + 1], model.positions[vertex * 3 + 2]];
        const lbs = skinVertexLBS(point, model.skinIndex, model.skinWeight, offset, palette);
        const dqs = skinVertexDQS(point, model.skinIndex, model.skinWeight, offset, palette);
        maximum = Math.max(maximum, distance(point, lbs), distance(point, dqs));
      }
    }
  }
  return {
    count: model.vertexCount - model.orphanStart,
    maxDeviation: maximum,
  };
}

export function precomputeTrajectories(model, sampleCount = 37) {
  const angles = [];
  const lbs = [];
  const dqs = [];
  const lbsRadial = [];
  const dqsRadial = [];
  const vertex = model.probeVertex;
  const point = [model.positions[vertex * 3], model.positions[vertex * 3 + 1], model.positions[vertex * 3 + 2]];
  for (let index = 0; index < sampleCount; index += 1) {
    const angle = (index / (sampleCount - 1)) * Math.PI;
    const paletteLbs = buildSkinningPalette(model.rig, angle, { sign: 1, tracker: new HemisphereTracker() });
    const paletteDqs = buildSkinningPalette(model.rig, angle, { sign: 1, tracker: new HemisphereTracker() });
    const pointLbs = skinVertexLBS(point, model.skinIndex, model.skinWeight, vertex * 4, paletteLbs);
    const pointDqs = skinVertexDQS(point, model.skinIndex, model.skinWeight, vertex * 4, paletteDqs);
    angles.push(angle);
    lbs.push(pointLbs);
    dqs.push(pointDqs);
    lbsRadial.push(Math.hypot(pointLbs[0], pointLbs[1]));
    dqsRadial.push(Math.hypot(pointDqs[0], pointDqs[1]));
  }
  return { angles, lbs, dqs, lbsRadial, dqsRadial, vertex };
}

export function currentProbePosition(model, positions) {
  const index = model.probeVertex;
  return [positions[index * 3], positions[index * 3 + 1], positions[index * 3 + 2]];
}

export function crossSectionRadius(points, center) {
  const distances = points.map((point) => Math.hypot(point[0] - center[0], point[1] - center[1], point[2] - center[2]));
  return distances.reduce((sum, value) => sum + value, 0) / distances.length;
}

export function formatInterval(interval) {
  if (!interval) return "无";
  return `z ${interval.start.toFixed(2)}–${interval.end.toFixed(2)}`;
}
