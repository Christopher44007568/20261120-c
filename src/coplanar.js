import { bounds, cross, dot, hash01, normalize, sub } from "./math.js";
import { orient3d } from "./predicates.js";

function triangleArea2(a, b, c) {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function incircle(a, b, c, d) {
  const ax = a[0] - d[0];
  const ay = a[1] - d[1];
  const bx = b[0] - d[0];
  const by = b[1] - d[1];
  const cx = c[0] - d[0];
  const cy = c[1] - d[1];
  const al = ax * ax + ay * ay;
  const bl = bx * bx + by * by;
  const cl = cx * cx + cy * cy;
  return ax * (by * cl - bl * cy)
    - ay * (bx * cl - bl * cx)
    + al * (bx * cy - by * cx);
}

function projectionBasis(normal) {
  const helper = Math.abs(normal[2]) < 0.8 ? [0, 0, 1] : [0, 1, 0];
  const u = normalize(cross(normal, helper), [1, 0, 0]);
  const v = normalize(cross(normal, u), [0, 1, 0]);
  return { u, v };
}

function project(point, center, basis) {
  const relative = sub(point, center);
  return [dot(relative, basis.u), dot(relative, basis.v)];
}

function superTriangle(points) {
  const box = bounds(points.map((point) => [point[0], point[1], 0]));
  const span = Math.max(box.size, 1) * 32;
  const [cx, cy] = box.center;
  return [
    [cx - span * 2, cy - span],
    [cx + span * 2, cy - span],
    [cx, cy + span * 2],
  ];
}

export function triangulate2D(points) {
  const box = bounds(points.map((point) => [point[0], point[1], 0]));
  const amplitude = Math.max(box.size * 2e-8, 1e-11);
  const working = points.map((point, index) => [
    point[0] + (hash01(index, 41) * 2 - 1) * amplitude,
    point[1] + (hash01(index, 71) * 2 - 1) * amplitude,
  ]);
  const superPoints = superTriangle(working);
  const offset = working.length;
  working.push(...superPoints);
  let triangles = [[offset, offset + 1, offset + 2]];
  if (triangleArea2(working[offset], working[offset + 1], working[offset + 2]) < 0) {
    triangles[0] = [offset, offset + 2, offset + 1];
  }
  const scale = Math.max(box.size, 1);
  const tolerance = scale ** 4 * 1e-11;
  let cocircularTies = 0;

  for (let pointIndex = 0; pointIndex < points.length; pointIndex += 1) {
    const point = working[pointIndex];
    const cavity = [];
    for (let index = 0; index < triangles.length; index += 1) {
      const [a, b, c] = triangles[index];
      const determinant = incircle(working[a], working[b], working[c], point);
      if (Math.abs(determinant) <= tolerance) cocircularTies += 1;
      if (determinant >= -tolerance) cavity.push(index);
    }
    if (!cavity.length) return { triangles: [], error: `EMPTY_2D_CAVITY_${pointIndex}` };
    const edges = new Map();
    for (const index of cavity) {
      const [a, b, c] = triangles[index];
      for (const [x, y] of [[a, b], [b, c], [c, a]]) {
        const key = x < y ? `${x},${y}` : `${y},${x}`;
        const entry = edges.get(key);
        if (entry) entry.count += 1;
        else edges.set(key, { a: x, b: y, count: 1 });
      }
    }
    const cavitySet = new Set(cavity);
    triangles = triangles.filter((_, index) => !cavitySet.has(index));
    for (const edge of edges.values()) {
      if (edge.count !== 1) continue;
      let triangle = [edge.a, edge.b, pointIndex];
      if (triangleArea2(working[triangle[0]], working[triangle[1]], working[triangle[2]]) < 0) {
        [triangle[1], triangle[2]] = [triangle[2], triangle[1]];
      }
      if (Math.abs(triangleArea2(
        working[triangle[0]],
        working[triangle[1]],
        working[triangle[2]],
      )) > tolerance * 1e-5) {
        triangles.push(triangle);
      }
    }
  }

  const finite = triangles.filter((triangle) => triangle.every((index) => index < points.length));
  return {
    triangles: finite,
    cocircularTies,
    error: finite.length ? null : "NO_FINITE_2D_TRIANGLES",
  };
}

export function buildCoplanarTetrahedralization(points, planarCount, topIndex, bottomIndex) {
  const top = points[topIndex];
  const bottom = points[bottomIndex];
  const normal = normalize(sub(top, bottom));
  const center = points.slice(0, planarCount).reduce(
    (sum, point) => [sum[0] + point[0], sum[1] + point[1], sum[2] + point[2]],
    [0, 0, 0],
  ).map((value) => value / planarCount);
  const basis = projectionBasis(normal);
  const projected = points.slice(0, planarCount).map((point) => project(point, center, basis));
  const triangulation = triangulate2D(projected);
  if (triangulation.error) return { tets: [], error: triangulation.error };

  const tets = [];
  const used = new Set();
  for (const [a, b, c] of triangulation.triangles) {
    let upper = [topIndex, a, b, c];
    if (orient3d(points[upper[0]], points[upper[1]], points[upper[2]], points[upper[3]]) < 0) {
      [upper[1], upper[2]] = [upper[2], upper[1]];
    }
    let lower = [bottomIndex, a, b, c];
    if (orient3d(points[lower[0]], points[lower[1]], points[lower[2]], points[lower[3]]) < 0) {
      [lower[1], lower[2]] = [lower[2], lower[1]];
    }
    tets.push({ vertices: upper }, { vertices: lower });
    used.add(a);
    used.add(b);
    used.add(c);
  }
  const missingPlanar = [];
  for (let index = 0; index < planarCount; index += 1) {
    if (!used.has(index)) missingPlanar.push(index);
  }
  return {
    tets,
    triangles2d: triangulation.triangles,
    cocircularTies: triangulation.cocircularTies,
    missingPlanar,
    error: missingPlanar.length ? "PLANAR_POINTS_NOT_TRIANGULATED" : null,
  };
}
