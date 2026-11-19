import { triangleFacesLight } from "./geometry.js";
import { clipPoint, vec3 } from "./math.js";

export const LIGHT_DIRECTION = vec3.normalize([-0.52, 1.0, 0.42]);
export const VOLUME_LENGTH = 26;

function vertex(mesh, index) {
  return [
    mesh.positions[index * 3],
    mesh.positions[index * 3 + 1],
    mesh.positions[index * 3 + 2],
  ];
}

function pushTriangle(output, a, b, c) {
  output.push(...a, ...b, ...c);
}

function projectedVertex(point) {
  return vec3.sub(point, vec3.scale(LIGHT_DIRECTION, VOLUME_LENGTH));
}

function buildClosedCapsAndSides(mesh, output, caps) {
  const facing = mesh.triangles.map((triangle, index) =>
    triangleFacesLight(mesh, index, LIGHT_DIRECTION));
  const lightEdges = new Map();

  mesh.triangles.forEach((triangle, triangleIndex) => {
    if (!facing[triangleIndex]) return;
    for (let edgeIndex = 0; edgeIndex < 3; edgeIndex += 1) {
      const a = triangle[edgeIndex];
      const b = triangle[(edgeIndex + 1) % 3];
      const reverseKey = `${b}:${a}`;
      if (lightEdges.has(reverseKey)) {
        lightEdges.delete(reverseKey);
      } else {
        lightEdges.set(`${a}:${b}`, { a, b });
      }
    }
  });

  const silhouetteEdges = [...lightEdges.values()];
  for (const edge of silhouetteEdges) {
    const a = vertex(mesh, edge.a);
    const b = vertex(mesh, edge.b);
    const aFar = projectedVertex(a);
    const bFar = projectedVertex(b);
    pushTriangle(output, a, bFar, b);
    pushTriangle(output, a, aFar, bFar);
  }

  if (!caps) {
    return { sideTriangles: silhouetteEdges.length * 2, capTriangles: 0, silhouetteEdges };
  }

  let capTriangles = 0;
  mesh.triangles.forEach((triangle, triangleIndex) => {
    if (!facing[triangleIndex]) return;
    const a = vertex(mesh, triangle[0]);
    const b = vertex(mesh, triangle[1]);
    const c = vertex(mesh, triangle[2]);
    pushTriangle(output, a, b, c);
    const aFar = projectedVertex(a);
    const bFar = projectedVertex(b);
    const cFar = projectedVertex(c);
    pushTriangle(output, aFar, cFar, bFar);
    capTriangles += 2;
  });

  return { sideTriangles: silhouetteEdges.length * 2, capTriangles, silhouetteEdges };
}

function buildOpenCapsAndSides(mesh, output, caps) {
  let sideTriangles = 0;
  let capTriangles = 0;
  for (const triangle of mesh.triangles) {
    const a = vertex(mesh, triangle[0]);
    const b = vertex(mesh, triangle[1]);
    const c = vertex(mesh, triangle[2]);
    const aFar = projectedVertex(a);
    const bFar = projectedVertex(b);
    const cFar = projectedVertex(c);
    pushTriangle(output, a, bFar, b);
    pushTriangle(output, a, aFar, bFar);
    pushTriangle(output, b, cFar, c);
    pushTriangle(output, b, bFar, cFar);
    pushTriangle(output, c, aFar, a);
    pushTriangle(output, c, cFar, aFar);
    sideTriangles += 6;
    if (caps) {
      pushTriangle(output, a, b, c);
      pushTriangle(output, aFar, cFar, bFar);
      capTriangles += 2;
    }
  }
  return { sideTriangles, capTriangles, silhouetteEdges: [] };
}

export function buildShadowVolume(mesh, options = {}) {
  const caps = options.caps ?? true;
  const output = [];
  const method = mesh.closed ? "silhouette+caps" : "per-triangle-prism";
  const parts = mesh.closed
    ? buildClosedCapsAndSides(mesh, output, caps)
    : buildOpenCapsAndSides(mesh, output, caps);
  const positions = new Float32Array(output);
  return {
    positions,
    vertexCount: positions.length / 3,
    triangleCount: positions.length / 9,
    sideTriangles: parts.sideTriangles,
    capTriangles: parts.capTriangles,
    silhouetteEdges: parts.silhouetteEdges,
    method,
    caps,
    closed: mesh.closed,
  };
}

