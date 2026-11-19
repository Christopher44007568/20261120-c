import { cross, dot, sub } from "./math.js";
import {
  insphere,
  planeOf,
  predicateScales,
  tetraVolume,
} from "./predicates.js";

function sortedFace(a, b, c) {
  return [a, b, c].sort((x, y) => x - y);
}

function faceKey(face) {
  return face.join(",");
}

function edgeKey(a, b) {
  return a < b ? `${a},${b}` : `${b},${a}`;
}

function signedVolume(points, faces) {
  let volume = 0;
  for (const face of faces) {
    const a = points[face[0]];
    const b = points[face[1]];
    const c = points[face[2]];
    volume += dot(a, cross(b, c)) / 6;
  }
  return volume;
}

export function validateHull(points, faces) {
  const edgeMap = new Map();
  const directedEdges = new Map();
  const faceKeys = new Set();
  const { orient: tolerance } = predicateScales(points);
  let minArea = Infinity;
  let maxInteriorViolation = 0;
  let duplicateFaces = 0;

  for (const face of faces) {
    const [a, b, c] = face.vertices;
    const key = faceKey(sortedFace(a, b, c));
    if (faceKeys.has(key)) duplicateFaces += 1;
    faceKeys.add(key);
    const area = 0.5 * Math.hypot(...cross(sub(points[b], points[a]), sub(points[c], points[a])));
    minArea = Math.min(minArea, area);
    for (const index of [a, b, c]) {
      if (Math.abs(dot(face.normal, sub(points[index], points[a]))) > tolerance) {
        return { ok: false, error: "FACE_NORMAL_MISMATCH" };
      }
    }
    for (let edge = 0; edge < 3; edge += 1) {
      const x = face.vertices[edge];
      const y = face.vertices[(edge + 1) % 3];
      const undirected = edgeKey(x, y);
      edgeMap.set(undirected, (edgeMap.get(undirected) ?? 0) + 1);
      const directed = `${x},${y}`;
      directedEdges.set(directed, (directedEdges.get(directed) ?? 0) + 1);
    }
    for (let index = 0; index < points.length; index += 1) {
      const violation = dot(face.normal, sub(points[index], points[a]));
      maxInteriorViolation = Math.max(maxInteriorViolation, violation);
    }
  }

  const badEdges = [...edgeMap.values()].filter((count) => count !== 2).length;
  const duplicateDirected = [...directedEdges.values()].filter((count) => count !== 1).length;
  const vertexSet = [...new Set(faces.flatMap((face) => face.vertices))];
  const edgeCount = edgeMap.size;
  const euler = vertexSet.length - edgeCount + faces.length;
  const volume = signedVolume(points, faces.map((face) => face.vertices));
  return {
    ok: badEdges === 0 && duplicateDirected === 0 && duplicateFaces === 0
      && maxInteriorViolation <= tolerance && volume > 0 && euler === 2,
    closed: badEdges === 0,
    orientable: duplicateDirected === 0,
    euler,
    edgeIncidenceErrors: badEdges,
    orientationErrors: duplicateDirected,
    duplicateFaces,
    maxInteriorViolation,
    tolerance,
    minArea,
    volume,
    vertices: vertexSet.length,
    edges: edgeCount,
    faces: faces.length,
  };
}

function tetFaces(tet) {
  const [a, b, c, d] = tet.vertices;
  return [
    [a, b, c],
    [a, b, d],
    [a, c, d],
    [b, c, d],
  ];
}

function faceOrientationSign(points, face, opposite) {
  const a = points[face[0]];
  const b = points[face[1]];
  const c = points[face[2]];
  const n = cross(sub(b, a), sub(c, a));
  return Math.sign(dot(n, sub(points[opposite], a)));
}

