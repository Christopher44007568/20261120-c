import { add, average, bounds, cross, dot, length, normalize, scale, sub } from "./math.js";

const LIGHT_DIRECTION = normalize([0.42, -0.68, 0.34]);
const RAY_DIRECTION = normalize([0.271, 0.137, 0.953]);

function orientedTriangle(a, b, c, interior) {
  const normal = cross(sub(b, a), sub(c, a));
  return dot(normal, sub(interior, a)) > 0 ? [a, c, b] : [a, b, c];
}

function faceEdges(faces) {
  const edges = new Map();
  faces.forEach((face, faceIndex) => {
    const vertices = face.vertices;
    for (let edge = 0; edge < 3; edge += 1) {
      const a = vertices[edge];
      const b = vertices[(edge + 1) % 3];
      const key = a < b ? `${a},${b}` : `${b},${a}`;
      const entry = edges.get(key);
      if (entry) entry.faces.push(faceIndex);
      else edges.set(key, { a, b, faces: [faceIndex] });
    }
  });
  return edges;
}

export function buildShadowVolume(mesh, direction = LIGHT_DIRECTION) {
  const points = mesh.points;
  const faces = mesh.hull.faces;
  const box = bounds(points);
  const extrusion = Math.max(box.size * 2.35, 1);
  const light = normalize(direction);
  const edgeMap = faceEdges(faces);
  const faceSign = faces.map((face) => Math.sign(dot(face.normal, light)));
  const vertices = points.map((point) => point.slice());
  const translatedOffset = vertices.length;
  const extrusionVector = scale(light, extrusion);
  for (const point of points) vertices.push(add(point, extrusionVector));
  const interior = average(vertices);

  const triangles = [];
  let nearCapFaces = 0;
  let farCapFaces = 0;
  let sideFaces = 0;
  faces.forEach((face, index) => {
    if (faceSign[index] < 0) {
      const [a, b, c] = orientedTriangle(
        points[face.vertices[0]],
        points[face.vertices[1]],
        points[face.vertices[2]],
        interior,
      );
      triangles.push({ points: [a, b, c], kind: "near-cap", source: index });
      nearCapFaces += 1;
    } else if (faceSign[index] > 0) {
      const [a, b, c] = orientedTriangle(
        add(points[face.vertices[0]], extrusionVector),
        add(points[face.vertices[1]], extrusionVector),
        add(points[face.vertices[2]], extrusionVector),
        interior,
      );
      triangles.push({ points: [a, b, c], kind: "far-cap", source: index });
      farCapFaces += 1;
    }
  });

  const silhouette = [];
  for (const edge of edgeMap.values()) {
    if (edge.faces.length !== 2) continue;
    const [first, second] = edge.faces;
    if (faceSign[first] === faceSign[second]) continue;
    if (faceSign[first] === 0 || faceSign[second] === 0) continue;
    silhouette.push(edge);
  }
  const silhouetteVertices = new Set();
  for (const edge of silhouette) {
    const a = points[edge.a];
    const b = points[edge.b];
    const ad = add(a, extrusionVector);
    const bd = add(b, extrusionVector);
    silhouetteVertices.add(edge.a);
    silhouetteVertices.add(edge.b);
    const quads = [
      [a, b, bd],
      [a, bd, ad],
    ];
    for (const raw of quads) {
      const triangle = orientedTriangle(raw[0], raw[1], raw[2], interior);
      if (length(cross(sub(triangle[1], triangle[0]), sub(triangle[2], triangle[0]))) > 1e-14) {
        triangles.push({ points: triangle, kind: "side", source: null });
        sideFaces += 1;
      }
    }
  }

  return {
    triangles,
    vertices,
    translatedOffset,
    light,
    extrusion,
    extrusionVector,
    interior,
    silhouette,
    silhouetteVertices,
    counts: {
      templateTriangles: triangles.length,
      nearCapFaces,
      farCapFaces,
      sideFaces,
      silhouetteEdges: silhouette.length,
      farCapTriangles: farCapFaces,
    },
    audit: validateShadowVolume(triangles),
  };
}

export function validateShadowVolume(triangles) {
  const edges = new Map();
  const directed = new Map();
  const vertexMap = new Map();
  let volume = 0;
  for (const triangle of triangles) {
    const [a, b, c] = triangle.points;
    volume += dot(a, cross(b, c)) / 6;
    const ids = [a, b, c].map((point) => {
      const key = point.join(",");
      if (!vertexMap.has(key)) vertexMap.set(key, vertexMap.size);
      return vertexMap.get(key);
    });
    for (let edge = 0; edge < 3; edge += 1) {
      const x = ids[edge];
      const y = ids[(edge + 1) % 3];
      const key = x < y ? `${x},${y}` : `${y},${x}`;
      edges.set(key, (edges.get(key) ?? 0) + 1);
      const forward = `${x},${y}`;
      directed.set(forward, (directed.get(forward) ?? 0) + 1);
    }
  }
  const badEdges = [...edges.values()].filter((count) => count !== 2).length;
  const badDirected = [...directed.values()].filter((count) => count !== 1).length;
  const euler = vertexMap.size - edges.size + triangles.length;
  return {
    closed: badEdges === 0,
    orientable: badDirected === 0,
    euler,
    badEdges,
    badDirected,
    vertices: vertexMap.size,
    edges: edges.size,
    faces: triangles.length,
    volume,
    capped: volume > 0 && badEdges === 0 && badDirected === 0 && euler === 2,
  };
}

