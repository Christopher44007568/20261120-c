import { distanceToSegmentSq, pointInPolygons } from "./geometry.js";

export const DISTANCE_ENCODE_RANGE = 1;

export function median3(a, b, c) {
  return Math.max(Math.min(a, b), Math.min(Math.max(a, b), c));
}

export function generateDistanceField(specimen, size = 128) {
  const { edges, polygons } = specimen.analysis;
  const data = new Uint8Array(size * size * 4);
  const far = Infinity;

  for (let y = 0; y < size; y += 1) {
    const sampleY = (y + 0.5) / size;
    for (let x = 0; x < size; x += 1) {
      const sampleX = (x + 0.5) / size;
      let red = far;
      let green = far;
      let blue = far;

      for (const edge of edges) {
        const distanceSq = distanceToSegmentSq(
          sampleX,
          sampleY,
          edge.ax,
          edge.ay,
          edge.bx,
          edge.by,
        );
        for (const channel of edge.channels) {
          if (channel === 0 && distanceSq < red) red = distanceSq;
          if (channel === 1 && distanceSq < green) green = distanceSq;
          if (channel === 2 && distanceSq < blue) blue = distanceSq;
        }
      }

      const allDistance = Math.sqrt(Math.min(red, green, blue));
      const inside = pointInPolygons(polygons, sampleX, sampleY);
      const sign = inside ? -1 : 1;
      const offset = (y * size + x) * 4;
      data[offset] = encodeDistance(Math.sqrt(red) * sign);
      data[offset + 1] = encodeDistance(Math.sqrt(green) * sign);
      data[offset + 2] = encodeDistance(Math.sqrt(blue) * sign);
      data[offset + 3] = encodeDistance(allDistance * sign);
    }
  }

  return {
    data,
    size,
    encodeRange: DISTANCE_ENCODE_RANGE,
    glyphId: specimen.id,
    edgeCount: edges.length,
    groupCount: specimen.analysis.groups.length,
  };
}

function encodeDistance(distance) {
  const normalized = (distance / DISTANCE_ENCODE_RANGE) * 0.5 + 0.5;
  return Math.round(Math.max(0, Math.min(1, normalized)) * 255);
}

function decodeDistance(byte) {
  return ((byte / 255) * 2 - 1) * DISTANCE_ENCODE_RANGE;
}

export function textureSample(field, x, y, channel) {
  const clampedX = Math.max(0, Math.min(field.size - 1, x));
  const clampedY = Math.max(0, Math.min(field.size - 1, y));
  return decodeDistance(field.data[(clampedY * field.size + clampedX) * 4 + channel]);
}

export function sampleDistanceField(field, u, v, channels = "all") {
  const x = u * field.size - 0.5;
  const y = v * field.size - 0.5;
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const fx = x - x0;
  const fy = y - y0;
  const sampleChannel = (channel) =>
    textureSample(field, x0, y0, channel) * (1 - fx) * (1 - fy) +
    textureSample(field, x0 + 1, y0, channel) * fx * (1 - fy) +
    textureSample(field, x0, y0 + 1, channel) * (1 - fx) * fy +
    textureSample(field, x0 + 1, y0 + 1, channel) * fx * fy;

  const red = sampleChannel(0);
  const green = sampleChannel(1);
  const blue = sampleChannel(2);
  const alpha = sampleChannel(3);
  return {
    red,
    green,
    blue,
    alpha,
    msdf: median3(red, green, blue),
  };
}

function smoothstep(edge0, edge1, value) {
  const t = Math.max(0, Math.min(1, (value - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

export function reconstructCoverage(field, u, v, testPx, channelMode = "msdf") {
  const step = 1 / Math.max(1, testPx);
  const center = sampleDistanceField(field, u, v);
  const left = sampleDistanceField(field, u - step, v);
  const right = sampleDistanceField(field, u + step, v);
  const up = sampleDistanceField(field, u, v - step);
  const down = sampleDistanceField(field, u, v + step);
  const key = channelMode === "msdf" ? "msdf" : "alpha";
  const sd = center[key];
  const fwidth =
    (Math.abs(right[key] - left[key]) + Math.abs(down[key] - up[key])) * 0.5;
  const pixelRange = Math.max(1e-5, fwidth * 0.5);
  const coverage = smoothstep(-pixelRange, pixelRange, -sd);
  return {
    coverage,
    sd,
    fwidth,
    pixelRange,
    raw: center,
  };
}

export function distanceAt(field, u, v, mode = "msdf") {
  const sample = sampleDistanceField(field, u, v);
  return mode === "msdf" ? sample.msdf : sample.alpha;
}
