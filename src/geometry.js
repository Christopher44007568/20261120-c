const TAU = Math.PI * 2;
const EPSILON = 1e-9;

function pointDistanceSq(a, b) {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return dx * dx + dy * dy;
}

function midpoint(a, b) {
  return { x: (a.x + b.x) * 0.5, y: (a.y + b.y) * 0.5 };
}

function flattenQuad(p0, p1, p2, toleranceSq, depth, output) {
  const dx = p2.x - p0.x;
  const dy = p2.y - p0.y;
  const lengthSq = dx * dx + dy * dy;
  let flatness = 0;

  if (lengthSq < EPSILON) {
    flatness = pointDistanceSq(p1, p0);
  } else {
    const cross = Math.abs((p1.x - p0.x) * dy - (p1.y - p0.y) * dx);
    flatness = (cross * cross) / lengthSq;
  }

  if (flatness <= toleranceSq || depth >= 11) {
    output.push(p2);
    return;
  }

  const p01 = midpoint(p0, p1);
  const p12 = midpoint(p1, p2);
  const mid = midpoint(p01, p12);
  flattenQuad(p0, p01, mid, toleranceSq, depth + 1, output);
  flattenQuad(mid, p12, p2, toleranceSq, depth + 1, output);
}

function flattenCubic(p0, p1, p2, p3, toleranceSq, depth, output) {
  const dx = p3.x - p0.x;
  const dy = p3.y - p0.y;
  const lengthSq = dx * dx + dy * dy;
  let flatness = 0;

  if (lengthSq < EPSILON) {
    flatness = Math.max(pointDistanceSq(p1, p0), pointDistanceSq(p2, p0));
  } else {
    const cross1 = Math.abs((p1.x - p0.x) * dy - (p1.y - p0.y) * dx);
    const cross2 = Math.abs((p2.x - p0.x) * dy - (p2.y - p0.y) * dx);
    flatness = (Math.max(cross1, cross2) ** 2) / lengthSq;
  }

  if (flatness <= toleranceSq || depth >= 12) {
    output.push(p3);
    return;
  }

  const p01 = midpoint(p0, p1);
  const p12 = midpoint(p1, p2);
  const p23 = midpoint(p2, p3);
  const p012 = midpoint(p01, p12);
  const p123 = midpoint(p12, p23);
  const mid = midpoint(p012, p123);
  flattenCubic(p0, p01, p012, mid, toleranceSq, depth + 1, output);
  flattenCubic(mid, p123, p23, p3, toleranceSq, depth + 1, output);
}

export function flattenContours(contours, tolerance = 0.0007) {
  const toleranceSq = tolerance * tolerance;

  return contours.map((contour, contourIndex) => {
    const points = [];
    const start = contour.start || contour.segments[0]?.p0;
    if (!start) return { points, closed: contour.closed, contourIndex };
    points.push({ x: start.x, y: start.y });

    for (const segment of contour.segments) {
      if (segment.type === "line") {
        if (pointDistanceSq(points[points.length - 1], segment.p1) > EPSILON) {
          points.push({ x: segment.p1.x, y: segment.p1.y });
        }
      } else if (segment.type === "quad") {
        flattenQuad(
          points[points.length - 1],
          segment.p1,
          segment.p2,
          toleranceSq,
          0,
          points,
        );
      } else if (segment.type === "cubic") {
        flattenCubic(
          points[points.length - 1],
          segment.p1,
          segment.p2,
          segment.p3,
          toleranceSq,
          0,
          points,
        );
      }
    }

    if (contour.closed && points.length > 1 && pointDistanceSq(points[0], points.at(-1)) < EPSILON) {
      points.pop();
    }

    return { points, closed: contour.closed, contourIndex };
  });
}

export function signedArea(points) {
  let area = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    area += current.x * next.y - next.x * current.y;
  }
  return area * 0.5;
}

export function polygonCentroid(points) {
  let area = 0;
  let x = 0;
  let y = 0;

  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    const cross = current.x * next.y - next.x * current.y;
    area += cross;
    x += (current.x + next.x) * cross;
    y += (current.y + next.y) * cross;
  }

  if (Math.abs(area) < EPSILON) {
    return {
      x: points.reduce((sum, p) => sum + p.x, 0) / points.length,
      y: points.reduce((sum, p) => sum + p.y, 0) / points.length,
    };
  }

  return { x: x / (3 * area), y: y / (3 * area) };
}

export function pointInPolygon(points, x, y) {
  let inside = false;
  for (let index = 0, previous = points.length - 1; index < points.length; previous = index++) {
    const a = points[index];
    const b = points[previous];
    const intersects =
      a.y > y !== b.y > y &&
      x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y + EPSILON) + a.x;
    if (intersects) inside = !inside;
  }
  return inside;
}

export function pointInPolygons(polygons, x, y) {
  let inside = false;
  for (const polygon of polygons) {
    if (polygon.points.length > 2 && pointInPolygon(polygon.points, x, y)) {
      inside = !inside;
    }
  }
  return inside;
}

