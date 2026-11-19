import { mat4Identity, mat4Translation, smoothstep } from "./math.js";
import { createRig, polygonArea3D } from "./skinning.js";

export const SCENE_META = {
  twist: {
    kind: "twist",
    label: "分节圆柱",
    english: "SEGMENTED CYLINDER · AXIAL TWIST",
    subtitle: "沿同一骨骼轴扭转，观察中段混合权重区域。",
    axis: [0, 0, 1],
    axisLabel: "Z 轴扭转",
    projection: "XY",
  },
  elbow: {
    kind: "elbow",
    label: "肘关节",
    english: "ELBOW RIG · SINGLE-AXIS BEND",
    subtitle: "绕肘关节 X 轴弯曲，比较关节处的体积塌缩。",
    axis: [1, 0, 0],
    axisLabel: "X 轴弯曲",
    projection: "YZ",
  },
};

const GEOMETRY = {
  ringCount: 81,
  radialSegments: 40,
  height: 4,
  radius: 0.46,
  blendStart: 1,
  blendEnd: 3,
  jointZ: 2,
};

function ringTint(z, radial, radialSegments) {
  const band = Math.floor((z + 0.025) / 0.4) % 2;
  const segmentLine = radial % 5 === 0 ? 0.18 : 0;
  const bandBoost = band === 0 ? 0.08 : 0;
  return [0.68 + bandBoost + segmentLine, 0.72 + bandBoost + segmentLine, 0.74 + bandBoost + segmentLine];
}

function addSurface(arrays, ringCount, radialSegments) {
  const { positions, normals, tints, skinIndex, skinWeight } = arrays;
  const twoPi = Math.PI * 2;
  for (let ring = 0; ring < ringCount; ring += 1) {
    const z = (ring / (ringCount - 1)) * GEOMETRY.height;
    const weight = smoothstep(GEOMETRY.blendStart, GEOMETRY.blendEnd, z);
    for (let radial = 0; radial < radialSegments; radial += 1) {
      const theta = (radial / radialSegments) * twoPi;
      positions.push(Math.cos(theta) * GEOMETRY.radius, Math.sin(theta) * GEOMETRY.radius, z);
      normals.push(Math.cos(theta), Math.sin(theta), 0);
      tints.push(...ringTint(z, radial, radialSegments));
      skinIndex.push(0, 1, 0, 0);
      skinWeight.push(1 - weight, weight, 0, 0);
    }
  }
}

function addSurfaceIndices(arrays, ringCount, radialSegments) {
  const { indices } = arrays;
  for (let ring = 0; ring < ringCount - 1; ring += 1) {
    for (let radial = 0; radial < radialSegments; radial += 1) {
      const next = (radial + 1) % radialSegments;
      const a = ring * radialSegments + radial;
      const b = ring * radialSegments + next;
      const c = (ring + 1) * radialSegments + radial;
      const d = (ring + 1) * radialSegments + next;
      indices.push(a, b, c, b, d, c);
    }
  }
}

function addCap(arrays, z, normalZ, reverse, radialSegments) {
  const { positions, normals, tints, skinIndex, skinWeight, indices } = arrays;
  const weight = smoothstep(GEOMETRY.blendStart, GEOMETRY.blendEnd, z);
  const centerIndex = positions.length / 3;
  positions.push(0, 0, z);
  normals.push(0, 0, normalZ);
  tints.push(0.45, 0.5, 0.52);
  skinIndex.push(0, 1, 0, 0);
  skinWeight.push(1 - weight, weight, 0, 0);
  const first = positions.length / 3;
  const twoPi = Math.PI * 2;
  for (let radial = 0; radial < radialSegments; radial += 1) {
    const theta = (radial / radialSegments) * twoPi;
    positions.push(Math.cos(theta) * GEOMETRY.radius, Math.sin(theta) * GEOMETRY.radius, z);
    normals.push(0, 0, normalZ);
    tints.push(0.56, 0.61, 0.63);
    skinIndex.push(0, 1, 0, 0);
    skinWeight.push(1 - weight, weight, 0, 0);
  }
  for (let radial = 0; radial < radialSegments; radial += 1) {
    const next = (radial + 1) % radialSegments;
    if (reverse) {
      indices.push(centerIndex, first + next, first + radial);
    } else {
      indices.push(centerIndex, first + radial, first + next);
    }
  }
}

function addOrphans(arrays) {
  const orphanPositions = [
    [1.34, 0.55, 0.78],
    [-1.16, 0.95, 2.18],
    [0.82, -1.2, 3.35],
  ];
  const first = arrays.positions.length / 3;
  for (const position of orphanPositions) {
    arrays.positions.push(...position);
    arrays.normals.push(0, 0, 1);
    arrays.tints.push(1, 0.72, 0.36);
    arrays.skinIndex.push(0, 1, 0, 0);
    arrays.skinWeight.push(0, 0, 0, 0);
  }
  return { orphanStart: first, orphanPositions };
}

export function createModel(kind) {
  const meta = SCENE_META[kind];
  const { ringCount, radialSegments, jointZ } = GEOMETRY;
  const arrays = {
    positions: [],
    normals: [],
    tints: [],
    skinIndex: [],
    skinWeight: [],
    indices: [],
  };
  addSurface(arrays, ringCount, radialSegments);
  addSurfaceIndices(arrays, ringCount, radialSegments);
  const surfaceVertexCount = ringCount * radialSegments;
  addCap(arrays, 0, -1, true, radialSegments);
  addCap(arrays, GEOMETRY.height, 1, false, radialSegments);
  const orphanInfo = addOrphans(arrays);

  const positions = new Float32Array(arrays.positions);
  const vertexCount = positions.length / 3;
  const model = {
    ...meta,
    ringCount,
    radialSegments,
    height: GEOMETRY.height,
    radius: GEOMETRY.radius,
    jointZ,
    blendStart: GEOMETRY.blendStart,
    blendEnd: GEOMETRY.blendEnd,
    surfaceVertexCount,
    vertexCount,
    positions,
    normals: new Float32Array(arrays.normals),
    tints: new Float32Array(arrays.tints),
    skinIndex: new Uint16Array(arrays.skinIndex),
    skinWeight: new Float32Array(arrays.skinWeight),
    indices: new Uint32Array(arrays.indices),
    orphanStart: orphanInfo.orphanStart,
    orphanPositions: orphanInfo.orphanPositions,
    midRing: Math.round((ringCount - 1) * (jointZ / GEOMETRY.height)),
    probeVertex:
      Math.round((ringCount - 1) * (jointZ / GEOMETRY.height)) * radialSegments +
      (kind === "elbow" ? Math.floor(radialSegments / 4) : 0),
    bindMatrices: [mat4Identity(), mat4Translation([0, 0, jointZ])],
  };
  model.rig = createRig(model.bindMatrices, meta.axis, jointZ);
  model.bindArea = polygonArea3D(
    Array.from({ length: radialSegments }, (_, radial) => {
      const theta = (radial / radialSegments) * Math.PI * 2;
      return [Math.cos(theta) * model.radius, Math.sin(theta) * model.radius, jointZ];
    }),
  );
  model.blendVertexCount = countBlendVertices(model);
  return model;
}

function countBlendVertices(model) {
  let count = 0;
  for (let vertex = 0; vertex < model.vertexCount; vertex += 1) {
    const weight = model.skinWeight[vertex * 4 + 1];
    if (weight > 1e-6 && weight < 1 - 1e-6) count += 1;
  }
  return count;
}

export const MODELS = {
  twist: createModel("twist"),
  elbow: createModel("elbow"),
};
