import { triangleNormal, vec3 } from "./math.js";

function pushTriangle(indices, a, b, c) {
  indices.push(a, b, c);
}

export function createSphere(radius = 1.7, slices = 64, stacks = 49, center = [0, 3.05, 0]) {
  const positions = [];
  const indices = [];
  positions.push(center[0], center[1] + radius, center[2]);

  for (let stack = 1; stack < stacks; stack += 1) {
    const phi = Math.PI * stack / stacks;
    const y = Math.cos(phi) * radius;
    const ringRadius = Math.sin(phi) * radius;
    for (let slice = 0; slice < slices; slice += 1) {
      const theta = Math.PI * 2 * slice / slices;
      positions.push(
        center[0] + Math.cos(theta) * ringRadius,
        center[1] + y,
        center[2] + Math.sin(theta) * ringRadius,
      );
    }
  }

  const south = 1 + (stacks - 1) * slices;
  positions.push(center[0], center[1] - radius, center[2]);

  for (let slice = 0; slice < slices; slice += 1) {
    const next = (slice + 1) % slices;
    pushTriangle(indices, 0, 1 + next, 1 + slice);
  }

  for (let stack = 0; stack < stacks - 2; stack += 1) {
    const ring = 1 + stack * slices;
    const nextRing = ring + slices;
    for (let slice = 0; slice < slices; slice += 1) {
      const next = (slice + 1) % slices;
      const a = ring + slice;
      const b = ring + next;
      const c = nextRing + next;
      const d = nextRing + slice;
      pushTriangle(indices, a, b, c);
      pushTriangle(indices, a, c, d);
    }
  }

  const lastRing = 1 + (stacks - 2) * slices;
  for (let slice = 0; slice < slices; slice += 1) {
    const next = (slice + 1) % slices;
    pushTriangle(indices, lastRing + slice, lastRing + next, south);
  }

  return finalizeMesh(new Float32Array(positions), new Uint32Array(indices), true);
}

export function createBox(size, center = [0, 0, 0], rotation = [0, 0, 0]) {
  const [width, height, depth] = size;
  const [cx, cy, cz] = center;
  const x = width / 2;
  const y = height / 2;
  const z = depth / 2;
  const base = [
    [-x, -y, -z], [x, -y, -z], [x, y, -z], [-x, y, -z],
    [-x, -y, z], [x, -y, z], [x, y, z], [-x, y, z],
  ];
  const positions = [];
  for (const point of base) {
    const [rx, ry, rz] = rotatePoint(point, rotation);
    positions.push(rx + cx, ry + cy, rz + cz);
  }
  const indices = new Uint32Array([
    0, 2, 1, 0, 3, 2,
    4, 5, 6, 4, 6, 7,
    0, 1, 5, 0, 5, 4,
    3, 7, 6, 3, 6, 2,
    0, 4, 7, 0, 7, 3,
    1, 2, 6, 1, 6, 5,
  ]);
  return finalizeMesh(new Float32Array(positions), indices, true);
}

function rotatePoint(point, rotation) {
  const [x, y, z] = point;
  const [rx, ry, rz] = rotation;
  const cx = Math.cos(rx);
  const sx = Math.sin(rx);
  const cy = Math.cos(ry);
  const sy = Math.sin(ry);
  const cz = Math.cos(rz);
  const sz = Math.sin(rz);
  const y1 = y * cx - z * sx;
  const z1 = y * sx + z * cx;
  const x2 = x * cy + z1 * sy;
  const z2 = -x * sy + z1 * cy;
  return [x2 * cz - y1 * sz, x2 * sz + y1 * cz, z2];
}

export function createOpenPanel(center = [0, 3.05, 0], segmentsX = 10, segmentsZ = 6) {
  const positions = [];
  const indices = [];
  for (let iz = 0; iz <= segmentsZ; iz += 1) {
    const v = iz / segmentsZ;
    for (let ix = 0; ix <= segmentsX; ix += 1) {
      const u = ix / segmentsX;
      const x = (u - 0.5) * 5.4;
      const z = (v - 0.5) * 3.8;
      const y = Math.sin(u * Math.PI) * 0.7 + Math.sin(v * Math.PI * 2) * 0.22;
      positions.push(center[0] + x, center[1] + y, center[2] + z);
    }
  }
  for (let iz = 0; iz < segmentsZ; iz += 1) {
    for (let ix = 0; ix < segmentsX; ix += 1) {
      const a = iz * (segmentsX + 1) + ix;
      const b = a + 1;
      const d = a + segmentsX + 1;
      const c = d + 1;
      pushTriangle(indices, a, d, b);
      pushTriangle(indices, b, d, c);
    }
  }
  return finalizeMesh(new Float32Array(positions), new Uint32Array(indices), false);
}

