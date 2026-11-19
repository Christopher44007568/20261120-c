import { average, bounds, distance2, length, scale, sub } from "./math.js";
import { buildCoplanarTetrahedralization } from "./coplanar.js";
import { buildDelaunay, delaunayEdges } from "./delaunay.js";
import { buildConvexHull, hullEdges } from "./hull.js";
import { planeOf, intrinsicDimension } from "./predicates.js";
import {
  countCosphericalHits,
  countCoplanarFacets,
  countPlanarClusters,
  validateHull,
  validateTets,
} from "./validate.js";

function farthestPair(points) {
  let a = 0;
  let b = 0;
  let best = -1;
  for (let i = 0; i < points.length; i += 1) {
    for (let j = i + 1; j < points.length; j += 1) {
      const distance = distance2(points[i], points[j]);
      if (distance > best) {
        best = distance;
        a = i;
        b = j;
      }
    }
  }
  return [a, b];
}

function coplanarSupport(points) {
  const [i0, i1] = farthestPair(points);
  const axis = sub(points[i1], points[i0]);
  const denominator = Math.max(length(axis) ** 2, 1e-30);
  let i2 = -1;
  let best = 0;
  for (let index = 0; index < points.length; index += 1) {
    const relative = sub(points[index], points[i0]);
    const projection = [axis[0] * (relative[0] * axis[0] + relative[1] * axis[1] + relative[2] * axis[2]) / denominator,
      axis[1] * (relative[0] * axis[0] + relative[1] * axis[1] + relative[2] * axis[2]) / denominator,
      axis[2] * (relative[0] * axis[0] + relative[1] * axis[1] + relative[2] * axis[2]) / denominator];
    const rejection = sub(relative, projection);
    const distance = dot3(rejection, rejection);
    if (distance > best) {
      best = distance;
      i2 = index;
    }
  }
  if (i2 < 0) return null;
  const plane = planeOf(points[i0], points[i1], points[i2]);
  if (!plane) return null;
  const center = average(points);
  let radius = 0;
  for (const point of points) radius = Math.max(radius, Math.sqrt(distance2(point, center)));
  return {
    center,
    normal: plane.normal,
    height: Math.max(radius * 0.72, 1e-3),
  };
}

