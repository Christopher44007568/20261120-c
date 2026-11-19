function longestRun(row, width, threshold) {
  let bestStart = -1;
  let bestEnd = -1;
  let start = -1;
  for (let x = 0; x <= width; x += 1) {
    const filled = x < width && row[x] > threshold;
    if (filled && start < 0) start = x;
    if (!filled && start >= 0) {
      if (x - start > bestEnd - bestStart) {
        bestStart = start;
        bestEnd = x;
      }
      start = -1;
    }
  }
  return { start: bestStart, end: bestEnd };
}

function lineResidual(points) {
  if (points.length < 4) return { rms: 0, rows: points.length };
  let sumY = 0;
  let sumX = 0;
  let sumYY = 0;
  let sumYX = 0;
  for (const [y, x] of points) {
    sumY += y;
    sumX += x;
    sumYY += y * y;
    sumYX += y * x;
  }
  const count = points.length;
  const denominator = count * sumYY - sumY * sumY;
  const slope = Math.abs(denominator) < 1e-6 ? 0 : (count * sumYX - sumY * sumX) / denominator;
  const intercept = (sumX - slope * sumY) / count;
  let error = 0;
  for (const [y, x] of points) {
    const delta = x - (slope * y + intercept);
    error += delta * delta;
  }
  return { rms: Math.sqrt(error / count), rows: count };
}

export function analyzeThinShadowEdge(mask, width, height) {
  const rows = [];
  const minRun = Math.max(8, Math.round(width * 0.018));
  for (let y = 0; y < height; y += 1) {
    const row = mask.subarray(y * width, (y + 1) * width);
    const run = longestRun(row, width, 127);
    if (run.start <= 0 || run.end >= width || run.end - run.start < minRun) continue;
    rows.push([y, run.start, run.end - 1, run.end - run.start]);
  }
  if (rows.length < 12) return { left: { rms: 0, rows: 0 }, right: { rms: 0, rows: 0 }, rms: 0, rows: 0 };
  const lengths = rows.map((row) => row[3]).sort((a, b) => a - b);
  const median = lengths[Math.floor(lengths.length / 2)];
  const trimmed = rows.filter((row) => row[3] >= median * 0.75);
  const trim = Math.max(3, Math.round(trimmed.length * 0.08));
  const usable = trimmed.slice(trim, trimmed.length - trim);
  const leftPoints = usable.map(([y, start]) => [y, start]);
  const rightPoints = usable.map(([y, , end]) => [y, end]);
  const left = lineResidual(leftPoints);
  const right = lineResidual(rightPoints);
  return {
    left,
    right,
    rms: (left.rms + right.rms) * 0.5,
    rows: Math.min(left.rows, right.rows),
  };
}

export function compareEdgeQuality(stencil, shadowMap) {
  const stencilScore = (stencil.left.rms + stencil.right.rms) * 0.5;
  const shadowMapScore = (shadowMap.left.rms + shadowMap.right.rms) * 0.5;
  return {
    stencil,
    shadowMap,
    stencilScore,
    shadowMapScore,
    sharper: stencilScore < shadowMapScore ? "stencil" : "shadowmap",
    improvement: shadowMapScore > 0
      ? (1 - stencilScore / shadowMapScore) * 100
      : 0,
  };
}
