import { bounds, hash01, length, sub } from "./math.js";
import {
  circumsphere,
  dedupePoints,
  insphere,
  intrinsicDimension,
  orient3d,
  predicateScales,
} from "./predicates.js";

function positiveTetra(points, vertices) {
  return orient3d(
    points[vertices[0]],
    points[vertices[1]],
    points[vertices[2]],
    points[vertices[3]],
  ) > 0;
}

function outwardFaces(points, tet) {
  const candidates = [
    { face: [tet[1], tet[2], tet[3]], opposite: tet[0] },
    { face: [tet[0], tet[2], tet[3]], opposite: tet[1] },
    { face: [tet[0], tet[1], tet[3]], opposite: tet[2] },
    { face: [tet[0], tet[1], tet[2]], opposite: tet[3] },
  ];
  return candidates.map(({ face, opposite }) => {
    const copy = face.slice();
    if (orient3d(
      points[copy[0]],
      points[copy[1]],
      points[copy[2]],
      points[opposite],
    ) > 0) {
      [copy[1], copy[2]] = [copy[2], copy[1]];
    }
    return copy;
  });
}

function superTetrahedron(box) {
  const center = box.center;
  const radius = Math.max(box.size, 1) * 1600;
  return [
    [center[0] - radius, center[1] - radius, center[2] - radius],
    [center[0] + radius, center[1] - radius, center[2] - radius],
    [center[0], center[1] + radius, center[2] - radius],
    [center[0], center[1], center[2] + radius],
  ];
}

function perturb(points) {
  const box = bounds(points);
  const amplitude = Math.max(box.size * 1.25e-7, 1e-10);
  const perturbed = points.map((point, index) => {
    const jx = hash01(index, 11, 1) * 2 - 1;
    const jy = hash01(index, 23, 2) * 2 - 1;
    const jz = hash01(index, 37, 3) * 2 - 1;
    return [
      point[0] + jx * amplitude,
      point[1] + jy * amplitude,
      point[2] + jz * amplitude,
    ];
  });
  let maxDisplacement = 0;
  for (let index = 0; index < points.length; index += 1) {
    maxDisplacement = Math.max(maxDisplacement, length(sub(perturbed[index], points[index])));
  }
  return { points: perturbed, amplitude, maxDisplacement };
}

function uniqueFaceMap() {
  return new Map();
}

function addCavityFace(map, face) {
  const sorted = face.slice().sort((a, b) => a - b);
  const key = sorted.join(",");
  const entry = map.get(key);
  if (entry) entry.count += 1;
  else map.set(key, { key, face, count: 1 });
}

