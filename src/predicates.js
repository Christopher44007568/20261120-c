import {
  bounds,
  cross,
  distance2,
  dot,
  length,
  scale,
  sub,
} from "./math.js";

export function orient3d(a, b, c, d) {
  const adx = a[0] - d[0];
  const ady = a[1] - d[1];
  const adz = a[2] - d[2];
  const bdx = b[0] - d[0];
  const bdy = b[1] - d[1];
  const bdz = b[2] - d[2];
  const cdx = c[0] - d[0];
  const cdy = c[1] - d[1];
  const cdz = c[2] - d[2];
  return adx * (bdy * cdz - bdz * cdy)
    - ady * (bdx * cdz - bdz * cdx)
    + adz * (bdx * cdy - bdy * cdx);
}

export function insphere(a, b, c, d, e) {
  const ax = a[0] - e[0];
  const ay = a[1] - e[1];
  const az = a[2] - e[2];
  const bx = b[0] - e[0];
  const by = b[1] - e[1];
  const bz = b[2] - e[2];
  const cx = c[0] - e[0];
  const cy = c[1] - e[1];
  const cz = c[2] - e[2];
  const dx = d[0] - e[0];
  const dy = d[1] - e[1];
  const dz = d[2] - e[2];
  const al = ax * ax + ay * ay + az * az;
  const bl = bx * bx + by * by + bz * bz;
  const cl = cx * cx + cy * cy + cz * cz;
  const dl = dx * dx + dy * dy + dz * dz;

  return ax * (by * (cz * dl - cl * dz) - bz * (cy * dl - cl * dy) + bl * (cy * dz - cz * dy))
    - ay * (bx * (cz * dl - cl * dz) - bz * (cx * dl - cl * dx) + bl * (cx * dz - cz * dx))
    + az * (bx * (cy * dl - cl * dy) - by * (cx * dl - cl * dx) + bl * (cx * dy - cy * dx))
    - al * (bx * (cy * dz - cz * dy) - by * (cx * dz - cz * dx) + bz * (cx * dy - cy * dx));
}

export function predicateScales(points) {
  const box = bounds(points);
  const radius = Math.max(box.size, 1e-9);
  return {
    orient: radius ** 3 * 1e-12,
    insphere: radius ** 4 * 1e-11,
  };
}

export function planeOf(a, b, c) {
  const normal = cross(sub(b, a), sub(c, a));
  const magnitude = length(normal);
  if (magnitude < 1e-15) return null;
  const unit = [normal[0] / magnitude, normal[1] / magnitude, normal[2] / magnitude];
  return { normal: unit, offset: dot(unit, a), magnitude };
}

export function tetraVolume(a, b, c, d) {
  return Math.abs(orient3d(a, b, c, d)) / 6;
}

export function circumsphere(a, b, c, d) {
  const bax = b[0] - a[0];
  const bay = b[1] - a[1];
  const baz = b[2] - a[2];
  const cax = c[0] - a[0];
  const cay = c[1] - a[1];
  const caz = c[2] - a[2];
  const dax = d[0] - a[0];
  const day = d[1] - a[1];
  const daz = d[2] - a[2];
  const bb = bax * bax + bay * bay + baz * baz;
  const cc = cax * cax + cay * cay + caz * caz;
  const dd = dax * dax + day * day + daz * daz;
  const det = bax * (cay * daz - caz * day)
    - bay * (cax * daz - caz * dax)
    + baz * (cax * day - cay * dax);
  if (Math.abs(det) < 1e-18) return null;
  const x = (bb * (cay * daz - caz * day)
    - bay * (cc * daz - caz * dd)
    + baz * (cc * day - cay * dd)) / (2 * det);
  const y = (bax * (cc * daz - caz * dd)
    - bb * (cax * daz - caz * dax)
    + baz * (cax * dd - cc * dax)) / (2 * det);
  const z = (bax * (cay * dd - cc * day)
    - bay * (cax * dd - cc * dax)
    + bb * (cax * day - cay * dax)) / (2 * det);
  return [a[0] + x, a[1] + y, a[2] + z];
}

export function intrinsicDimension(points) {
  if (points.length < 2) return points.length - 1;
  const origin = points[0];
  let p1 = points[1];
  let max1 = -1;
  for (const p of points) {
    const distance = distance2(origin, p);
    if (distance > max1) {
      max1 = distance;
      p1 = p;
    }
  }
  if (max1 < 1e-20) return 0;

  const axis = sub(p1, origin);
  const axisLength2 = dot(axis, axis);
  let p2 = null;
  let max2 = -1;
  for (const p of points) {
    const relative = sub(p, origin);
    const rejection = sub(relative, scale(axis, dot(relative, axis) / axisLength2));
    const distance = dot(rejection, rejection);
    if (distance > max2) {
      max2 = distance;
      p2 = p;
    }
  }
  const box = bounds(points);
  if (!p2 || Math.sqrt(max2) < box.size * 1e-9) return 1;

  const normal = cross(axis, sub(p2, origin));
  const normalLength = length(normal);
  let max3 = 0;
  for (const p of points) {
    max3 = Math.max(max3, Math.abs(dot(normal, sub(p, origin))) / normalLength);
  }
  return max3 < box.size * 1e-9 ? 2 : 3;
}

export function dedupePoints(points, tolerance) {
  const merged = [];
  const sourceIndices = [];
  const tolerance2 = tolerance * tolerance;
  for (let index = 0; index < points.length; index += 1) {
    let duplicate = -1;
    for (let j = 0; j < merged.length; j += 1) {
      if (distance2(points[index], merged[j]) <= tolerance2) {
        duplicate = j;
        break;
      }
    }
    if (duplicate < 0) {
      merged.push(points[index].slice());
      sourceIndices.push([index]);
    } else {
      sourceIndices[duplicate].push(index);
    }
  }
  return { points: merged, sourceIndices, removed: points.length - merged.length };
}

export function pointInTetra(point, a, b, c, d, epsilon) {
  const o = orient3d(a, b, c, d);
  if (Math.abs(o) < epsilon) return false;
  const sign = Math.sign(o);
  return sign * orient3d(point, b, c, d) >= -epsilon
    && sign * orient3d(a, point, c, d) >= -epsilon
    && sign * orient3d(a, b, point, d) >= -epsilon
    && sign * orient3d(a, b, c, point) >= -epsilon;
}
