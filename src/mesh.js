import { length } from "./math.js";

function vertexKey(vertex, tolerance = 1e-6) {
  const scale = 1 / tolerance;
  return vertex.map((value) => Math.round(value * scale)).join(",");
}

function edgeKey(a, b) {
  return a < b ? `${a}:${b}` : `${b}:${a}`;
}

function triangleArea(vertices, triangle) {
  const [a, b, c] = triangle.map((index) => vertices[index]);
  const ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const ac = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
  return 0.5 * length([
    ab[1] * ac[2] - ab[2] * ac[1],
    ab[2] * ac[0] - ab[0] * ac[2],
    ab[0] * ac[1] - ab[1] * ac[0],
  ]);
}

export function validateMesh(mesh, tolerance = 1e-6) {
  if (!mesh || !Array.isArray(mesh.vertices) || !Array.isArray(mesh.triangles)) {
    return {
      valid: false,
      watertight: false,
      findings: ["mesh 必须同时包含 vertices 与 triangles 数组。"],
      stats: null,
    };
  }
  const findings = [];
  const welded = [];
  const weldMap = new Map();
  const remap = [];
  for (const vertex of mesh.vertices) {
    if (!Array.isArray(vertex) || vertex.length !== 3 || vertex.some((v) => !Number.isFinite(v))) {
      findings.push("存在非有限三维顶点。");
      continue;
    }
    const key = vertexKey(vertex, tolerance);
    if (!weldMap.has(key)) {
      weldMap.set(key, welded.length);
      welded.push(vertex);
    }
    remap.push(weldMap.get(key));
  }

  const triangles = [];
  let degenerateTriangles = 0;
  for (const triangle of mesh.triangles) {
    if (!Array.isArray(triangle) || triangle.length !== 3) {
      findings.push("存在非三角面片。");
      continue;
    }
    const mapped = triangle.map((index) => remap[index]);
    if (mapped.some((index) => !Number.isInteger(index))) {
      findings.push("面片引用了不存在的顶点索引。");
      continue;
    }
    if (new Set(mapped).size !== 3 || triangleArea(welded, mapped) < 1e-12) {
      degenerateTriangles += 1;
      continue;
    }
    triangles.push(mapped);
  }

  const edgeMap = new Map();
  for (const triangle of triangles) {
    for (let i = 0; i < 3; i += 1) {
      const a = triangle[i];
      const b = triangle[(i + 1) % 3];
      const key = edgeKey(a, b);
      const record = edgeMap.get(key) ?? { count: 0, directions: [] };
      record.count += 1;
      record.directions.push(a < b ? 1 : -1);
      edgeMap.set(key, record);
    }
  }

  let boundaryEdges = 0;
  let nonManifoldEdges = 0;
  let inconsistentEdges = 0;
  for (const record of edgeMap.values()) {
    if (record.count === 1) boundaryEdges += 1;
    if (record.count > 2) nonManifoldEdges += 1;
    if (record.count === 2 && record.directions[0] === record.directions[1]) {
      inconsistentEdges += 1;
    }
  }

  const euler = welded.length - edgeMap.size + triangles.length;
  const watertight = boundaryEdges === 0 && nonManifoldEdges === 0 && inconsistentEdges === 0;
  const valid = watertight && degenerateTriangles === 0 && findings.length === 0;
  if (boundaryEdges > 0) findings.push(`发现 ${boundaryEdges} 条边界边（缺失面片）。`);
  if (nonManifoldEdges > 0) findings.push(`发现 ${nonManifoldEdges} 条非流形边。`);
  if (inconsistentEdges > 0) findings.push(`发现 ${inconsistentEdges} 条绕序不一致的边。`);
  if (degenerateTriangles > 0) findings.push(`发现 ${degenerateTriangles} 个退化三角形。`);
  if (euler !== 2) findings.push(`Euler 特征数为 ${euler}，不是闭合 genus-0 实体。`);

  return {
    valid,
    watertight,
    findings,
    stats: {
      inputVertices: mesh.vertices.length,
      weldedVertices: welded.length,
      triangles: triangles.length,
      edges: edgeMap.size,
      boundaryEdges,
      nonManifoldEdges,
      inconsistentEdges,
      degenerateTriangles,
      euler,
    },
  };
}

function validateFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

export function validateScene(scene) {
  const findings = [];
  if (!scene || scene.schema !== "ltc-area-light-scene/1") {
    findings.push("schema 必须为 ltc-area-light-scene/1。");
  }
  const emitter = scene?.emitter;
  if (!emitter || !["rect", "disk"].includes(emitter.type)) {
    findings.push("emitter.type 必须为 rect 或 disk。");
  } else if (emitter.type === "rect") {
    if (!validateFiniteNumber(emitter.halfWidth) || emitter.halfWidth <= 0) {
      findings.push("矩形半宽必须为正有限数。");
    }
    if (!validateFiniteNumber(emitter.halfHeight) || emitter.halfHeight <= 0) {
      findings.push("矩形半高必须为正有限数。");
    }
  } else if (!validateFiniteNumber(emitter.radius) || emitter.radius <= 0) {
    findings.push("圆盘半径必须为正有限数。");
  }
  const roughMin = scene?.surface?.roughnessMin;
  const roughMax = scene?.surface?.roughnessMax;
  if (!validateFiniteNumber(roughMin) || roughMin <= 0 || roughMin > 1) {
    findings.push("surface.roughnessMin 必须位于 (0, 1]。");
  }
  if (!validateFiniteNumber(roughMax) || roughMax <= 0 || roughMax > 1) {
    findings.push("surface.roughnessMax 必须位于 (0, 1]。");
  }
  if (validateFiniteNumber(roughMin) && validateFiniteNumber(roughMax) && roughMin > roughMax) {
    findings.push("surface.roughnessMin 不能大于 roughnessMax。");
  }
  if (!Number.isInteger(scene?.sampling?.spp) || scene.sampling.spp <= 0) {
    findings.push("sampling.spp 必须为正整数。");
  }
  const meshReport = scene?.mesh ? validateMesh(scene.mesh) : null;
  if (meshReport && !meshReport.valid) {
    findings.push(...meshReport.findings.map((finding) => `mesh：${finding}`));
  }
  return {
    valid: findings.length === 0,
    findings,
    mesh: meshReport,
  };
}

export function meshWireframe(mesh, width = 220, height = 150) {
  if (!mesh?.vertices?.length) return [];
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const vertex of mesh.vertices) {
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], vertex[axis]);
      max[axis] = Math.max(max[axis], vertex[axis]);
    }
  }
  const cx = (min[0] + max[0]) / 2;
  const cy = (min[1] + max[1]) / 2;
  const cz = (min[2] + max[2]) / 2;
  const scale = Math.min(width, height) * 0.32 / Math.max(
    max[0] - min[0],
    max[1] - min[1],
    max[2] - min[2],
    1e-6,
  );
  const yaw = -0.62;
  const pitch = 0.46;
  const project = (vertex) => {
    const x = vertex[0] - cx;
    const y = vertex[1] - cy;
    const z = vertex[2] - cz;
    const x1 = yaw ? x * Math.cos(yaw) - y * Math.sin(yaw) : x;
    const y1 = yaw ? x * Math.sin(yaw) + y * Math.cos(yaw) : y;
    const y2 = y1 * Math.cos(pitch) - z * Math.sin(pitch);
    const depth = y1 * Math.sin(pitch) + z * Math.cos(pitch);
    return [width / 2 + x1 * scale, height / 2 - y2 * scale, depth];
  };
  const edges = new Set();
  for (const triangle of mesh.triangles) {
    for (let i = 0; i < 3; i += 1) {
      const a = triangle[i];
      const b = triangle[(i + 1) % 3];
      edges.add(a < b ? `${a}:${b}` : `${b}:${a}`);
    }
  }
  return [...edges].map((key) => {
    const [a, b] = key.split(":").map(Number);
    return [project(mesh.vertices[a]), project(mesh.vertices[b])];
  });
}
