import {
  PI,
  TAU,
  basisFromNormal,
  clamp,
  cross,
  dot,
  fromLocal,
  length,
  normalize,
  radicalInverse,
  toLocal,
} from "./math.js";

const TABLE_SIZE = 64;
const TABLE_STRIDE = TABLE_SIZE * TABLE_SIZE * 4;
let table1 = null;
let table2 = null;
let tableReady = false;

export function initLTCData(arrayBuffer) {
  const data = new Float32Array(arrayBuffer);
  if (data.length !== TABLE_STRIDE * 2) {
    throw new Error(`LTC table must contain ${TABLE_STRIDE * 2} floats`);
  }
  table1 = data.subarray(0, TABLE_STRIDE);
  table2 = data.subarray(TABLE_STRIDE);
  tableReady = true;
}

export const isLTCDataReady = () => tableReady;

function tableCoords(roughness, ndotv) {
  return [
    clamp(roughness, 0, 1) * (TABLE_SIZE - 1),
    Math.sqrt(clamp(1 - ndotv, 0, 1)) * (TABLE_SIZE - 1),
  ];
}

function bilinearTable(table, x, y, channel) {
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const x1 = Math.min(TABLE_SIZE - 1, x0 + 1);
  const y1 = Math.min(TABLE_SIZE - 1, y0 + 1);
  const tx = x - x0;
  const ty = y - y0;
  const index = (row, col) => (row * TABLE_SIZE + col) * 4 + channel;
  const a = table[index(y0, x0)] * (1 - tx) + table[index(y0, x1)] * tx;
  const b = table[index(y1, x0)] * (1 - tx) + table[index(y1, x1)] * tx;
  return a * (1 - ty) + b * ty;
}

export function sampleLTCMatrix(roughness, ndotv, second = false) {
  if (!tableReady) throw new Error("LTC data has not been initialized");
  const [x, y] = tableCoords(roughness, ndotv);
  const table = second ? table2 : table1;
  return [0, 1, 2, 3].map((channel) => bilinearTable(table, x, y, channel));
}

export function sampleLTCMatrixQuantized(roughness, ndotv, levels = 8) {
  if (!tableReady) throw new Error("LTC data has not been initialized");
  const quantized = Math.round(clamp(roughness, 0, 1) * (levels - 1)) / (levels - 1);
  return sampleLTCMatrix(quantized, ndotv);
}

export function invertLTCBlock(values) {
  const [a, b, c, d] = values;
  const det = a * d - b * c;
  if (Math.abs(det) < 1e-9) throw new Error("singular LTC matrix");
  return [d / det, -b / det, -c / det, a / det, det];
}

export function ltcMatrix3(values) {
  const [a, b, c, d] = values;
  return [
    [a, 0, c],
    [0, 1, 0],
    [b, 0, d],
  ];
}

export function inverseLTCBlock(values) {
  const inverse = invertLTCBlock(values);
  return inverse.slice(0, 4);
}

function transformInverseBlock(block, local) {
  const [a, b, c, d] = block;
  return [
    a * local[0] + c * local[2],
    local[1],
    b * local[0] + d * local[2],
  ];
}

function transformForwardBlock(block, local) {
  const [a, b, c, d] = block;
  return [
    a * local[0] + c * local[2],
    local[1],
    b * local[0] + d * local[2],
  ];
}

function edgeVectorFormFactor(v1, v2) {
  const x = dot(v1, v2);
  const y = Math.abs(x);
  const a = 0.8543985 + (0.4965155 + 0.0145206 * y) * y;
  const b = 3.417594 + (4.1616724 + y) * y;
  const v = a / b;
  const invSin = 0.5 / Math.sqrt(Math.max(1 - x * x, 1e-7));
  const thetaSinTheta = x > 0 ? v : invSin - v;
  return [
    (v1[1] * v2[2] - v1[2] * v2[1]) * thetaSinTheta,
    (v1[2] * v2[0] - v1[0] * v2[2]) * thetaSinTheta,
    (v1[0] * v2[1] - v1[1] * v2[0]) * thetaSinTheta,
  ];
}

function clippedSphereFormFactor(vectorFormFactor) {
  const len = length(vectorFormFactor);
  return Math.max((len * len + vectorFormFactor[2]) / (len + 1), 0);
}

export function ltcEvaluatePolygon(normal, view, point, polygon, matrixInverse) {
  if (polygon.length < 3) return 0;
  const edge1 = [
    polygon[1][0] - polygon[0][0],
    polygon[1][1] - polygon[0][1],
    polygon[1][2] - polygon[0][2],
  ];
  const edge2 = [
    polygon[3][0] - polygon[0][0],
    polygon[3][1] - polygon[0][1],
    polygon[3][2] - polygon[0][2],
  ];
  const lightNormal = cross(edge1, edge2);
  const toPoint = [
    point[0] - polygon[0][0],
    point[1] - polygon[0][1],
    point[2] - polygon[0][2],
  ];
  if (dot(lightNormal, toPoint) < 0) return 0;

  const basis = basisFromNormal(normal, view);
  const transformed = polygon.map((vertex) => {
    const local = toLocal(
      [vertex[0] - point[0], vertex[1] - point[1], vertex[2] - point[2]],
      basis,
    );
    return normalize(transformInverseBlock(matrixInverse, local));
  });

  const formFactor = [0, 0, 0];
  for (let i = 0; i < transformed.length; i += 1) {
    const current = transformed[i];
    const next = transformed[(i + 1) % transformed.length];
    const contribution = edgeVectorFormFactor(current, next);
    formFactor[0] += contribution[0];
    formFactor[1] += contribution[1];
    formFactor[2] += contribution[2];
  }
  return clippedSphereFormFactor(formFactor);
}