export function validateTets(points, tets, hullVolume) {
  const faceMap = new Map();
  const boundaryFaces = [];
  let minVolume = Infinity;
  let totalVolume = 0;
  let negativeTets = 0;
  const { orient: orientTolerance, insphere: sphereTolerance } = predicateScales(points);
  const parent = tets.map((_, index) => index);
  const find = (value) => {
    let root = value;
    while (parent[root] !== root) root = parent[root];
    while (parent[value] !== value) {
      const next = parent[value];
      parent[value] = root;
      value = next;
    }
    return root;
  };

  for (let tetIndex = 0; tetIndex < tets.length; tetIndex += 1) {
    const tet = tets[tetIndex];
    const [a, b, c, d] = tet.vertices;
    const volume = tetraVolume(points[a], points[b], points[c], points[d]);
    minVolume = Math.min(minVolume, volume);
    totalVolume += volume;
    if (volume <= orientTolerance) negativeTets += 1;
    for (const face of tetFaces(tet)) {
      const sorted = sortedFace(...face);
      const key = faceKey(sorted);
      const entry = faceMap.get(key);
      if (entry) {
        entry.count += 1;
        entry.indices.push(tetIndex);
      } else {
        faceMap.set(key, { face: sorted, count: 1, indices: [tetIndex] });
      }
    }
  }

  let orientationErrors = 0;
  for (const entry of faceMap.values()) {
    if (entry.count === 1) {
      boundaryFaces.push(entry.face);
    } else if (entry.count === 2) {
      const [first, second] = entry.indices;
      const firstOpposite = tets[first].vertices.find((index) => !entry.face.includes(index));
      const secondOpposite = tets[second].vertices.find((index) => !entry.face.includes(index));
      if (faceOrientationSign(points, entry.face, firstOpposite)
        === faceOrientationSign(points, entry.face, secondOpposite)) {
        orientationErrors += 1;
      }
      parent[find(first)] = find(second);
    }
  }

  const components = new Set(tets.map((_, index) => find(index))).size;
  const boundaryEdgeMap = new Map();
  let boundaryOrientationErrors = 0;
  const directedBoundary = new Map();
  for (const face of boundaryFaces) {
    const sorted = sortedFace(...face);
    const unordered = directBoundaryOrientation(points, sorted);
    for (let edge = 0; edge < 3; edge += 1) {
      const a = unordered[edge];
      const b = unordered[(edge + 1) % 3];
      const key = edgeKey(a, b);
      boundaryEdgeMap.set(key, (boundaryEdgeMap.get(key) ?? 0) + 1);
      const directed = `${a},${b}`;
      directedBoundary.set(directed, (directedBoundary.get(directed) ?? 0) + 1);
    }
  }
  boundaryOrientationErrors = [...directedBoundary.values()].filter((count) => count !== 1).length;
  const boundaryVertices = [...new Set(boundaryFaces.flatMap((face) => face))];
  const boundaryEuler = boundaryVertices.length - boundaryEdgeMap.size + boundaryFaces.length;

  let emptySphereViolations = 0;
  let cosphericalHits = 0;
  let maxPositiveInsphere = -Infinity;
  for (const tet of tets) {
    const vertices = tet.vertices;
    for (let index = 0; index < points.length; index += 1) {
      if (vertices.includes(index)) continue;
      const determinant = insphere(
        points[vertices[0]],
        points[vertices[1]],
        points[vertices[2]],
        points[vertices[3]],
        points[index],
      );
      maxPositiveInsphere = Math.max(maxPositiveInsphere, determinant);
      if (Math.abs(determinant) <= sphereTolerance) cosphericalHits += 1;
      else if (determinant > sphereTolerance) emptySphereViolations += 1;
    }
  }

  const usedVertices = [...new Set(tets.flatMap((tet) => tet.vertices))];
  const volumeError = hullVolume > 0 ? Math.abs(totalVolume - hullVolume) / hullVolume : Infinity;
  return {
    ok: tets.length > 0
      && negativeTets === 0
      && orientationErrors === 0
      && boundaryOrientationErrors === 0
      && components === 1
      && boundaryEuler === 2
      && volumeError <= 2e-5
      && emptySphereViolations === 0,
    manifold: orientationErrors === 0,
    internalFaceErrors: orientationErrors,
    boundaryOrientationErrors,
    components,
    boundaryEuler,
    negativeTets,
    minVolume,
    totalVolume,
    hullVolume,
    volumeError,
    emptySphereViolations,
    cosphericalHits,
    maxPositiveInsphere,
    boundaryFaces: boundaryFaces.length,
    usedVertices: usedVertices.length,
    unusedVertices: points.length - usedVertices.length,
  };
}

function directBoundaryOrientation(points, face) {
  const [a, b, c] = face;
  const normal = cross(sub(points[b], points[a]), sub(points[c], points[a]));
  const centroid = points.reduce(
    (sum, point) => [sum[0] + point[0], sum[1] + point[1], sum[2] + point[2]],
    [0, 0, 0],
  ).map((value) => value / points.length);
  const outward = dot(normal, sub(centroid, points[a]));
  return outward > 0 ? [a, c, b] : [a, b, c];
}

