export function buildPath2D(contours) {
  const path = new Path2D();
  for (const contour of contours) {
    const first = contour.start || contour.segments[0]?.p0;
    if (!first) continue;
    path.moveTo(first.x, first.y);
    for (const segment of contour.segments) {
      if (segment.type === "line") {
        path.lineTo(segment.p1.x, segment.p1.y);
      } else if (segment.type === "quad") {
        path.quadraticCurveTo(segment.p1.x, segment.p1.y, segment.p2.x, segment.p2.y);
      } else if (segment.type === "cubic") {
        path.bezierCurveTo(
          segment.p1.x,
          segment.p1.y,
          segment.p2.x,
          segment.p2.y,
          segment.p3.x,
          segment.p3.y,
        );
      }
    }
    if (contour.closed) path.closePath();
  }
  return path;
}

export function drawThumbnail(canvas, specimen, color = "#17282a") {
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);
  context.save();
  const inset = 4;
  const scale = Math.min(width - inset * 2, height - inset * 2);
  context.translate((width - scale) * 0.5, (height - scale) * 0.5);
  context.scale(scale, scale);
  context.fillStyle = color;
  context.fill(buildPath2D(specimen.contours), "evenodd");
  context.restore();
}

export function drawReference(canvas, specimen, options = {}) {
  const {
    background = "#f1eee3",
    ink = "#182b2d",
    showOutlines = false,
    padding = 0.07,
    dpr = window.devicePixelRatio || 1,
  } = options;
  const cssWidth = canvas.clientWidth || 800;
  const cssHeight = canvas.clientHeight || 500;
  const width = Math.max(1, Math.round(cssWidth * dpr));
  const height = Math.max(1, Math.round(cssHeight * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }

  const context = canvas.getContext("2d");
  context.setTransform(1, 0, 0, 1, 0, 0);
  context.fillStyle = background;
  context.fillRect(0, 0, width, height);

  const side = Math.min(width, height) * (1 - padding * 2);
  const left = (width - side) * 0.5;
  const top = (height - side) * 0.5;
  const path = buildPath2D(specimen.contours);

  context.save();
  context.translate(left, top);
  context.scale(side, side);
  context.fillStyle = ink;
  context.fill(path, "evenodd");
  if (showOutlines) {
    context.strokeStyle = "rgba(232, 92, 47, 0.8)";
    context.lineWidth = 0.8 / side;
    context.stroke(path);
  }
  context.restore();

  return { width, height, left, top, side, dpr };
}

export function drawReferenceRaster(
  specimen,
  sizePx,
  shiftX = 0,
  shiftY = 0,
  paddingPx = 3,
  superSample = 4,
) {
  const width = Math.ceil(sizePx) + paddingPx * 2;
  const height = width;
  const canvas = document.createElement("canvas");
  canvas.width = width * superSample;
  canvas.height = height * superSample;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.setTransform(superSample, 0, 0, superSample, 0, 0);
  context.translate(paddingPx + shiftX, paddingPx + shiftY);
  context.scale(sizePx, sizePx);
  context.fillStyle = "#000";
  context.fill(buildPath2D(specimen.contours), "evenodd");

  const image = context.getImageData(0, 0, canvas.width, canvas.height);
  const coverage = new Float32Array(width * height);
  const area = superSample * superSample;

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let alpha = 0;
      for (let sy = 0; sy < superSample; sy += 1) {
        const sourceY = y * superSample + sy;
        for (let sx = 0; sx < superSample; sx += 1) {
          const sourceX = x * superSample + sx;
          alpha += image.data[(sourceY * canvas.width + sourceX) * 4 + 3];
        }
      }
      coverage[y * width + x] = alpha / (area * 255);
    }
  }

  return { coverage, width, height, paddingPx, sizePx, shiftX, shiftY };
}