function rayTriangle(origin, direction, triangle) {
  const [a, b, c] = triangle.points;
  const edge1 = sub(b, a);
  const edge2 = sub(c, a);
  const h = cross(direction, edge2);
  const determinant = dot(edge1, h);
  if (Math.abs(determinant) < 1e-12) return null;
  const inverse = 1 / determinant;
  const s = sub(origin, a);
  const u = inverse * dot(s, h);
  if (u < -1e-9 || u > 1 + 1e-9) return null;
  const q = cross(s, edge1);
  const v = inverse * dot(direction, q);
  if (v < -1e-9 || u + v > 1 + 1e-9) return null;
  const t = inverse * dot(edge2, q);
  return t > 1e-9 ? t : null;
}

export function pointInsideShadow(point, shadow) {
  let parity = 0;
  for (const triangle of shadow.triangles) {
    if (rayTriangle(point, RAY_DIRECTION, triangle) !== null) parity ^= 1;
  }
  return parity === 1;
}

function segmentHit(origin, target, shadow) {
  const delta = sub(target, origin);
  let best = null;
  for (let index = 0; index < shadow.triangles.length; index += 1) {
    const hit = rayTriangle(origin, delta, shadow.triangles[index]);
    if (hit !== null && hit <= 1 + 1e-9 && (!best || hit < best.t)) {
      best = { t: Math.min(hit, 1), triangle: index };
    }
  }
  return best;
}

function lerpPoint(a, b, t) {
  return [
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t,
  ];
}

export function traceTemplateFlips(shadow, start, end, samples = 720) {
  const records = [];
  let previousT = 0;
  let previousInside = pointInsideShadow(start, shadow);
  if (previousInside) {
    return {
      start,
      end,
      records: [],
      valid: false,
      error: "CAMERA_START_INSIDE_SHADOW",
    };
  }
  for (let sample = 1; sample <= samples; sample += 1) {
    const currentT = sample / samples;
    const current = lerpPoint(start, end, currentT);
    const inside = pointInsideShadow(current, shadow);
    if (inside !== previousInside) {
      let low = previousT;
      let high = currentT;
      for (let iteration = 0; iteration < 34; iteration += 1) {
        const middle = (low + high) * 0.5;
        const middleInside = pointInsideShadow(lerpPoint(start, end, middle), shadow);
        if (middleInside === previousInside) low = middle;
        else high = middle;
      }
      const crossingT = (low + high) * 0.5;
      const fromPoint = lerpPoint(start, end, Math.max(0, crossingT - 1e-5));
      const toPoint = lerpPoint(start, end, Math.min(1, crossingT + 1e-5));
      const hit = segmentHit(fromPoint, toPoint, shadow);
      const triangle = hit ? shadow.triangles[hit.triangle] : null;
      records.push({
        index: records.length,
        t: crossingT,
        position: lerpPoint(start, end, crossingT),
        direction: inside ? "enter" : "exit",
        surface: triangle?.kind ?? "unresolved",
        templateBefore: previousInside ? 1 : 0,
        templateAfter: inside ? 1 : 0,
        delta: (inside ? 1 : 0) - (previousInside ? 1 : 0),
        triangleIndex: hit?.triangle ?? -1,
      });
    }
    previousInside = inside;
    previousT = currentT;
  }
  const enter = records.find((record) => record.direction === "enter");
  const exit = records.find((record) => record.direction === "exit");
  return {
    start,
    end,
    records,
    valid: records.length === 2
      && enter?.surface === "near-cap"
      && ["far-cap", "side"].includes(exit?.surface),
    enterSurface: enter?.surface ?? null,
    exitSurface: exit?.surface ?? null,
    finalInside: previousInside,
    error: null,
  };
}

export function cameraCrossing(shadow, points) {
  const box = bounds(points);
  const center = box.center;
  const span = Math.max(box.size, 1);
  const start = add(center, scale(shadow.light, -span * 1.9));
  const end = add(center, scale(shadow.light, span * 4.2));
  return traceTemplateFlips(shadow, start, end);
}

export const SHADOW_LIGHT_DIRECTION = LIGHT_DIRECTION;
