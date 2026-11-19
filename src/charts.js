import { TAU, clamp } from "./math.js";

const FONT = '11px "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif';
const SMALL_FONT = '10px "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif';

export const CHART_COLORS = {
  amber: "#f0b45f",
  teal: "#58c9c1",
  blue: "#6f9dff",
  rose: "#e7869b",
  text: "#d9dfeb",
  muted: "#7f899d",
  grid: "#2a3040",
};

export function prepareCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(320, Math.round(rect.width || canvas.clientWidth || 640));
  const height = Math.max(120, Math.round(rect.height || canvas.clientHeight || 240));
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width, height };
}

function drawPlotFrame(ctx, box, xTicks, yTicks, options) {
  const { left, top, right, bottom } = box;
  ctx.save();
  ctx.strokeStyle = CHART_COLORS.grid;
  ctx.lineWidth = 1;
  ctx.font = SMALL_FONT;
  ctx.fillStyle = CHART_COLORS.muted;
  for (const tick of xTicks) {
    const x = left + (right - left) * tick.position;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
    ctx.textAlign = "center";
    ctx.fillText(tick.label, x, bottom + 15);
  }
  for (const tick of yTicks) {
    const y = bottom - (bottom - top) * tick.position;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();
    ctx.textAlign = "right";
    ctx.fillText(tick.label, left - 8, y + 3);
  }
  if (options.xlabel) {
    ctx.textAlign = "right";
    ctx.fillText(options.xlabel, right, bottom + 30);
  }
  if (options.ylabel) {
    ctx.save();
    ctx.translate(11, top);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "right";
    ctx.fillText(options.ylabel, 0, 0);
    ctx.restore();
  }
  ctx.restore();
}