export function countCoplanarFacets(points, faces, tolerance) {
  const planes = [];
  const { orient: orientTolerance } = predicateScales(points);
  const planeTolerance = Math.max(tolerance ?? 0, orientTolerance / Math.max(1, points.length));
  for (const face of faces) {
    const plane = planeOf(points[face.vertices[0]], points[face.vertices[1]], points[face.vertices[2]]);
    if (!plane) continue;
    let group = planes.find((candidate) => (
      Math.abs(dot(candidate.normal, plane.normal) - 1) <= 1e-8
      && Math.abs(candidate.offset - plane.offset) <= planeTolerance
    ));
    if (!group) {
      group = { normal: plane.normal, offset: plane.offset, faces: 0, vertices: new Set() };
      planes.push(group);
    }
    group.faces += 1;
    for (const index of face.vertices) group.vertices.add(index);
  }
  let extraCoplanarPoints = 0;
  for (const group of planes) {
    if (group.faces < 2) continue;
    for (let index = 0; index < points.length; index += 1) {
      const distance = Math.abs(dot(group.normal, points[index]) - group.offset);
      if (distance <= planeTolerance && !group.vertices.has(index)) extraCoplanarPoints += 1;
    }
  }
  return {
    coplanarFacetGroups: planes.filter((group) => group.faces > 1).length,
    coplanarTriangles: planes.filter((group) => group.faces > 1)
      .reduce((sum, group) => sum + group.faces, 0),
    extraCoplanarPoints,
    planeTolerance,
  };
}

export function countPlanarClusters(points) {
  const box = { size: 1, center: [0, 0, 0] };
  let min = [Infinity, Infinity, Infinity];
  let max = [-Infinity, -Infinity, -Infinity];
  for (const point of points) {
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], point[axis]);
      max[axis] = Math.max(max[axis], point[axis]);
    }
  }
  box.size = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2], 1e-9);
  const tolerance = box.size * 1e-7;
  const seen = new Set();
  const clusters = [];
  for (let i = 0; i < points.length - 2; i += 1) {
    for (let j = i + 1; j < points.length - 1; j += 1) {
      for (let k = j + 1; k < points.length; k += 1) {
        const ab = sub(points[j], points[i]);
        const ac = sub(points[k], points[i]);
        let normal = cross(ab, ac);
        const magnitude = Math.hypot(normal[0], normal[1], normal[2]);
        if (magnitude <= tolerance * tolerance) continue;
        normal = normal.map((value) => value / magnitude);
        if (normal[0] < 0
          || (Math.abs(normal[0]) < 1e-12 && normal[1] < 0)
          || (Math.abs(normal[0]) < 1e-12 && Math.abs(normal[1]) < 1e-12 && normal[2] < 0)) {
          normal = normal.map((value) => -value);
        }
        const offset = dot(normal, points[i]);
        const key = `${normal.map((value) => Math.round(value * 1e5)).join(",")}:${Math.round((offset / box.size) * 1e7)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const members = [];
        for (let index = 0; index < points.length; index += 1) {
          if (Math.abs(dot(normal, points[index]) - offset) <= tolerance) members.push(index);
        }
        if (members.length >= 4) {
          clusters.push({ normal, offset, count: members.length, members });
        }
      }
    }
  }
  clusters.sort((a, b) => b.count - a.count);
  const maximal = [];
  for (const cluster of clusters) {
    const memberSet = new Set(cluster.members);
    const contained = maximal.some((parent) => (
      cluster.count <= parent.count
      && cluster.members.every((index) => parent.members.includes(index))
    ));
    if (!contained) maximal.push(cluster);
  }
  const structured = maximal.filter((cluster) => cluster.count >= 8);
  return {
    planarClusters: structured.length,
    planarCandidates: clusters.length,
    maxPlanarPoints: maximal.length ? maximal[0].count : 0,
    planarPointMemberships: structured.reduce((sum, cluster) => sum + cluster.count, 0),
    extraPlanarPoints: structured.reduce((sum, cluster) => sum + cluster.count - 3, 0),
  };
}

export function countCosphericalHits(points, tets) {
  const { insphere: tolerance } = predicateScales(points);
  let hits = 0;
  let violations = 0;
  for (const tet of tets) {
    const vertices = tet.vertices;
    for (let index = 0; index < points.length; index += 1) {
      if (vertices.includes(index)) continue;
      const determinant = insphere(
        points[vertices[0]],
        points[vertices[1]],
        points[vertices[2]],
        points[vertices[3]],
        points[index],
      );
      if (Math.abs(determinant) <= tolerance) hits += 1;
      else if (determinant > tolerance) violations += 1;
    }
  }
  return { hits, violations };
}