export function buildDelaunay(inputPoints) {
  const box = bounds(inputPoints);
  const dedupe = dedupePoints(inputPoints, Math.max(box.size * 1e-9, 1e-12));
  const points = dedupe.points;
  const rank = intrinsicDimension(points);
  if (rank < 3) {
    return {
      tets: [],
      points,
      regularizedPoints: points.map((point) => point.slice()),
      regularization: { amplitude: 0, maxDisplacement: 0 },
      sourceIndices: dedupe.sourceIndices,
      removedDuplicates: dedupe.removed,
      rank,
      error: "INTRINSIC_DIMENSION_LT_3",
    };
  }

  const regularization = perturb(points);
  const working = regularization.points;
  const superTetra = superTetrahedron(box);
  const superOffset = working.length;
  working.push(...superTetra);
  let superVertices = [superOffset, superOffset + 1, superOffset + 2, superOffset + 3];
  if (!positiveTetra(working, superVertices)) {
    [superVertices[1], superVertices[2]] = [superVertices[2], superVertices[1]];
  }

  let tets = [{ vertices: superVertices, alive: true }];
  let cosphericalTies = 0;
  let degenerateTetsSkipped = 0;
  let cavityFaceViolations = 0;
  let maxCavityTets = 0;
  let maxCavityComponents = 0;
  const { insphere: tolerance } = predicateScales(points);

  for (let pointIndex = 0; pointIndex < points.length; pointIndex += 1) {
    const point = working[pointIndex];
    const cavity = [];
    for (let tetIndex = 0; tetIndex < tets.length; tetIndex += 1) {
      const tet = tets[tetIndex];
      if (!tet.alive) continue;
      const [a, b, c, d] = tet.vertices;
      const determinant = insphere(working[a], working[b], working[c], working[d], point);
      if (Math.abs(determinant) <= tolerance) cosphericalTies += 1;
      if (determinant >= -tolerance) cavity.push(tetIndex);
    }
    if (cavity.length === 0) {
      return {
        tets: [],
        points,
        regularizedPoints: working.slice(0, points.length),
        regularization: {
          amplitude: regularization.amplitude,
          maxDisplacement: regularization.maxDisplacement,
        },
        sourceIndices: dedupe.sourceIndices,
        removedDuplicates: dedupe.removed,
        rank,
        error: `EMPTY_CAVITY_AT_POINT_${pointIndex}`,
      };
    }
    maxCavityTets = Math.max(maxCavityTets, cavity.length);
    const cavitySet = new Set(cavity);
    const shared = new Map();
    for (const tetIndex of cavity) {
      const tet = tets[tetIndex];
      for (const face of outwardFaces(working, tet.vertices)) {
        const key = face.slice().sort((a, b) => a - b).join(",");
        if (!shared.has(key)) shared.set(key, []);
        shared.get(key).push(tetIndex);
      }
    }
    const cavityParent = new Map(cavity.map((index) => [index, index]));
    const findCavity = (value) => {
      let root = value;
      while (cavityParent.get(root) !== root) root = cavityParent.get(root);
      return root;
    };
    for (const owners of shared.values()) {
      if (owners.length > 2) cavityFaceViolations += 1;
      if (owners.length === 2 && cavitySet.has(owners[0]) && cavitySet.has(owners[1])) {
        const a = findCavity(owners[0]);
        const b = findCavity(owners[1]);
        if (a !== b) cavityParent.set(a, b);
      }
    }
    const roots = new Set(cavity.map((index) => findCavity(index)));
    maxCavityComponents = Math.max(maxCavityComponents, roots.size);

    const faces = uniqueFaceMap();
    for (const tetIndex of cavity) {
      const tet = tets[tetIndex];
      for (const face of outwardFaces(working, tet.vertices)) addCavityFace(faces, face);
      tet.alive = false;
    }
    tets = tets.filter((tet) => tet.alive);

    for (const entry of faces.values()) {
      if (entry.count !== 1) continue;
      const vertices = entry.face.slice();
      let faceOrientation = orient3d(
        working[vertices[0]],
        working[vertices[1]],
        working[vertices[2]],
        point,
      );
      if (faceOrientation < 0) {
        [vertices[1], vertices[2]] = [vertices[2], vertices[1]];
        faceOrientation = -faceOrientation;
      }
      if (faceOrientation > tolerance * 1e-6) {
        tets.push({ vertices: [...vertices, pointIndex], alive: true });
      } else {
        degenerateTetsSkipped += 1;
      }
    }
  }

  const finalTets = tets
    .filter((tet) => tet.vertices.every((index) => index < points.length))
    .map((tet) => ({ vertices: tet.vertices.slice() }));

  return {
    tets: finalTets,
    points,
    regularizedPoints: working.slice(0, points.length),
    regularization: {
      amplitude: regularization.amplitude,
      maxDisplacement: regularization.maxDisplacement,
    },
    sourceIndices: dedupe.sourceIndices,
    removedDuplicates: dedupe.removed,
    rank,
    cosphericalTies,
    degenerateTetsSkipped,
    cavityFaceViolations,
    maxCavityTets,
    maxCavityComponents,
    emptyCavityCount: 0,
    error: finalTets.length ? null : "NO_FINITE_TETRAHEDRA",
    circumspheres: finalTets.map((tet) => circumsphere(
      points[tet.vertices[0]],
      points[tet.vertices[1]],
      points[tet.vertices[2]],
      points[tet.vertices[3]],
    )),
  };
}

export function delaunayEdges(tets) {
  const edges = new Map();
  const pairs = [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]];
  for (const tet of tets) {
    for (const [i, j] of pairs) {
      const a = tet.vertices[i];
      const b = tet.vertices[j];
      const key = a < b ? `${a},${b}` : `${b},${a}`;
      if (!edges.has(key)) edges.set(key, { a: Math.min(a, b), b: Math.max(a, b) });
    }
  }
  return [...edges.values()];
}
