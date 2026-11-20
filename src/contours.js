const EPSILON = 1e-9;

function point(x, y) {
  return { x, y };
}

function samePoint(a, b, tolerance = 1e-7) {
  return Math.abs(a.x - b.x) <= tolerance && Math.abs(a.y - b.y) <= tolerance;
}

class ContourBuilder {
  constructor() {
    this.contours = [];
    this.current = null;
  }

  ensureCurrent() {
    if (!this.current) {
      this.current = { segments: [], closed: false, start: null };
      this.contours.push(this.current);
    }
    return this.current;
  }

  moveTo(x, y) {
    this.current = { segments: [], closed: false, start: point(x, y) };
    this.contours.push(this.current);
  }

  lineTo(x, y) {
    const contour = this.ensureCurrent();
    const p0 = contour.start
      ? this.currentPoint() || contour.start
      : point(x, y);
    contour.segments.push({ type: "line", p0, p1: point(x, y) });
  }

  quadTo(cx, cy, x, y) {
    const contour = this.ensureCurrent();
    const p0 = this.currentPoint() || contour.start || point(cx, cy);
    contour.segments.push({
      type: "quad",
      p0,
      p1: point(cx, cy),
      p2: point(x, y),
    });
  }

  cubicTo(c1x, c1y, c2x, c2y, x, y) {
    const contour = this.ensureCurrent();
    const p0 = this.currentPoint() || contour.start || point(c1x, c1y);
    contour.segments.push({
      type: "cubic",
      p0,
      p1: point(c1x, c1y),
      p2: point(c2x, c2y),
      p3: point(x, y),
    });
  }

  close() {
    const contour = this.ensureCurrent();
    contour.closed = true;
    contour.start = contour.start || contour.segments[0]?.p0 || null;
  }

  currentPoint() {
    const segments = this.current?.segments;
    if (!segments?.length) return this.current?.start || null;
    const last = segments[segments.length - 1];
    return last.p3 || last.p2 || last.p1;
  }

  finish() {
    return this.contours.filter((contour) => contour.segments.length > 0);
  }
}