function clipNearPlane(polygon) {
  const result = [];
  for (let index = 0; index < polygon.length; index += 1) {
    const current = polygon[index];
    const next = polygon[(index + 1) % polygon.length];
    const currentIn = current[3] > 1e-5;
    const nextIn = next[3] > 1e-5;
    if (currentIn) result.push(current);
    if (currentIn !== nextIn) {
      const t = (1e-5 - current[3]) / (next[3] - current[3]);
      result.push(current.map((value, component) => value + (next[component] - value) * t));
    }
  }
  return result;
}

function screenPoint(clip, width, height) {
  const inverseW = 1 / clip[3];
  return [
    (clip[0] * inverseW * 0.5 + 0.5) * width,
    (1 - (clip[1] * inverseW * 0.5 + 0.5)) * height,
  ];
}

function fillTriangle(mask, width, height, points) {
  const [a, b, c] = points;
  const area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  if (Math.abs(area) < 1e-6) return 0;
  const minX = Math.max(0, Math.floor(Math.min(a[0], b[0], c[0])));
  const maxX = Math.min(width - 1, Math.ceil(Math.max(a[0], b[0], c[0])));
  const minY = Math.max(0, Math.floor(Math.min(a[1], b[1], c[1])));
  const maxY = Math.min(height - 1, Math.ceil(Math.max(a[1], b[1], c[1])));
  let filled = 0;
  const sign = Math.sign(area);
  for (let y = minY; y <= maxY; y += 1) {
    const py = y + 0.5;
    for (let x = minX; x <= maxX; x += 1) {
      const px = x + 0.5;
      const e0 = ((b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0])) * sign;
      const e1 = ((c[0] - b[0]) * (py - b[1]) - (c[1] - b[1]) * (px - b[0])) * sign;
      const e2 = ((a[0] - c[0]) * (py - c[1]) - (a[1] - c[1]) * (px - c[0])) * sign;
      if (e0 >= 0 && e1 >= 0 && e2 >= 0) {
        mask[y * width + x] = 1;
        filled += 1;
      }
    }
  }
  return filled;
}

export function measureVolumeCoverage(volume, viewProjection, width, height) {
  const mask = new Uint8Array(width * height);
  let covered = 0;
  let fragments = 0;
  const positions = volume.positions;
  for (let offset = 0; offset < positions.length; offset += 9) {
    const polygon = clipNearPlane([
      clipPoint(viewProjection, [positions[offset], positions[offset + 1], positions[offset + 2]]),
      clipPoint(viewProjection, [positions[offset + 3], positions[offset + 4], positions[offset + 5]]),
      clipPoint(viewProjection, [positions[offset + 6], positions[offset + 7], positions[offset + 8]]),
    ]);
    if (polygon.length < 3) continue;
    const points = polygon.map((clip) => screenPoint(clip, width, height));
    for (let index = 1; index < points.length - 1; index += 1) {
      fragments += fillTriangle(mask, width, height, [points[0], points[index], points[index + 1]]);
    }
  }
  for (let index = 0; index < mask.length; index += 1) covered += mask[index];
  return {
    pixels: covered,
    coverage: covered / (width * height),
    fragments,
    overdraw: covered > 0 ? fragments / covered : 0,
  };
}

export function volumeDebugLines(volume) {
  const positions = volume.positions;
  const edges = [];
  for (let offset = 0; offset < positions.length; offset += 9) {
    for (let edge = 0; edge < 3; edge += 1) {
      const a = offset + edge * 3;
      const b = offset + ((edge + 1) % 3) * 3;
      edges.push(
        positions[a], positions[a + 1], positions[a + 2],
        positions[b], positions[b + 1], positions[b + 2],
      );
    }
  }
  return new Float32Array(edges);
}