function dot3(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function preparePoints(rawPoints) {
  const box = bounds(rawPoints);
  const tolerance = Math.max(box.size * 1e-9, 1e-12);
  const dedupeMap = new Map();
  const points = [];
  for (const point of rawPoints) {
    let merged = false;
    for (const existing of points) {
      if (distance2(existing, point) <= tolerance * tolerance) {
        merged = true;
        break;
      }
    }
    if (!merged) points.push(point.slice());
  }
  const duplicatesRemoved = rawPoints.length - points.length;
  const originalCount = points.length;
  const rank = intrinsicDimension(points);
  const synthetic = [];

  if (rank === 2) {
    const support = coplanarSupport(points);
    if (!support) {
      return { error: "COPLANAR_SUPPORT_FAILED" };
    }
    points.push(scale(support.normal, support.height).map((value, axis) => value + support.center[axis]));
    points.push(scale(support.normal, -support.height).map((value, axis) => value + support.center[axis]));
    synthetic.push(points.length - 2, points.length - 1);
  } else if (rank < 2) {
    return { error: "INTRINSIC_DIMENSION_LT_2" };
  }

  return {
    points,
    duplicatesRemoved,
    originalCount,
    rank,
    synthetic,
    tolerance,
    error: null,
  };
}

export function buildMesh(dataset) {
  const prepared = preparePoints(dataset.points);
  if (prepared.error) {
    return { dataset, error: prepared.error };
  }
  let delaunay;
  if (prepared.rank === 2) {
    const topIndex = prepared.synthetic[0];
    const bottomIndex = prepared.synthetic[1];
    const planar = buildCoplanarTetrahedralization(
      prepared.points,
      prepared.originalCount,
      topIndex,
      bottomIndex,
    );
    delaunay = {
      tets: planar.tets,
      points: prepared.points,
      cosphericalTies: planar.cocircularTies ?? 0,
      degenerateTetsSkipped: 0,
      error: planar.error,
      planarTriangles: planar.triangles2d,
    };
  } else {
    delaunay = buildDelaunay(prepared.points);
  }
  if (delaunay.error) {
    return {
      dataset,
      error: delaunay.error,
      points: prepared.points,
    };
  }

  const points = prepared.rank === 2 ? prepared.points : delaunay.regularizedPoints;
  const sourcePoints = prepared.points;
  const synthetic = prepared.synthetic.filter((index) => index < points.length);
  const hull = buildConvexHull(points);
  if (hull.error) {
    return { dataset, points, error: hull.error };
  }
  const hullAudit = validateHull(points, hull.faces);
  const tetAudit = validateTets(points, delaunay.tets, hullAudit.volume);
  const coplanar = countCoplanarFacets(points, hull.faces);
  const sourcePlanar = countPlanarClusters(
    sourcePoints.slice(0, prepared.originalCount),
  );
  const sourceCospherical = countCosphericalHits(sourcePoints, delaunay.tets);
  const tetEdges = delaunayEdges(delaunay.tets);
  const hEdges = hullEdges(hull.faces);
  const syntheticSet = new Set(synthetic);
  const hullVertexSet = new Set(hull.vertices);
  const tetVertexSet = new Set(delaunay.tets.flatMap((tet) => tet.vertices));

  const counts = {
    inputVertices: dataset.points.length,
    uniqueVertices: prepared.originalCount,
    meshVertices: points.length,
    originalMeshVertices: points.length - synthetic.length,
    syntheticVertices: synthetic.length,
    hullVertices: hull.vertices.length,
    hullEdges: hEdges.length,
    hullFaces: hull.faces.length,
    tetrahedra: delaunay.tets.length,
    tetraEdges: tetEdges.length,
    tetraFaces: delaunay.tets.length * 4,
    boundaryFaces: tetAudit.boundaryFaces,
  };

  const degeneracy = {
    duplicatesRemoved: prepared.duplicatesRemoved,
    intrinsicRank: prepared.rank,
    syntheticAnchors: synthetic.length,
    planarClusters: sourcePlanar.planarClusters,
    planarCandidates: sourcePlanar.planarCandidates,
    maxPlanarPoints: sourcePlanar.maxPlanarPoints,
    extraCoplanarPoints: sourcePlanar.extraPlanarPoints,
    coplanarHullFacetGroups: coplanar.coplanarFacetGroups,
    cosphericalInsertionTies: delaunay.cosphericalTies,
    cosphericalEmptySphereHits: sourceCospherical.hits,
    degenerateTetsRemoved: delaunay.degenerateTetsSkipped ?? 0,
    maxRegularizationOffset: delaunay.regularization?.maxDisplacement ?? 0,
  };

  return {
    dataset,
    points,
    sourcePoints,
    rawPoints: dataset.points,
    synthetic: syntheticSet,
    hull,
    tets: delaunay.tets,
    tetEdges,
    hullEdges: hEdges,
    hullAudit,
    tetAudit,
    counts,
    degeneracy,
    audits: {
      hullClosed: hullAudit.closed && hullAudit.orientable,
      hullTopology: hullAudit.euler === 2,
      tetraManifold: tetAudit.manifold,
      tetraTopology: tetAudit.components === 1 && tetAudit.boundaryEuler === 2,
      volumeConserved: tetAudit.volumeError <= 2e-5,
      delaunayEmpty: tetAudit.emptySphereViolations === 0,
      noDegenerateTets: tetAudit.negativeTets === 0,
      allTetraVerticesUsed: tetAudit.unusedVertices === 0,
    },
    allPassed: hullAudit.ok && tetAudit.ok,
    hullVertices: hullVertexSet,
    tetraVertices: tetVertexSet,
    error: null,
  };
}
