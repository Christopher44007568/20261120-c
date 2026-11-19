const COLORS = {
  cyan: "#66ddff",
  lime: "#c8f56a",
  coral: "#ff8066",
  grid: "rgba(166, 189, 214, 0.10)",
  gridStrong: "rgba(166, 189, 214, 0.18)",
  text: "#4f5a66",
  textBright: "#8f9ca9",
};

function prepare(canvas) {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, rect.width);
  const height = Math.max(1, rect.height);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  return { ctx, width, height };
}

function roundedRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.roundRect(x, y, width, height, r);
}

function drawGlowLine(ctx, points, color, fill = false, width = 1.5) {
  if (!points.length) return;
  ctx.save();
  ctx.beginPath();
  points.forEach(([x, y], index) => {
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  if (fill) {
    ctx.lineTo(points.at(-1)[0], points[0][1]);
    ctx.closePath();
  }
  if (fill) {
    const gradient = ctx.createLinearGradient(0, points[0][1], 0, points.at(-1)[1]);
    gradient.addColorStop(0, color.replace(")", ", 0.16)").replace("rgb", "rgba"));
    gradient.addColorStop(1, color.replace(")", ", 0)").replace("rgb", "rgba"));
    ctx.fillStyle = gradient;
    ctx.fill();
  } else {
    ctx.strokeStyle = color;
    ctx.lineWidth = width + 4;
    ctx.globalAlpha = 0.1;
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.lineWidth = width;
    ctx.stroke();
  }
  ctx.restore();
}

function drawPlotFrame(ctx, width, height, options) {
  const margin = { left: 38, right: 12, top: 13, bottom: 27 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  ctx.save();
  ctx.font = '7px "Forma Mono", "Ubuntu Mono", monospace';
  ctx.fillStyle = COLORS.text;
  ctx.textBaseline = "middle";

  for (let index = 0; index <= 4; index += 1) {
    const y = margin.top + (plotHeight * index) / 4;
    ctx.beginPath();
    ctx.strokeStyle = index === 4 ? COLORS.gridStrong : COLORS.grid;
    ctx.lineWidth = 1;
    ctx.moveTo(margin.left, y + 0.5);
    ctx.lineTo(width - margin.right, y + 0.5);
    ctx.stroke();
  }
  for (let index = 0; index < options.xLabels.length; index += 1) {
    const x = margin.left + (plotWidth * index) / Math.max(1, options.xLabels.length - 1);
    ctx.textAlign = index === 0 ? "left" : index === options.xLabels.length - 1 ? "right" : "center";
    ctx.fillText(options.xLabels[index], x, height - 9);
  }
  ctx.textAlign = "right";
  for (let index = 0; index <= 4; index += 1) {
    const y = margin.top + (plotHeight * index) / 4;
    const value = options.yMax - ((options.yMax - options.yMin) * index) / 4;
    ctx.fillText(options.formatY(value), margin.left - 7, y);
  }
  if (options.yLabel) {
    ctx.save();
    ctx.translate(9, margin.top + plotHeight / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(79, 90, 102, 0.8)";
    ctx.fillText(options.yLabel, 0, 0);
    ctx.restore();
  }
  ctx.restore();
  return { margin, plotWidth, plotHeight };
}

function mapPoints(values, frame, yMin, yMax) {
  return values.map((value, index) => [
    frame.margin.left + (frame.plotWidth * index) / Math.max(1, values.length - 1),
    frame.margin.top + ((yMax - value) / (yMax - yMin)) * frame.plotHeight,
  ]);
}

export function drawVolumeChart(canvas, rows) {
  const { ctx, width, height } = prepare(canvas);
  const yMin = 97.5;
  const yMax = 101;
  const frame = drawPlotFrame(ctx, width, height, {
    yMin,
    yMax,
    xLabels: rows.map((row) => `${row.iterations}`),
    formatY: (value) => value.toFixed(1),
    yLabel: "%",
  });
  const referenceY = frame.margin.top + ((yMax - 100) / (yMax - yMin)) * frame.plotHeight;
  ctx.save();
  ctx.setLineDash([3, 4]);
  ctx.strokeStyle = "rgba(238, 243, 245, 0.2)";
  ctx.beginPath();
  ctx.moveTo(frame.margin.left, referenceY);
  ctx.lineTo(width - frame.margin.right, referenceY);
  ctx.stroke();
  ctx.restore();

  const compress = mapPoints(rows.map((row) => row.compressVolume), frame, yMin, yMax);
  const stretch = mapPoints(rows.map((row) => row.stretchVolume), frame, yMin, yMax);
  drawGlowLine(ctx, compress, COLORS.cyan, false, 1.7);
  drawGlowLine(ctx, stretch, COLORS.coral, false, 1.7);
  for (const points of [compress, stretch]) {
    for (const [x, y] of points) {
      ctx.beginPath();
      ctx.fillStyle = "#0d131b";
      ctx.arc(x, y, 2.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = points === compress ? COLORS.cyan : COLORS.coral;
      ctx.stroke();
    }
  }
  const last = rows.at(-1);
  ctx.font = '7px "Forma Mono", monospace';
  ctx.textAlign = "right";
  ctx.fillStyle = COLORS.cyan;
  ctx.fillText(`${last.compressVolume.toFixed(2)}%`, width - 13, compress.at(-1)[1] - 7);
  ctx.fillStyle = COLORS.coral;
  ctx.fillText(`${last.stretchVolume.toFixed(2)}%`, width - 13, stretch.at(-1)[1] + 13);
}

export function drawErrorChart(canvas, rows) {
  const { ctx, width, height } = prepare(canvas);
  const maxError = Math.max(...rows.map((row) => row.vertexError), 0.2);
  const yMax = Math.ceil(maxError * 10) / 10;
  const yMin = 0;
  const frame = drawPlotFrame(ctx, width, height, {
    yMin,
    yMax,
    xLabels: rows.map((row) => `${row.iterations}`),
    formatY: (value) => value.toFixed(1),
    yLabel: "mm",
  });
  const values = rows.map((row) => row.vertexError);
  const points = mapPoints(values, frame, yMin, yMax);
  const gradient = ctx.createLinearGradient(0, frame.margin.top, 0, height - frame.margin.bottom);
  gradient.addColorStop(0, "rgba(102, 221, 255, 0.16)");
  gradient.addColorStop(1, "rgba(102, 221, 255, 0)");
  ctx.beginPath();
  points.forEach(([x, y], index) => {
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineTo(points.at(-1)[0], height - frame.margin.bottom);
  ctx.lineTo(points[0][0], height - frame.margin.bottom);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();
  drawGlowLine(ctx, points, COLORS.cyan, false, 1.7);
  for (let index = 0; index < points.length; index += 1) {
    const [x, y] = points[index];
    ctx.beginPath();
    ctx.fillStyle = index === points.length - 1 ? COLORS.lime : "#0d131b";
    ctx.arc(x, y, 2.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = index === points.length - 1 ? COLORS.lime : COLORS.cyan;
    ctx.lineWidth = 1;
    ctx.stroke();
  }
  ctx.font = '7px "Forma Mono", monospace';
  ctx.textAlign = "right";
  ctx.fillStyle = COLORS.textBright;
  ctx.fillText(`${values[0].toFixed(2)} mm`, frame.margin.left + frame.plotWidth - 4, points[0][1] + 12);
  ctx.fillStyle = COLORS.lime;
  ctx.fillText("0.00 mm", width - 16, points.at(-1)[1] - 8);
}

export function drawSpectrumChart(canvas, spectrum) {
  const { ctx, width, height } = prepare(canvas);
  const margin = { left: 33, right: 10, top: 12, bottom: 28 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const wavelengths = spectrum.wavelengths;
  const xAt = (index) => margin.left + (plotWidth * index) / (wavelengths.length - 1);
  const yAt = (value) => margin.top + (1 - value) * plotHeight;

  ctx.save();
  ctx.font = '6px "Forma Mono", monospace';
  ctx.fillStyle = COLORS.text;
  ctx.textBaseline = "middle";
  for (let index = 0; index <= 4; index += 1) {
    const y = margin.top + (plotHeight * index) / 4;
    ctx.beginPath();
    ctx.strokeStyle = COLORS.grid;
    ctx.moveTo(margin.left, y + 0.5);
    ctx.lineTo(width - margin.right, y + 0.5);
    ctx.stroke();
    ctx.textAlign = "right";
    ctx.fillText((1 - index / 4).toFixed(1), margin.left - 5, y);
  }
  ctx.setLineDash([3, 4]);
  ctx.strokeStyle = "rgba(238, 243, 245, 0.2)";
  ctx.beginPath();
  ctx.moveTo(margin.left, yAt(1));
  ctx.lineTo(width - margin.right, yAt(1));
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();

  const series = [
    [spectrum.reflectances, COLORS.cyan],
    [spectrum.transmissions, COLORS.lime],
    [spectrum.absorptions, COLORS.coral],
  ];
  for (const [values, color] of series) {
    const points = values.map((value, index) => [xAt(index), yAt(value)]);
    drawGlowLine(ctx, points, color, false, 1.35);
  }

  const stripY = height - 22;
  const stripHeight = 4;
  const gradient = ctx.createLinearGradient(margin.left, 0, width - margin.right, 0);
  for (const [stop, color] of [
    [0, "#3d2dcc"], [0.1, "#167cff"], [0.25, "#19d5bd"], [0.4, "#b8ed4d"],
    [0.58, "#ffb536"], [0.78, "#ff4b38"], [1, "#8c1d38"],
  ]) gradient.addColorStop(stop, color);
  ctx.globalAlpha = 0.7;
  ctx.fillStyle = gradient;
  ctx.fillRect(margin.left, stripY, plotWidth, stripHeight);
  ctx.globalAlpha = 1;

  const highlightIndex = Math.max(0, Math.min(
    wavelengths.length - 1,
    Math.round((560 - wavelengths[0]) / 5),
  ));
  const hx = xAt(highlightIndex);
  ctx.save();
  ctx.setLineDash([2, 3]);
  ctx.strokeStyle = "rgba(200, 245, 106, 0.28)";
  ctx.beginPath();
  ctx.moveTo(hx, margin.top);
  ctx.lineTo(hx, margin.top + plotHeight);
  ctx.stroke();
  ctx.restore();

  ctx.font = '6px "Forma Mono", monospace';
  ctx.fillStyle = COLORS.text;
  ctx.textBaseline = "alphabetic";
  const xLabels = [380, 480, 580, 680, 780];
  for (const wavelength of xLabels) {
    const index = (wavelength - wavelengths[0]) / 5;
    const x = xAt(index);
    ctx.textAlign = wavelength === 380 ? "left" : wavelength === 780 ? "right" : "center";
    ctx.fillText(wavelength, x, height - 7);
  }
}

export function drawColorChart(canvas, response) {
  const { ctx, width, height } = prepare(canvas);
  const margin = { left: 27, right: 10, top: 12, bottom: 23 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const xAt = (index) => margin.left + (plotWidth * index) / (response.length - 1);
  const yAt = (value) => margin.top + (1 - value) * plotHeight;

  ctx.save();
  ctx.font = '6px "Forma Mono", monospace';
  ctx.fillStyle = COLORS.text;
  ctx.textBaseline = "middle";
  for (let index = 0; index <= 4; index += 1) {
    const y = margin.top + (plotHeight * index) / 4;
    ctx.beginPath();
    ctx.strokeStyle = COLORS.grid;
    ctx.moveTo(margin.left, y + 0.5);
    ctx.lineTo(width - margin.right, y + 0.5);
    ctx.stroke();
    ctx.textAlign = "right";
    ctx.fillText((1 - index / 4).toFixed(1), margin.left - 4, y);
  }
  const angleLabels = [0, 30, 60];
  for (const angle of angleLabels) {
    const index = Math.round(angle / 5);
    ctx.textAlign = "center";
    ctx.fillStyle = COLORS.text;
    ctx.fillText(`${angle}°`, xAt(index), height - 6);
  }
  ctx.restore();

  const channels = [
    ["R", 0, "#ff8066"],
    ["G", 1, "#c8f56a"],
    ["B", 2, "#66ddff"],
  ];
  for (const [, channel, color] of channels) {
    const points = response.map((entry, index) => [xAt(index), yAt(entry.rgb[channel])]);
    drawGlowLine(ctx, points, color, false, 1.15);
  }
  ctx.font = '6px "Forma Mono", monospace';
  ctx.textAlign = "right";
  ctx.fillStyle = COLORS.textBright;
  ctx.fillText("CHANNEL", width - 10, margin.top + 7);
}

function ray(ctx, x1, y1, x2, y2, color, width = 1, dash = 0) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.shadowColor = color;
  ctx.shadowBlur = 8;
  if (dash) ctx.setLineDash([3, 4]);
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  ctx.restore();
}

function arrowHead(ctx, x, y, angle, color) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(5, 0);
  ctx.lineTo(-3, -2.4);
  ctx.lineTo(-3, 2.4);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

export function drawPaintCrossSection(canvas, spectrum, preset, time = 0) {
  const { ctx, width, height } = prepare(canvas);
  const layerTop = height * 0.39;
  const clearHeight = Math.max(31, height * 0.095);
  const baseHeight = Math.max(23, height * 0.07);
  const primerHeight = Math.max(18, height * 0.052);
  const left = width * 0.13;
  const right = width * 0.83;
  const bandWidth = right - left;

  ctx.save();
  ctx.strokeStyle = "rgba(166, 189, 214, 0.12)";
  ctx.lineWidth = 1;
  for (let i = 0; i < 6; i += 1) {
    const y = layerTop + clearHeight + baseHeight + primerHeight + i * 16;
    ctx.beginPath();
    ctx.moveTo(left - 30, y);
    ctx.lineTo(right + 28, y);
    ctx.stroke();
  }
  ctx.restore();

  const clearGradient = ctx.createLinearGradient(0, layerTop, 0, layerTop + clearHeight);
  clearGradient.addColorStop(0, "rgba(210, 250, 255, 0.2)");
  clearGradient.addColorStop(0.45, "rgba(93, 179, 204, 0.13)");
  clearGradient.addColorStop(1, "rgba(30, 82, 119, 0.16)");
  ctx.fillStyle = clearGradient;
  ctx.fillRect(left, layerTop, bandWidth, clearHeight);

  const baseGradient = ctx.createLinearGradient(left, 0, right, 0);
  baseGradient.addColorStop(0, "#0a1735");
  baseGradient.addColorStop(0.25, spectrum.hex);
  baseGradient.addColorStop(0.46, "#08122b");
  baseGradient.addColorStop(0.7, spectrum.hex);
  baseGradient.addColorStop(1, "#09101e");
  ctx.fillStyle = baseGradient;
  ctx.fillRect(left, layerTop + clearHeight, bandWidth, baseHeight);

  ctx.fillStyle = "#4e5861";
  ctx.fillRect(left, layerTop + clearHeight + baseHeight, bandWidth, primerHeight);
  ctx.fillStyle = "#151b22";
  ctx.fillRect(
    left,
    layerTop + clearHeight + baseHeight + primerHeight,
    bandWidth,
    height * 0.035,
  );

  ctx.save();
  ctx.beginPath();
  ctx.rect(left, layerTop + clearHeight, bandWidth, baseHeight);
  ctx.clip();
  for (let i = 0; i < 58; i += 1) {
    const x = left + ((i * 83.7) % bandWidth);
    const y = layerTop + clearHeight + 3 + ((i * 31.3) % (baseHeight - 5));
    const shimmer = 0.26 + 0.74 * Math.abs(Math.sin(time * 0.0007 + i * 0.9));
    ctx.fillStyle = `rgba(235, 249, 255, ${0.1 + shimmer * 0.34})`;
    ctx.fillRect(x, y, i % 4 === 0 ? 2 : 1, 1);
  }
  ctx.restore();

  ctx.save();
  ctx.strokeStyle = "rgba(220, 245, 255, 0.35)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(left, layerTop);
  ctx.lineTo(right, layerTop);
  ctx.stroke();
  ctx.restore();

  const hitX = width * 0.5;
  const hitY = layerTop;
  const incoming = Math.max(0.24, 0.58 - spectrum.angle * 0.0035);
  const inX = hitX - width * incoming;
  const inY = hitY - width * 0.34;
  ray(ctx, inX, inY, hitX, hitY, "rgba(238, 247, 255, 0.9)", 1.6);
  arrowHead(ctx, hitX - 17, hitY - 14, Math.atan2(hitY - inY, hitX - inX), "#eef7ff");

  const surfaceStrength = spectrum.totals.surface;
  const firstStrength = spectrum.totals.firstBounce;
  const multiStrength = spectrum.totals.multiple;
  const outX = hitX + width * 0.3;
  const outY = hitY - width * 0.32;
  ray(ctx, hitX, hitY, outX, outY, `rgba(102, 221, 255, ${0.35 + surfaceStrength})`, 1.1);
  ray(ctx, hitX + 4, hitY - 2, outX + 18, outY - 18, `rgba(200, 245, 106, ${0.3 + firstStrength * 2})`, 1.3);
  ray(ctx, hitX + 8, hitY - 3, outX + 34, outY - 31, `rgba(255, 255, 255, ${0.16 + multiStrength * 3})`, 0.8);
  arrowHead(ctx, outX + 34, outY - 31, Math.atan2(outY - hitY, outX - hitX), "rgba(200, 245, 106, 0.8)");

  const insideY = layerTop + clearHeight;
  ray(ctx, hitX, hitY, hitX + 23, insideY, "rgba(255, 255, 255, 0.55)", 1, 3);
  ray(ctx, hitX + 23, insideY, hitX + 46, layerTop + clearHeight - 10, "rgba(255, 255, 255, 0.42)", 0.9, 3);
  ray(ctx, hitX + 46, layerTop + clearHeight - 10, hitX + 68, layerTop + 6, "rgba(255, 255, 255, 0.3)", 0.8, 3);
  ray(ctx, hitX, insideY, hitX + 72, insideY, `rgba(102, 221, 255, ${0.24 + surfaceStrength})`, 0.9);
  ray(ctx, hitX + 72, insideY, hitX + 88, layerTop - 4, `rgba(102, 221, 255, ${0.18 + surfaceStrength * 0.8})`, 0.8);

  ctx.font = '7px "Forma Mono", monospace';
  ctx.fillStyle = "rgba(143, 156, 169, 0.85)";
  ctx.fillText("INCIDENT", inX + 2, inY - 6);
  ctx.fillStyle = COLORS.cyan;
  ctx.fillText("SPECULAR", outX - 4, outY - 8);
  ctx.fillStyle = COLORS.lime;
  ctx.fillText("METAL BOUNCE", outX + 12, outY + 2);

  const labelX = right + 7;
  ctx.font = '6px "Forma Mono", monospace';
  const labels = [
    ["CLEAR", layerTop + clearHeight / 2, "45µm"],
    ["BASE", layerTop + clearHeight + baseHeight / 2, "18µm"],
    ["PRIMER", layerTop + clearHeight + baseHeight + primerHeight / 2, "25µm"],
  ];
  for (const [label, y, thickness] of labels) {
    ctx.fillStyle = "rgba(200, 220, 232, 0.58)";
    ctx.fillText(label, labelX, y - 1);
    ctx.fillStyle = COLORS.text;
    ctx.fillText(thickness, labelX, y + 7);
  }

  const pulse = 0.5 + Math.sin(time * 0.002) * 0.5;
  ctx.beginPath();
  ctx.fillStyle = `rgba(200, 245, 106, ${0.3 + pulse * 0.6})`;
  ctx.arc(hitX, hitY, 2.2, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.strokeStyle = `rgba(200, 245, 106, ${0.18 + pulse * 0.16})`;
  ctx.arc(hitX, hitY, 6 + pulse * 4, 0, Math.PI * 2);
  ctx.stroke();

  ctx.strokeStyle = "rgba(102, 221, 255, 0.28)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(left - 10, layerTop);
  ctx.lineTo(left - 10, layerTop + clearHeight + baseHeight + primerHeight);
  ctx.stroke();
  for (const y of [
    layerTop,
    layerTop + clearHeight,
    layerTop + clearHeight + baseHeight,
    layerTop + clearHeight + baseHeight + primerHeight,
  ]) {
    ctx.beginPath();
    ctx.moveTo(left - 14, y);
    ctx.lineTo(left - 6, y);
    ctx.stroke();
  }
}