export function distanceToSegmentSq(px, py, ax, ay, bx, by) {
  const abx = bx - ax;
  const aby = by - ay;
  const lengthSq = abx * abx + aby * aby;
  const t =
    lengthSq < EPSILON
      ? 0
      : Math.max(0, Math.min(1, ((px - ax) * abx + (py - ay) * aby) / lengthSq));
  const dx = px - (ax + abx * t);
  const dy = py - (ay + aby * t);
  return dx * dx + dy * dy;
}

function vertexAngle(points, index, closed) {
  const count = points.length;
  if (count < 3) return 0;
  if (!closed && (index === 0 || index === count - 1)) return 0;
  const previous = points[(index - 1 + count) % count];
  const current = points[index];
  const next = points[(index + 1) % count];
  const ax = current.x - previous.x;
  const ay = current.y - previous.y;
  const bx = next.x - current.x;
  const by = next.y - current.y;
  const lengthA = Math.hypot(ax, ay);
  const lengthB = Math.hypot(bx, by);
  if (lengthA < EPSILON || lengthB < EPSILON) return 0;
  const cosine = Math.max(-1, Math.min(1, (ax * bx + ay * by) / (lengthA * lengthB)));
  return (Math.acos(cosine) * 180) / Math.PI;
}

function edgeRange(start, end, count) {
  const result = [];
  let index = start;
  while (index !== end) {
    result.push(index);
    index = (index + 1) % count;
  }
  return result;
}

function buildGroups(polygons, corners, cornerAngle) {
  const edges = [];
  const groups = [];

  for (const polygon of polygons) {
    const { points, closed, contourIndex } = polygon;
    if (points.length < 2) continue;
    const edgeCount = closed ? points.length : points.length - 1;
    const edgeOffset = edges.length;

    for (let index = 0; index < edgeCount; index += 1) {
      const a = points[index];
      const b = points[(index + 1) % points.length];
      edges.push({
        ax: a.x,
        ay: a.y,
        bx: b.x,
        by: b.y,
        contourIndex,
        vertexIndex: index,
        channels: [],
      });
    }

    const contourCorners = corners
      .filter((corner) => corner.contourIndex === contourIndex)
      .sort((a, b) => a.vertexIndex - b.vertexIndex);
    const localGroups = [];

    if (closed) {
      const boundaries =
        contourCorners.length > 0
          ? contourCorners.map((corner) => corner.vertexIndex)
          : [0];

      if (boundaries.length === 1) {
        const start = boundaries[0];
        localGroups.push(edgeRange(start, start, edgeCount));
      } else {
        for (let index = 0; index < boundaries.length; index += 1) {
          const start = boundaries[index];
          const end = boundaries[(index + 1) % boundaries.length];
          localGroups.push(edgeRange(start, end, edgeCount));
        }
      }
    } else {
      const boundaries = [0];
      for (const corner of contourCorners) {
        if (corner.vertexIndex > 0 && corner.vertexIndex < edgeCount) {
          boundaries.push(corner.vertexIndex);
        }
      }
      boundaries.push(edgeCount);
      for (let index = 0; index < boundaries.length - 1; index += 1) {
        const edgeIndices = [];
        for (let edge = boundaries[index]; edge < boundaries[index + 1]; edge += 1) {
          edgeIndices.push(edge);
        }
        if (edgeIndices.length) localGroups.push(edgeIndices);
      }
    }

    const channelSets =
      localGroups.length === 1
        ? [[0, 1, 2]]
        : localGroups.length === 2
          ? [
              [0, 2],
              [1, 2],
            ]
          : localGroups.map((_, index) => [index % 3]);

    localGroups.forEach((edgeIndices, groupIndex) => {
      const channels = channelSets[groupIndex] || [groupIndex % 3];
      const group = {
        contourIndex,
        groupIndex,
        channels,
        edgeIndices: edgeIndices.map((edge) => edge + edgeOffset),
        cornerAngle: contourCorners[groupIndex]?.angle || 0,
      };
      groups.push(group);
      for (const edgeIndex of group.edgeIndices) {
        for (const channel of channels) {
          if (!edges[edgeIndex].channels.includes(channel)) {
            edges[edgeIndex].channels.push(channel);
          }
        }
      }
    });
  }

  return { edges, groups, cornerAngle };
}

function segmentIntersection(a, b, c, d) {
  const orient = (p, q, r) => (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x);
  const o1 = orient(a, b, c);
  const o2 = orient(a, b, d);
  const o3 = orient(c, d, a);
  const o4 = orient(c, d, b);
  const scale = 1e-8;

  if (Math.abs(o1) < scale && Math.abs(o2) < scale && Math.abs(o3) < scale && Math.abs(o4) < scale) {
    return false;
  }
  return o1 * o2 < 0 && o3 * o4 < 0;
}

