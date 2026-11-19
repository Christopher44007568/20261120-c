import {
  average,
  cross,
  length,
  normalize,
  sub,
  triangleArea,
} from "./math.js";
import { intrinsicDimension, orient3d, predicateScales } from "./predicates.js";

function farthestFromLine(points, a, b) {
  const axis = sub(b, a);
  const denominator = Math.max(length(axis) ** 2, 1e-30);
  let best = -1;
  let bestDistance = -1;
  for (let index = 0; index < points.length; index += 1) {
    const relative = sub(points[index], a);
    const projection = (relative[0] * axis[0] + relative[1] * axis[1] + relative[2] * axis[2]) / denominator;
    const dx = relative[0] - axis[0] * projection;
    const dy = relative[1] - axis[1] * projection;
    const dz = relative[2] - axis[2] * projection;
    const distance = dx * dx + dy * dy + dz * dz;
    if (distance > bestDistance) {
      bestDistance = distance;
      best = index;
    }
  }
  return { index: best, distance: Math.sqrt(Math.max(bestDistance, 0)) };
}

function seedTetrahedron(points, epsilon) {
  let i0 = 0;
  for (let index = 1; index < points.length; index += 1) {
    if (points[index][0] < points[i0][0]) i0 = index;
  }
  let i1 = 0;
  let far = -1;
  for (let index = 0; index < points.length; index += 1) {
    const dx = points[index][0] - points[i0][0];
    const dy = points[index][1] - points[i0][1];
    const dz = points[index][2] - points[i0][2];
    const distance = dx * dx + dy * dy + dz * dz;
    if (distance > far) {
      far = distance;
      i1 = index;
    }
  }
  const line = farthestFromLine(points, points[i0], points[i1]);
  if (line.distance <= epsilon) return null;
  const i2 = line.index;
  let i3 = -1;
  let maxVolume = 0;
  for (let index = 0; index < points.length; index += 1) {
    const volume = Math.abs(orient3d(points[i0], points[i1], points[i2], points[index]));
    if (volume > maxVolume) {
      maxVolume = volume;
      i3 = index;
    }
  }
  if (i3 < 0 || maxVolume <= epsilon) return null;
  const seed = [i0, i1, i2, i3];
  const interior = average(seed.map((index) => points[index]));
  if (orient3d(points[seed[0]], points[seed[1]], points[seed[2]], interior) < 0) {
    [seed[1], seed[2]] = [seed[2], seed[1]];
  }
  return { indices: seed, interior };
}

function orientedFace(a, b, c, interior, points) {
  const face = [a, b, c];
  if (orient3d(points[a], points[b], points[c], interior) < 0) {
    face[1] = c;
    face[2] = b;
  }
  return face;
}

function initialFaces(seed, interior, points) {
  const [a, b, c, d] = seed;
  const triples = [
    [a, b, c],
    [a, b, d],
    [a, c, d],
    [b, c, d],
  ];
  return triples.map(([x, y, z]) => orientedFace(x, y, z, interior, points));
}

export function buildConvexHull(points) {
  const rank = intrinsicDimension(points);
  if (rank < 3) return { faces: [], vertices: [], rank, error: "INTRINSIC_DIMENSION_LT_3" };
  const { orient: epsilon } = predicateScales(points);
  const seed = seedTetrahedron(points, epsilon);
  if (!seed) return { faces: [], vertices: [], rank, error: "NO_NON_COPLANAR_SEED" };

  let faces = initialFaces(seed.indices, seed.interior, points);
  const seedSet = new Set(seed.indices);
  for (let index = 0; index < points.length; index += 1) {
    if (seedSet.has(index)) continue;
    const point = points[index];
    const visible = [];
    for (let faceIndex = 0; faceIndex < faces.length; faceIndex += 1) {
      const face = faces[faceIndex];
      if (orient3d(points[face[0]], points[face[1]], points[face[2]], point) < -epsilon) {
        visible.push(faceIndex);
      }
    }
    if (visible.length === 0) continue;

    const visibleSet = new Set(visible);
    const edges = new Map();
    for (const faceIndex of visible) {
      const face = faces[faceIndex];
      for (let edge = 0; edge < 3; edge += 1) {
        const a = face[edge];
        const b = face[(edge + 1) % 3];
        const key = a < b ? `${a},${b}` : `${b},${a}`;
        const entry = edges.get(key);
        if (entry) entry.count += 1;
        else edges.set(key, { a, b, count: 1 });
      }
    }

    faces = faces.filter((_, faceIndex) => !visibleSet.has(faceIndex));
    for (const edge of edges.values()) {
      if (edge.count !== 1) continue;
      const face = orientedFace(edge.a, edge.b, index, seed.interior, points);
      if (triangleArea(points[face[0]], points[face[1]], points[face[2]]) > epsilon ** (2 / 3)) {
        faces.push(face);
      }
    }
  }

  const normalizedFaces = faces.map((vertices) => {
    const normal = normalize(cross(
      sub(points[vertices[1]], points[vertices[0]]),
      sub(points[vertices[2]], points[vertices[0]]),
    ));
    return { vertices, normal };
  });
  const vertices = [...new Set(normalizedFaces.flatMap((face) => face.vertices))];
  return {
    faces: normalizedFaces,
    vertices,
    rank,
    epsilon,
    error: null,
  };
}

export function hullEdges(faces) {
  const edges = new Map();
  for (const face of faces) {
    for (let index = 0; index < 3; index += 1) {
      const a = face.vertices[index];
      const b = face.vertices[(index + 1) % 3];
      const key = a < b ? `${a},${b}` : `${b},${a}`;
      const entry = edges.get(key);
      if (entry) entry.count += 1;
      else edges.set(key, { a: Math.min(a, b), b: Math.max(a, b), count: 1 });
    }
  }
  return [...edges.values()];
}