const PATH_TOKEN = /[a-zA-Z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g;

export function parsePathData(pathData) {
  const tokens = pathData.match(PATH_TOKEN) || [];
  const builder = new ContourBuilder();
  let index = 0;
  let command = null;
  let previousCommand = null;
  let lastCubicControl = null;
  let lastQuadControl = null;

  const read = () => Number(tokens[index++]);
  const hasNumber = () => index < tokens.length && !/[a-zA-Z]/.test(tokens[index]);

  while (index < tokens.length) {
    if (/[a-zA-Z]/.test(tokens[index])) {
      command = tokens[index++];
    }

    const relative = command === command.toLowerCase();
    const current = builder.currentPoint() || point(0, 0);
    const dx = relative ? current.x : 0;
    const dy = relative ? current.y : 0;
    const upper = command.toUpperCase();

    if (upper === "Z") {
      builder.close();
      previousCommand = upper;
      command = null;
      continue;
    }

    if (!hasNumber()) continue;

    if (upper === "M") {
      builder.moveTo(read() + dx, read() + dy);
      command = relative ? "l" : "L";
      lastCubicControl = null;
      lastQuadControl = null;
    } else if (upper === "L") {
      builder.lineTo(read() + dx, read() + dy);
      lastCubicControl = null;
      lastQuadControl = null;
    } else if (upper === "H") {
      builder.lineTo(read() + dx, current.y);
      lastCubicControl = null;
      lastQuadControl = null;
    } else if (upper === "V") {
      builder.lineTo(current.x, read() + dy);
      lastCubicControl = null;
      lastQuadControl = null;
    } else if (upper === "C") {
      const c1 = point(read() + dx, read() + dy);
      const c2 = point(read() + dx, read() + dy);
      const end = point(read() + dx, read() + dy);
      builder.cubicTo(c1.x, c1.y, c2.x, c2.y, end.x, end.y);
      lastCubicControl = c2;
      lastQuadControl = null;
    } else if (upper === "S") {
      const reflected =
        previousCommand === "C" || previousCommand === "S"
          ? point(current.x * 2 - lastCubicControl.x, current.y * 2 - lastCubicControl.y)
          : current;
      const c2 = point(read() + dx, read() + dy);
      const end = point(read() + dx, read() + dy);
      builder.cubicTo(reflected.x, reflected.y, c2.x, c2.y, end.x, end.y);
      lastCubicControl = c2;
      lastQuadControl = null;
    } else if (upper === "Q") {
      const c1 = point(read() + dx, read() + dy);
      const end = point(read() + dx, read() + dy);
      builder.quadTo(c1.x, c1.y, end.x, end.y);
      lastQuadControl = c1;
      lastCubicControl = null;
    } else if (upper === "T") {
      const reflected =
        previousCommand === "Q" || previousCommand === "T"
          ? point(current.x * 2 - lastQuadControl.x, current.y * 2 - lastQuadControl.y)
          : current;
      const end = point(read() + dx, read() + dy);
      builder.quadTo(reflected.x, reflected.y, end.x, end.y);
      lastQuadControl = reflected;
      lastCubicControl = null;
    } else {
      index += 1;
    }

    previousCommand = upper;
  }

  return builder.finish();
}

export function contoursFromCommands(commands) {
  const builder = new ContourBuilder();
  for (const command of commands) {
    if (command.type === "M") builder.moveTo(command.x, command.y);
    if (command.type === "L") builder.lineTo(command.x, command.y);
    if (command.type === "Q") builder.quadTo(command.x1, command.y1, command.x, command.y);
    if (command.type === "C") {
      builder.cubicTo(
        command.x1,
        command.y1,
        command.x2,
        command.y2,
        command.x,
        command.y,
      );
    }
    if (command.type === "Z") builder.close();
  }
  return builder.finish();
}

function getRawBounds(contours) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const include = (p) => {
    if (!p) return;
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x);
    maxY = Math.max(maxY, p.y);
  };

  for (const contour of contours) {
    include(contour.start);
    for (const segment of contour.segments) {
      include(segment.p0);
      include(segment.p1);
      include(segment.p2);
      include(segment.p3);
    }
  }

  return { minX, minY, maxX, maxY };
}

function mapPoint(p, transform) {
  return point(
    p.x * transform.scale + transform.offsetX,
    p.y * transform.scale + transform.offsetY,
  );
}

function mapSegment(segment, transform) {
  const mapped = { type: segment.type, p0: mapPoint(segment.p0, transform) };
  if (segment.p1) mapped.p1 = mapPoint(segment.p1, transform);
  if (segment.p2) mapped.p2 = mapPoint(segment.p2, transform);
  if (segment.p3) mapped.p3 = mapPoint(segment.p3, transform);
  return mapped;
}

export function normalizeContours(contours, padding = 0.075) {
  const bounds = getRawBounds(contours);
  const width = Math.max(bounds.maxX - bounds.minX, EPSILON);
  const height = Math.max(bounds.maxY - bounds.minY, EPSILON);
  const available = Math.max(0.1, 1 - padding * 2);
  const scale = Math.min(available / width, available / height);
  const offsetX = (1 - width * scale) / 2 - bounds.minX * scale;
  const offsetY = (1 - height * scale) / 2 - bounds.minY * scale;
  const transform = { scale, offsetX, offsetY, bounds, width, height };

  return {
    contours: contours.map((contour) => ({
      ...contour,
      start: contour.start ? mapPoint(contour.start, transform) : null,
      segments: contour.segments.map((segment) => mapSegment(segment, transform)),
    })),
    transform,
  };
}

export function transformRawPoint(p, transform) {
  return mapPoint(p, transform);
}