export function ltcDensity(direction, normal, view, matrixInverse) {
  const basis = basisFromNormal(normal, view);
  const local = toLocal(normalize(direction), basis);
  const transformed = transformInverseBlock(matrixInverse, local);
  if (transformed[2] <= 0) return 0;
  const len = length(transformed);
  const cosine = transformed[2] / len;
  const detM = 1 / (matrixInverse[0] * matrixInverse[3] - matrixInverse[1] * matrixInverse[2]);
  return cosine / (PI * detM * len * len * len);
}

export function sampleLTCDirections(count, roughness, ndotv, seed = 1, normal = [0, 0, 1], view) {
  const matrix = sampleLTCMatrix(roughness, ndotv);
  const forward = inverseLTCBlock(matrix);
  const safeView = view ?? normalize([0, 0.35, 1]);
  const basis = basisFromNormal(normal, safeView);
  const directions = [];
  let state = seed >>> 0;
  const random = () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  for (let i = 0; i < count; i += 1) {
    let direction = null;
    for (let attempt = 0; attempt < 128; attempt += 1) {
      const u1 = random();
      const u2 = random();
      const radius = Math.sqrt(u1);
      const phi = TAU * u2;
      const cosineSample = [
        radius * Math.cos(phi),
        radius * Math.sin(phi),
        Math.sqrt(Math.max(0, 1 - u1)),
      ];
      const transformed = normalize(transformForwardBlock(forward, cosineSample));
      const candidate = fromLocal(transformed, basis);
      if (candidate[2] >= 0) {
        direction = candidate;
        break;
      }
    }
    if (direction) directions.push(direction);
  }
  return directions;
}

export function makeRectLight({ center = [0, 0, 1.6], halfWidth = 0.8, halfHeight = 0.5 } = {}) {
  const [cx, cy, cz] = center;
  const polygon = [
    [cx - halfWidth, cy - halfHeight, cz],
    [cx - halfWidth, cy + halfHeight, cz],
    [cx + halfWidth, cy + halfHeight, cz],
    [cx + halfWidth, cy - halfHeight, cz],
  ];
  return {
    type: "rect",
    center,
    normal: [0, 0, -1],
    halfWidth,
    halfHeight,
    area: 4 * halfWidth * halfHeight,
    polygon,
    segments: 4,
  };
}

export function makeDiskLight({ center = [0, 0, 1.6], radius = 0.7, segments = 128 } = {}) {
  const [cx, cy, cz] = center;
  const polygon = [];
  for (let i = 0; i < segments; i += 1) {
    const angle = -TAU * (i / segments);
    polygon.push([cx + radius * Math.cos(angle), cy + radius * Math.sin(angle), cz]);
  }
  return {
    type: "disk",
    center,
    normal: [0, 0, -1],
    radius,
    area: PI * radius * radius,
    polygon,
    segments,
  };
}

export function sampleLightPoint(light, u1, u2) {
  const [cx, cy, cz] = light.center;
  if (light.type === "rect") {
    return [
      cx + (u1 * 2 - 1) * light.halfWidth,
      cy + (u2 * 2 - 1) * light.halfHeight,
      cz,
    ];
  }
  const radius = light.radius * Math.sqrt(u1);
  const angle = TAU * u2;
  return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle), cz];
}

export function integrateLTCAnalytic(point, normal, view, light, ltcValues) {
  return ltcEvaluatePolygon(normal, view, point, light.polygon, ltcValues);
}

export function integrateLTCMC(point, normal, view, light, ltcValues, sampleCount, random) {
  if (sampleCount <= 0) return 0;
  const rotation = random();
  let sum = 0;
  for (let i = 0; i < sampleCount; i += 1) {
    const u1 = sampleCount === 1
      ? random()
      : (i + random()) / sampleCount;
    const u2 = sampleCount === 1
      ? random()
      : (radicalInverse(i + 1, 2) + rotation) % 1;
    const q = sampleLightPoint(light, u1, u2);
    const delta = [q[0] - point[0], q[1] - point[1], q[2] - point[2]];
    const distanceSquared = dot(delta, delta);
    const distance = Math.sqrt(distanceSquared);
    const cosineLight = dot(
      light.normal,
      [-delta[0] / distance, -delta[1] / distance, -delta[2] / distance],
    );
    if (cosineLight <= 0 || distanceSquared < 1e-10) continue;
    const direction = [delta[0] / distance, delta[1] / distance, delta[2] / distance];
    const density = ltcDensity(direction, normal, view, ltcValues);
    sum += density * light.area * cosineLight / distanceSquared;
  }
  return sum / sampleCount;
}

export function diskPolygonAreaError(segments) {
  return 1 - (segments / (2 * PI)) * Math.sin(TAU / segments);
}