export function drawSeriesChart(canvas, {
  series,
  xLabel = "",
  yLabel = "",
  xMin = 0,
  xMax = 1,
  yMin,
  yMax,
  markers = [],
  xTicks = [0, 0.25, 0.5, 0.75, 1],
  yTickCount = 5,
} = {}) {
  const { ctx, width, height } = prepareCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const box = { left: 46, top: 22, right: width - 16, bottom: height - 34 };
  const allY = series.flatMap((entry) => entry.points.map((point) => point[1]));
  const low = yMin ?? Math.min(...allY);
  const high = yMax ?? Math.max(...allY);
  const span = Math.max(high - low, 1e-9);
  const xScale = (x) => box.left + (box.right - box.left) * ((x - xMin) / (xMax - xMin));
  const yScale = (y) => box.bottom - (box.bottom - box.top) * ((y - low) / span);
  const xTickData = xTicks.map((value) => ({
    position: (value - xMin) / (xMax - xMin),
    label: Number.isInteger(value) ? String(value) : value.toFixed(2),
  }));
  const yTickData = [];
  for (let i = 0; i < yTickCount; i += 1) {
    const position = i / (yTickCount - 1);
    yTickData.push({ position, label: (low + span * position).toFixed(2) });
  }
  drawPlotFrame(ctx, box, xTickData, yTickData, { xlabel: xLabel, ylabel: yLabel });

  for (const marker of markers) {
    const x = xScale(marker.value);
    ctx.save();
    ctx.setLineDash([3, 4]);
    ctx.strokeStyle = "rgba(240,180,95,.32)";
    ctx.beginPath();
    ctx.moveTo(x, box.top);
    ctx.lineTo(x, box.bottom);
    ctx.stroke();
    ctx.restore();
  }

  for (const entry of series) {
    if (!entry.points.length) continue;
    ctx.save();
    ctx.strokeStyle = entry.color;
    ctx.lineWidth = entry.width ?? 1.7;
    ctx.beginPath();
    entry.points.forEach(([x, y], index) => {
      const px = xScale(x);
      const py = yScale(y);
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();
    ctx.restore();
  }

  let legendX = box.left + 4;
  for (const entry of series) {
    ctx.fillStyle = entry.color;
    ctx.fillRect(legendX, 7, 14, 3);
    ctx.fillStyle = CHART_COLORS.text;
    ctx.font = SMALL_FONT;
    ctx.fillText(entry.label, legendX + 19, 10);
    legendX += ctx.measureText(entry.label).width + 38;
  }
}

export function drawErrorChart(canvas, series, sampleCounts, analytic) {
  const { ctx, width, height } = prepareCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const box = { left: 54, top: 24, right: width - 16, bottom: height - 40 };
  const values = series.flatMap((entry) => entry.points.map((point) => point[1]));
  const low = Math.max(1e-7, Math.min(...values) * 0.75);
  const high = Math.max(low * 10, Math.max(...values) * 1.25);
  const logMin = Math.log10(low);
  const logMax = Math.log10(high);
  const xMin = Math.log2(Math.min(...sampleCounts));
  const xMax = Math.log2(Math.max(...sampleCounts));
  const xScale = (value) =>
    box.left + (box.right - box.left) * ((Math.log2(value) - xMin) / (xMax - xMin));
  const yScale = (value) =>
    box.bottom - (box.bottom - box.top) *
    ((Math.log10(Math.max(value, low)) - logMin) / (logMax - logMin));

  const xTicks = sampleCounts
    .filter((count) => count === 1 || count === 4 || count === 16 || count === 64 || count === 256 || count === 1024)
    .map((count) => ({
      position: (Math.log2(count) - xMin) / (xMax - xMin),
      label: `${count}`,
    }));
  const yTicks = [];
  for (let decade = Math.ceil(logMin); decade <= Math.floor(logMax); decade += 1) {
    const value = 10 ** decade;
    yTicks.push({
      position: (decade - logMin) / (logMax - logMin),
      label: `${value >= 0.01 ? (value * 100).toFixed(0) + "%" : value.toExponential(0)}`,
    });
  }
  drawPlotFrame(ctx, box, xTicks, yTicks, { xlabel: "spp（对数）", ylabel: "相对亮度误差" });

  for (const entry of series) {
    ctx.save();
    ctx.strokeStyle = entry.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    entry.points.forEach(([x, y], index) => {
      const px = xScale(x);
      const py = yScale(y);
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();
    for (const [x, y] of entry.points) {
      ctx.fillStyle = entry.color;
      ctx.beginPath();
      ctx.arc(xScale(x), yScale(y), 2.6, 0, TAU);
      ctx.fill();
    }
    ctx.restore();
  }

  let legendX = box.left;
  ctx.font = SMALL_FONT;
  for (const entry of series) {
    ctx.fillStyle = entry.color;
    ctx.fillRect(legendX, 8, 14, 3);
    ctx.fillStyle = CHART_COLORS.text;
    ctx.fillText(entry.label, legendX + 19, 11);
    legendX += ctx.measureText(entry.label).width + 42;
  }
  ctx.fillStyle = CHART_COLORS.muted;
  ctx.textAlign = "right";
  ctx.fillText(`解析值 ${analytic.toFixed(5)}`, box.right, height - 8);
}

export function drawDirectionQuadrants(canvas, directionSets) {
  const { ctx, width, height } = prepareCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const columns = 2;
  const rows = Math.ceil(directionSets.length / columns);
  const cellW = width / columns;
  const cellH = (height - 8) / rows;
  const colors = [CHART_COLORS.teal, CHART_COLORS.blue, CHART_COLORS.amber, CHART_COLORS.rose];

  directionSets.forEach((entry, index) => {
    const col = index % columns;
    const row = Math.floor(index / columns);
    const cx = col * cellW + cellW / 2;
    const cy = row * cellH + cellH / 2 + 4;
    const radius = Math.min(cellW, cellH) * 0.37;
    ctx.save();
    ctx.strokeStyle = CHART_COLORS.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, TAU);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 0.5, 0, TAU);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx - radius, cy);
    ctx.lineTo(cx + radius, cy);
    ctx.moveTo(cx, cy - radius);
    ctx.lineTo(cx, cy + radius);
    ctx.stroke();
    ctx.fillStyle = colors[index % colors.length];
    for (const direction of entry.directions) {
      const x = cx + direction[0] * radius;
      const y = cy - direction[1] * radius;
      ctx.globalAlpha = 0.24 + 0.55 * clamp(direction[2], 0, 1);
      ctx.beginPath();
      ctx.arc(x, y, 1.1, 0, TAU);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.fillStyle = CHART_COLORS.text;
    ctx.font = SMALL_FONT;
    ctx.textAlign = "left";
    ctx.fillText(`α ${entry.roughness.toFixed(2)}`, col * cellW + 10, row * cellH + 14);
    ctx.restore();
  });
}

export function drawMesh(canvas, edges, valid) {
  const { ctx, width, height } = prepareCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const color = valid ? "#6fd1a1" : "#e37b72";
  ctx.save();
  ctx.strokeStyle = color;
  ctx.globalAlpha = 0.72;
  ctx.lineWidth = 1;
  for (const [a, b] of edges) {
    ctx.beginPath();
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
  ctx.fillStyle = color;
  for (const [a] of edges) {
    ctx.beginPath();
    ctx.arc(a[0], a[1], 1.6, 0, TAU);
    ctx.fill();
  }
  ctx.restore();
}

export function drawBoundaryStrip(canvas, continuity) {
  const { ctx, width, height } = prepareCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const left = 66;
  const right = width - 18;
  const top = 30;
  const rowGap = Math.max(22, (height - top - 32) / continuity.rows.length);
  const barH = 9;
  const maxLog = Math.log10(Math.max(continuity.maxQuantizedJump * 2, 1e-7));
  const minLog = -6;
  ctx.font = SMALL_FONT;
  continuity.rows.forEach((row, index) => {
    const y = top + index * rowGap;
    ctx.fillStyle = CHART_COLORS.muted;
    ctx.textAlign = "right";
    ctx.fillText(`r=${row.roughness.toFixed(2)}`, left - 8, y + 7);
    const fraction = clamp(
      (Math.log10(Math.max(row.continuousJump, 1e-7)) - minLog) / (maxLog - minLog),
      0,
      1,
    );
    ctx.fillStyle = CHART_COLORS.teal;
    ctx.fillRect(left, y, Math.max(2, (right - left) * fraction), barH);
    ctx.fillStyle = CHART_COLORS.text;
    ctx.textAlign = "left";
    ctx.fillText(formatSmallPercent(row.continuousJump), left + (right - left) * fraction + 7, y + 7);
  });
  const quantizedX = left + (right - left) * clamp(
    (Math.log10(Math.max(continuity.maxQuantizedJump, 1e-7)) - minLog) / (maxLog - minLog),
    0,
    1,
  );
  ctx.save();
  ctx.setLineDash([4, 4]);
  ctx.strokeStyle = CHART_COLORS.rose;
  ctx.beginPath();
  ctx.moveTo(quantizedX, top - 10);
  ctx.lineTo(quantizedX, height - 24);
  ctx.stroke();
  ctx.restore();
  ctx.fillStyle = CHART_COLORS.rose;
  ctx.textAlign = "left";
  ctx.fillText(`量化反例 ${formatSmallPercent(continuity.maxQuantizedJump)}`, Math.min(quantizedX + 6, right - 84), height - 22);
  ctx.fillStyle = CHART_COLORS.muted;
  ctx.fillText("青条 = 双线性连续跳变（对数轴）", left, height - 5);
}

function formatSmallPercent(value) {
  const percent = value * 100;
  if (percent < 0.01) return `${percent.toFixed(4)}%`;
  if (percent < 1) return `${percent.toFixed(3)}%`;
  return `${percent.toFixed(1)}%`;
}