function detectSelfIntersections(polygons) {
  const issues = [];
  for (const polygon of polygons) {
    const { points, closed } = polygon;
    if (points.length < 4) continue;
    const edgeCount = closed ? points.length : points.length - 1;

    for (let first = 0; first < edgeCount && issues.length < 4; first += 1) {
      const a = points[first];
      const b = points[(first + 1) % points.length];
      const minAX = Math.min(a.x, b.x);
      const maxAX = Math.max(a.x, b.x);
      const minAY = Math.min(a.y, b.y);
      const maxAY = Math.max(a.y, b.y);

      for (let second = first + 1; second < edgeCount; second += 1) {
        if (second === first + 1) continue;
        if (closed && first === 0 && second === edgeCount - 1) continue;
        const c = points[second];
        const d = points[(second + 1) % points.length];
        if (
          Math.max(c.x, d.x) < minAX ||
          Math.min(c.x, d.x) > maxAX ||
          Math.max(c.y, d.y) < minAY ||
          Math.min(c.y, d.y) > maxAY
        ) {
          continue;
        }
        if (segmentIntersection(a, b, c, d)) {
          issues.push({
            type: "self-intersection",
            contourIndex: polygon.contourIndex,
            point: midpoint(midpoint(a, b), midpoint(c, d)),
          });
          break;
        }
      }
    }
  }
  return issues;
}

function collectContourIssues(contours, polygons, edges) {
  const issues = [];
  contours.forEach((contour, contourIndex) => {
    const polygon = polygons[contourIndex];
    if (!contour.closed) {
      issues.push({
        type: "open-contour",
        contourIndex,
        point: polygon?.points.at(-1) || contour.start,
      });
    }

    const points = polygon?.points || [];
    let previous = null;
    for (const current of points) {
      if (previous && pointDistanceSq(previous, current) < 1e-12) {
        issues.push({ type: "duplicate-vertex", contourIndex, point: current });
        break;
      }
      previous = current;
    }

    if (points.length > 2 && Math.abs(signedArea(points)) < 1e-7) {
      issues.push({ type: "degenerate-contour", contourIndex, point: polygonCentroid(points) });
    }
  });

  const zeroLengthEdge = edges.find(
    (edge) => pointDistanceSq({ x: edge.ax, y: edge.ay }, { x: edge.bx, y: edge.by }) < 1e-12,
  );
  if (zeroLengthEdge) {
    issues.push({
      type: "zero-length-edge",
      contourIndex: zeroLengthEdge.contourIndex,
      point: { x: zeroLengthEdge.ax, y: zeroLengthEdge.ay },
    });
  }

  issues.push(...detectSelfIntersections(polygons));
  return issues;
}

export function analyzeGlyph(contours, cornerAngle = 42) {
  const polygons = flattenContours(contours);
  const corners = [];

  polygons.forEach((polygon) => {
    polygon.points.forEach((point, vertexIndex) => {
      const angle = vertexAngle(polygon.points, vertexIndex, polygon.closed);
      if (angle >= cornerAngle) {
        corners.push({
          point,
          angle,
          contourIndex: polygon.contourIndex,
          vertexIndex,
        });
      }
    });
  });

  corners.sort((a, b) => b.angle - a.angle);
  const { edges, groups } = buildGroups(polygons, corners, cornerAngle);
  const issues = collectContourIssues(contours, polygons, edges);
  const ringAreas = polygons
    .map((polygon) => ({ polygon, area: signedArea(polygon.points) }))
    .filter((entry) => Math.abs(entry.area) > 1e-7);
  const largest = ringAreas.reduce(
    (best, entry) => (Math.abs(entry.area) > Math.abs(best?.area || 0) ? entry : best),
    null,
  );
  const holes = ringAreas
    .filter(
      (entry) =>
        entry !== largest &&
        largest &&
        Math.sign(entry.area) !== Math.sign(largest.area),
    )
    .map((entry) => polygonCentroid(entry.polygon.points));

  return {
    polygons,
    edges,
    groups,
    corners,
    holes,
    issues,
    contourErrors: issues.filter((issue) =>
      ["open-contour", "self-intersection", "degenerate-contour", "duplicate-vertex", "zero-length-edge"].includes(
        issue.type,
      ),
    ),
  };
}

export function pointNormal(points, index) {
  const count = points.length;
  const previous = points[(index - 1 + count) % count];
  const current = points[index];
  const next = points[(index + 1) % count];
  const ax = current.x - previous.x;
  const ay = current.y - previous.y;
  const bx = next.x - current.x;
  const by = next.y - current.y;
  const length = Math.hypot(ax + bx, ay + by);
  if (length < EPSILON) return { x: 0, y: 0 };
  return { x: -(ay + by) / length, y: (ax + bx) / length };
}

export function nearestPointOnSegments(edges, x, y) {
  let bestDistanceSq = Infinity;
  for (const edge of edges) {
    const dx = edge.bx - edge.ax;
    const dy = edge.by - edge.ay;
    const lengthSq = dx * dx + dy * dy;
    const t =
      lengthSq < EPSILON
        ? 0
        : Math.max(0, Math.min(1, ((x - edge.ax) * dx + (y - edge.ay) * dy) / lengthSq));
    const px = edge.ax + dx * t;
    const py = edge.ay + dy * t;
    const distanceSq = (x - px) ** 2 + (y - py) ** 2;
    if (distanceSq < bestDistanceSq) bestDistanceSq = distanceSq;
  }
  return Math.sqrt(bestDistanceSq);
}

export { TAU };