export function createPlank() {
  return createBox(
    [12.8, 0.18, 0.5],
    [0.4, 3.75, 0.1],
    [0.03, 0.24, -0.055],
  );
}

export function createSceneMeshes() {
  return {
    closed: createSphere(),
    open: createOpenPanel(),
    plank: createPlank(),
  };
}

export function finalizeMesh(positions, indices, closed) {
  const triangles = [];
  for (let index = 0; index < indices.length; index += 3) {
    triangles.push([indices[index], indices[index + 1], indices[index + 2]]);
  }
  const topology = buildTopology(positions, triangles);
  return {
    positions,
    indices,
    triangles,
    closed: closed && topology.boundaryEdges === 0,
    margin: 1.2,
    ...topology,
  };
}

export function buildTopology(positions, triangles) {
  const edgeMap = new Map();
  triangles.forEach((triangle, triangleIndex) => {
    for (let edgeIndex = 0; edgeIndex < 3; edgeIndex += 1) {
      const a = triangle[edgeIndex];
      const b = triangle[(edgeIndex + 1) % 3];
      const key = a < b ? `${a}:${b}` : `${b}:${a}`;
      if (!edgeMap.has(key)) edgeMap.set(key, []);
      edgeMap.get(key).push({ a, b, triangleIndex });
    }
  });

  let boundaryEdges = 0;
  let nonManifoldEdges = 0;
  for (const records of edgeMap.values()) {
    if (records.length === 1) boundaryEdges += 1;
    if (records.length > 2) nonManifoldEdges += 1;
  }

  return { edgeMap, boundaryEdges, nonManifoldEdges };
}

export function getTriangle(mesh, triangleIndex) {
  const [ia, ib, ic] = mesh.triangles[triangleIndex];
  const p = mesh.positions;
  return {
    a: [p[ia * 3], p[ia * 3 + 1], p[ia * 3 + 2]],
    b: [p[ib * 3], p[ib * 3 + 1], p[ib * 3 + 2]],
    c: [p[ic * 3], p[ic * 3 + 1], p[ic * 3 + 2]],
  };
}

export function triangleFacesLight(mesh, triangleIndex, lightDirection) {
  const triangle = getTriangle(mesh, triangleIndex);
  const normal = triangleNormal(triangle.a, triangle.b, triangle.c);
  return vec3.dot(normal, lightDirection) > 0;
}

export function rayHitsMesh(mesh, origin, direction, maxDistance = 100) {
  for (const triangle of mesh.triangles) {
    const [ia, ib, ic] = triangle;
    const p = mesh.positions;
    const a = [p[ia * 3], p[ia * 3 + 1], p[ia * 3 + 2]];
    const b = [p[ib * 3], p[ib * 3 + 1], p[ib * 3 + 2]];
    const c = [p[ic * 3], p[ic * 3 + 1], p[ic * 3 + 2]];
    const edge1 = vec3.sub(b, a);
    const edge2 = vec3.sub(c, a);
    const pvec = vec3.cross(direction, edge2);
    const determinant = vec3.dot(edge1, pvec);
    if (Math.abs(determinant) < 1e-8) continue;
    const inverse = 1 / determinant;
    const tvec = vec3.sub(origin, a);
    const u = vec3.dot(tvec, pvec) * inverse;
    if (u < 0 || u > 1) continue;
    const qvec = vec3.cross(tvec, edge1);
    const v = vec3.dot(direction, qvec) * inverse;
    if (v < 0 || u + v > 1) continue;
    const distance = vec3.dot(edge2, qvec) * inverse;
    if (distance > 1e-5 && distance < maxDistance) return true;
  }
  return false;
}
