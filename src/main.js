import {
  UP,
  clampIrradiance,
  evaluateIrradiance,
  luminance,
} from "./sh.js";
import { ProbeGrid } from "./probe-grid.js";
import { DynamicProbeSimulation } from "./simulation.js";

const $ = (id) => document.getElementById(id);
const elements = {
  scene: $("sceneCanvas"),
  history: $("historyCanvas"),
  modePill: $("modePill"),
  modeButtons: [...document.querySelectorAll("[data-mode]")],
  strategyNote: $("strategyNote"),
  interval: $("intervalInput"),
  intervalLabel: $("intervalLabel"),
  speed: $("speedInput"),
  speedLabel: $("speedLabel"),
  smoothing: $("smoothingInput"),
  smoothingLabel: $("smoothingLabel"),
  play: $("playButton"),
  reset: $("resetButton"),
  export: $("exportButton"),
  fps: $("fpsLabel"),
  updateMetric: $("updateMetric"),
  interpolationMetric: $("interpolationMetric"),
  totalMetric: $("totalMetric"),
  p95Metric: $("p95Metric"),
  budgetBar: $("budgetBar"),
  budgetText: $("budgetText"),
  boundaryCount: $("boundaryCount"),
  boundaryJump: $("boundaryJump"),
  meanError: $("meanError"),
  updateCount: $("updateCount"),
  continuityBadge: $("continuityBadge"),
  selectedProbeLabel: $("selectedProbeLabel"),
  selectedLuminance: $("selectedLuminance"),
  selectedError: $("selectedError"),
  coefficientGrid: $("coefficientGrid"),
  trajectoryTime: $("trajectoryTime"),
  compareTable: $("compareTable"),
  benchmarkStatus: $("benchmarkStatus"),
  rebuildRatio: $("rebuildRatio"),
  totalRatio: $("totalRatio"),
  frequencyBody: document.querySelector("#frequencyTable tbody"),
  probeBody: document.querySelector("#probeTable tbody"),
  probeSummary: $("probeSummary"),
};

const SH_NAMES = ["c00", "c1m1", "c10", "c11", "c2m2", "c2m1", "c20", "c21", "c22"];
const CHANNELS = ["R", "G", "B"];
const heatCanvas = document.createElement("canvas");
const heatContext = heatCanvas.getContext("2d", { willReadFrequently: false });
const heatWidth = 88;
const heatHeight = 62;
heatCanvas.width = heatWidth;
heatCanvas.height = heatHeight;
const heatImage = heatContext.createImageData(heatWidth, heatHeight);
const sampleCoefficients = new Float64Array(27);
const samplePosition = new Float64Array(3);
const sampleRgb = new Float64Array(3);
const probeRgb = new Float64Array(3);
const sampleBasis = new Float64Array(9);
const trail = [];

let simulation;
let selectedProbe = 0;
let probeRows = [];
let playing = true;
let lastFrameTime = performance.now();
let lastUiTime = 0;
let lastProbeRefresh = 0;
let frameCounter = 0;
let fpsEma = 60;
let currentMode = "ondemand";

function createSimulation() {
  const grid = new ProbeGrid({ cols: 14, rows: 10, spacing: 1 });
  simulation = new DynamicProbeSimulation({
    grid,
    mode: currentMode,
    intervalMs: Number(elements.interval.value),
    smoothingTau: Number(elements.smoothing.value) / 1000,
    speed: Number(elements.speed.value) / 100,
    lightCount: 1,
    qualityStride: 10,
  });
  selectedProbe = Math.floor(grid.rows / 2) * grid.cols + Math.floor(grid.cols / 2);
  probeRows = [];
  trail.length = 0;
  elements.play.textContent = "Ⅱ";
  playing = true;
}

function fitCanvas(canvas) {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const width = Math.max(1, Math.round(canvas.clientWidth * dpr));
  const height = Math.max(1, Math.round(canvas.clientHeight * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const context = canvas.getContext("2d");
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  return {
    context,
    width: canvas.clientWidth,
    height: canvas.clientHeight,
  };
}

function sceneViewport() {
  const width = elements.scene.clientWidth;
  const height = elements.scene.clientHeight;
  const grid = simulation.grid;
  const margin = Math.max(30, Math.min(width, height) * 0.055);
  const gridWidth = Math.max(1, (grid.cols - 1) * grid.spacing);
  const gridDepth = Math.max(1, (grid.rows - 1) * grid.spacing);
  const scale = Math.min(
    (width - margin * 2) / gridWidth,
    (height - margin * 2) / gridDepth,
  );
  return {
    width,
    height,
    scale,
    centerX: width / 2,
    centerY: height / 2,
    mapX: (x) => width / 2 + x * scale,
    mapZ: (z) => height / 2 + z * scale,
  };
}

function displayColor(rgb, exposure = 2.1, alpha = 1) {
  const r = Math.round(255 * (1 - Math.exp(-Math.max(0, rgb[0]) * exposure)));
  const g = Math.round(255 * (1 - Math.exp(-Math.max(0, rgb[1]) * exposure)));
  const b = Math.round(255 * (1 - Math.exp(-Math.max(0, rgb[2]) * exposure)));
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function updateHeatImage() {
  const grid = simulation.grid;
  const padding = grid.spacing * 0.5;
  const minX = grid.minX - padding;
  const maxX = grid.minX + (grid.cols - 1) * grid.spacing + padding;
  const minZ = grid.minZ - padding;
  const maxZ = grid.minZ + (grid.rows - 1) * grid.spacing + padding;
  const pixels = heatImage.data;
  let offset = 0;
  for (let py = 0; py < heatHeight; py += 1) {
    samplePosition[2] = minZ + (py / (heatHeight - 1)) * (maxZ - minZ);
    for (let px = 0; px < heatWidth; px += 1) {
      samplePosition[0] = minX + (px / (heatWidth - 1)) * (maxX - minX);
      samplePosition[1] = grid.y;
      grid.sampleCoefficients(samplePosition, sampleCoefficients);
      evaluateIrradiance(sampleCoefficients, UP, sampleRgb, sampleBasis);
      clampIrradiance(sampleRgb);
      pixels[offset] = 255 * (1 - Math.exp(-sampleRgb[0] * 2.15)) + 3;
      pixels[offset + 1] = 255 * (1 - Math.exp(-sampleRgb[1] * 2.15)) + 4;
      pixels[offset + 2] = 255 * (1 - Math.exp(-sampleRgb[2] * 2.15)) + 6;
      pixels[offset + 3] = 255;
      offset += 4;
    }
  }
  heatContext.putImageData(heatImage, 0, 0);
}

function drawBackground(context, width, height) {
  context.clearRect(0, 0, width, height);
  const gradient = context.createRadialGradient(
    width * 0.5,
    height * 0.43,
    20,
    width * 0.5,
    height * 0.43,
    Math.max(width, height) * 0.62,
  );
  gradient.addColorStop(0, "#0c121b");
  gradient.addColorStop(1, "#070a0f");
  context.fillStyle = gradient;
  context.fillRect(0, 0, width, height);
}

function drawGrid(context, viewport) {
  const grid = simulation.grid;
  context.lineWidth = 1;
  context.strokeStyle = "rgba(160, 190, 220, 0.055)";
  context.beginPath();
  for (let col = 0; col < grid.cols; col += 1) {
    const x = viewport.mapX(grid.minX + col * grid.spacing);
    context.moveTo(x, viewport.mapZ(grid.minZ));
    context.lineTo(x, viewport.mapZ(grid.minZ + (grid.rows - 1) * grid.spacing));
  }
  for (let row = 0; row < grid.rows; row += 1) {
    const z = viewport.mapZ(grid.minZ + row * grid.spacing);
    context.moveTo(viewport.mapX(grid.minX), z);
    context.lineTo(viewport.mapX(grid.minX + (grid.cols - 1) * grid.spacing), z);
  }
  context.stroke();
}

function drawProbes(context, viewport) {
  const grid = simulation.grid;
  for (let probe = 0; probe < grid.count; probe += 1) {
    const offset = probe * 3;
    const x = viewport.mapX(grid.positions[offset]);
    const z = viewport.mapZ(grid.positions[offset + 2]);
    const coefficientOffset = probe * 27;
    const coefficients = grid.display.subarray(
      coefficientOffset,
      coefficientOffset + 27,
    );
    evaluateIrradiance(coefficients, UP, probeRgb, sampleBasis);
    clampIrradiance(probeRgb);
    const value = luminance(probeRgb[0], probeRgb[1], probeRgb[2]);
    const radius = 2.15 + Math.min(3.1, value * 1.25);
    context.beginPath();
    context.arc(x, z, radius, 0, Math.PI * 2);
    context.fillStyle = displayColor(probeRgb, 2.1, 0.92);
    context.fill();
    context.strokeStyle =
      probe === selectedProbe ? "rgba(103, 240, 194, 0.95)" : "rgba(220, 235, 250, 0.23)";
    context.lineWidth = probe === selectedProbe ? 1.5 : 0.7;
    context.stroke();
    if (probe === selectedProbe) {
      context.beginPath();
      context.arc(x, z, radius + 7, 0, Math.PI * 2);
      context.strokeStyle = "rgba(103, 240, 194, 0.32)";
      context.setLineDash([2, 3]);
      context.stroke();
      context.setLineDash([]);
      context.font = '9px "SFMono-Regular", monospace';
      context.fillStyle = "#67f0c2";
      context.fillText(`P${probe}`, x + radius + 8, z - radius - 5);
    }
  }
}

function drawInterpolationCell(context, viewport) {
  const grid = simulation.grid;
  const cell = grid.cellAt(simulation.objectPosition);
  const left = viewport.mapX(grid.minX + cell.col0 * grid.spacing);
  const right = viewport.mapX(grid.minX + cell.col1 * grid.spacing);
  const top = viewport.mapZ(grid.minZ + cell.row0 * grid.spacing);
  const bottom = viewport.mapZ(grid.minZ + cell.row1 * grid.spacing);
  context.fillStyle = "rgba(103, 240, 194, 0.025)";
  context.fillRect(left, top, right - left, bottom - top);
  context.strokeStyle = "rgba(103, 240, 194, 0.46)";
  context.lineWidth = 1;
  context.strokeRect(left + 0.5, top + 0.5, right - left - 1, bottom - top - 1);
  context.font = '8px "SFMono-Regular", monospace';
  context.fillStyle = "rgba(103, 240, 194, 0.68)";
  context.fillText(`cell ${cell.row0},${cell.col0}`, left + 6, top + 13);

  const cornerLabels = [
    [`w00 ${((1 - cell.tx) * (1 - cell.tz)).toFixed(2)}`, left - 3, top - 5],
    [`w10 ${(cell.tx * (1 - cell.tz)).toFixed(2)}`, right + 4, top - 5],
    [`w01 ${((1 - cell.tx) * cell.tz).toFixed(2)}`, left - 3, bottom + 12],
    [`w11 ${(cell.tx * cell.tz).toFixed(2)}`, right + 4, bottom + 12],
  ];
  context.font = '8px "SFMono-Regular", monospace';
  context.fillStyle = "rgba(126, 239, 204, 0.78)";
  for (const [label, x, y] of cornerLabels) {
    const alignRight = x > viewport.width - 44;
    context.textAlign = alignRight ? "right" : "left";
    context.fillText(label, alignRight ? x - 6 : x, y);
  }
  context.textAlign = "left";
}

function drawLights(context, viewport) {
  const pulse = 1.5 + Math.sin(simulation.time * 3.2) * 1.2;
  for (const light of simulation.currentLights) {
    const x = viewport.mapX(light.position[0]);
    const z = viewport.mapZ(light.position[2]);
    context.beginPath();
    context.arc(x, z, 5 + pulse, 0, Math.PI * 2);
    context.strokeStyle = "rgba(255, 179, 92, 0.36)";
    context.lineWidth = 1;
    context.stroke();
    context.beginPath();
    context.arc(x, z, 2.2, 0, Math.PI * 2);
    context.fillStyle = "rgba(255, 204, 133, 0.92)";
    context.fill();
  }
}

function drawTrailAndObject(context, viewport) {
  if (trail.length > 1) {
    context.beginPath();
    for (let index = 0; index < trail.length; index += 1) {
      const point = trail[index];
      const x = viewport.mapX(point[0]);
      const z = viewport.mapZ(point[1]);
      if (index === 0) context.moveTo(x, z);
      else context.lineTo(x, z);
    }
    context.strokeStyle = "rgba(255, 179, 92, 0.2)";
    context.lineWidth = 1.2;
    context.stroke();
  }

  const x = viewport.mapX(simulation.objectPosition[0]);
  const z = viewport.mapZ(simulation.objectPosition[2]);
  const color = displayColor(simulation.objectRgb, 2.1, 0.7);
  const glow = context.createRadialGradient(x, z, 1, x, z, 34);
  glow.addColorStop(0, color);
  glow.addColorStop(0.28, displayColor(simulation.objectRgb, 2.1, 0.32));
  glow.addColorStop(1, "rgba(255, 179, 92, 0)");
  context.fillStyle = glow;
  context.beginPath();
  context.arc(x, z, 34, 0, Math.PI * 2);
  context.fill();

  context.beginPath();
  context.arc(x, z, 6.5, 0, Math.PI * 2);
  context.fillStyle = color;
  context.fill();
  context.strokeStyle = "rgba(255, 244, 220, 0.9)";
  context.lineWidth = 1;
  context.stroke();
  context.beginPath();
  context.arc(x, z, 11, 0, Math.PI * 2);
  context.strokeStyle = "rgba(255, 179, 92, 0.38)";
  context.setLineDash([3, 4]);
  context.stroke();
  context.setLineDash([]);
}

function drawScene() {
  const { context, width, height } = fitCanvas(elements.scene);
  drawBackground(context, width, height);
  const viewport = sceneViewport();
  const grid = simulation.grid;
  const left = viewport.mapX(grid.minX - grid.spacing * 0.5);
  const top = viewport.mapZ(grid.minZ - grid.spacing * 0.5);
  const right = viewport.mapX(grid.minX + (grid.cols - 1) * grid.spacing + grid.spacing * 0.5);
  const bottom = viewport.mapZ(grid.minZ + (grid.rows - 1) * grid.spacing + grid.spacing * 0.5);

  if (frameCounter % 2 === 0) updateHeatImage();
  context.imageSmoothingEnabled = true;
  context.globalAlpha = 0.82;
  context.drawImage(heatCanvas, left, top, right - left, bottom - top);
  context.globalAlpha = 1;
  drawGrid(context, viewport);
  drawInterpolationCell(context, viewport);
  drawProbes(context, viewport);
  drawLights(context, viewport);
  drawTrailAndObject(context, viewport);

  context.font = '9px "SFMono-Regular", monospace';
  context.fillStyle = "rgba(166, 185, 205, 0.62)";
  context.fillText("L2 SH FIELD / CONTINUOUS BILINEAR", 14, 20);
  context.textAlign = "right";
  context.fillStyle = "rgba(103, 240, 194, 0.7)";
  const last = simulation.history.at(-1);
  context.fillText(
    last?.rebuild
      ? `REBUILD ${last.updatedProbes} probes`
      : "FIELD CACHED",
    width - 14,
    20,
  );
  context.textAlign = "left";
}

function drawHistory() {
  const { context, width, height } = fitCanvas(elements.history);
  context.clearRect(0, 0, width, height);
  context.fillStyle = "rgba(4, 7, 11, 0.62)";
  context.fillRect(0, 0, width, height);

  const entries = simulation.history.slice(-300);
  const left = 40;
  const right = width - 13;
  const top = 13;
  const bottom = height - 20;
  context.strokeStyle = "rgba(160, 190, 220, 0.075)";
  context.lineWidth = 1;
  context.font = '8px "SFMono-Regular", monospace';
  context.fillStyle = "rgba(140, 158, 178, 0.75)";
  for (let line = 0; line <= 4; line += 1) {
    const y = top + ((bottom - top) * line) / 4;
    context.beginPath();
    context.moveTo(left, y);
    context.lineTo(right, y);
    context.stroke();
  }
  if (entries.length < 2) return;

  const values = entries.map((entry) => entry.luminance);
  let min = Math.min(...values);
  let max = Math.max(...values);
  const pad = Math.max(0.015, (max - min) * 0.16);
  min -= pad;
  max += pad;
  const mapX = (index) =>
    left + (index / Math.max(1, entries.length - 1)) * (right - left);
  const mapY = (value) => bottom - ((value - min) / Math.max(1e-6, max - min)) * (bottom - top);

  for (let index = 0; index < entries.length; index += 1) {
    if (!entries[index].rebuild) continue;
    const x = mapX(index);
    context.beginPath();
    context.moveTo(x, top);
    context.lineTo(x, bottom);
    context.strokeStyle = "rgba(103, 240, 194, 0.12)";
    context.stroke();
  }

  context.beginPath();
  for (let index = 0; index < entries.length; index += 1) {
    const x = mapX(index);
    const y = mapY(entries[index].luminance);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  }
  context.strokeStyle = "#67f0c2";
  context.lineWidth = 1.5;
  context.stroke();

  for (let index = 0; index < entries.length; index += 1) {
    if (!entries[index].crossedBoundary) continue;
    context.beginPath();
    context.arc(mapX(index), mapY(entries[index].luminance), 2.2, 0, Math.PI * 2);
    context.fillStyle = "#ffb35c";
    context.fill();
  }

  context.font = '8px "SFMono-Regular", monospace';
  context.fillStyle = "rgba(140, 158, 178, 0.7)";
  context.textAlign = "right";
  context.fillText(max.toFixed(3), left - 7, top + 4);
  context.fillText(min.toFixed(3), left - 7, bottom);
  context.textAlign = "left";
  context.fillText("luminance", left + 2, 9);
  context.textAlign = "right";
  context.fillStyle = "rgba(255, 179, 92, 0.82)";
  context.fillText("● cell boundary", right, 9);
  context.textAlign = "left";
}

function formatCoefficient(value) {
  if (Math.abs(value) >= 100) return value.toFixed(1);
  if (Math.abs(value) >= 0.001 || value === 0) return value.toFixed(3);
  return value.toExponential(1);
}

function renderCoefficients(row) {
  const grid = simulation.grid;
  let coefficients;
  let displayLuminance;
  let errorPct = 0;
  if (row) {
    coefficients = row.coefficients;
    displayLuminance = row.displayLuminance;
    errorPct = row.errorPct;
  } else {
    const offset = selectedProbe * 27;
    coefficients = Array.from(grid.display.subarray(offset, offset + 27));
    evaluateIrradiance(
      grid.display.subarray(offset, offset + 27),
      UP,
      probeRgb,
      sampleBasis,
    );
    clampIrradiance(probeRgb);
    displayLuminance = luminance(probeRgb[0], probeRgb[1], probeRgb[2]);
  }

  elements.selectedProbeLabel.textContent = `P${selectedProbe}`;
  elements.selectedLuminance.textContent = displayLuminance.toFixed(4);
  elements.selectedError.textContent = `${errorPct.toFixed(2)}%`;
  elements.selectedError.className = `error-chip ${
    errorPct > 30 ? "error-bad" : errorPct > 10 ? "error-warn" : ""
  }`;
  const fragment = document.createDocumentFragment();
  const headerName = document.createElement("span");
  headerName.className = "coef-name";
  headerName.textContent = "SH";
  fragment.append(headerName);
  for (const channel of CHANNELS) {
    const label = document.createElement("span");
    label.className = "coef-head";
    label.textContent = channel;
    fragment.append(label);
  }
  for (let sh = 0; sh < SH_NAMES.length; sh += 1) {
    const name = document.createElement("span");
    name.className = "coef-name";
    name.textContent = SH_NAMES[sh];
    fragment.append(name);
    for (let channel = 0; channel < 3; channel += 1) {
      const value = coefficients[sh * 3 + channel];
      const cell = document.createElement("span");
      cell.className = `coef-value ${value < 0 ? "negative" : ""}`;
      cell.textContent = formatCoefficient(value);
      fragment.append(cell);
    }
  }
  elements.coefficientGrid.replaceChildren(fragment);
}

function errorClass(errorPct) {
  return errorPct > 30 ? "error-bad" : errorPct > 10 ? "error-warn" : "error-good";
}

function renderProbeTable() {
  const fragment = document.createDocumentFragment();
  for (const row of probeRows) {
    const tr = document.createElement("tr");
    if (row.probe === selectedProbe) tr.className = "selected";
    tr.dataset.probe = String(row.probe);
    const values = [
      `P${row.probe}`,
      row.x.toFixed(1),
      row.z.toFixed(1),
      row.displayLuminance.toFixed(4),
      row.referenceLuminance.toFixed(4),
      `${row.errorPct.toFixed(2)}%`,
      `${row.projectionErrorPct.toFixed(2)}%`,
      `${row.updateAgeMs.toFixed(0)} ms`,
    ];
    values.forEach((value, index) => {
      const td = document.createElement("td");
      td.textContent = value;
      if (index === 5) td.className = errorClass(row.errorPct);
      if (index === 6) td.className = errorClass(row.projectionErrorPct);
      tr.append(td);
    });
    fragment.append(tr);
  }
  elements.probeBody.replaceChildren(fragment);
  if (probeRows.length) {
    const mean = probeRows.reduce((sum, row) => sum + row.errorPct, 0) / probeRows.length;
    const maximum = Math.max(...probeRows.map((row) => row.errorPct));
    elements.probeSummary.textContent = `${probeRows.length} probes · mean ${mean.toFixed(2)}% · max ${maximum.toFixed(2)}%`;
  }
  const selectedRow = probeRows.find((row) => row.probe === selectedProbe);
  renderCoefficients(selectedRow);
}

function refreshProbeRows() {
  const reference = simulation.grid.computeReference(simulation.currentLights);
  probeRows = simulation.probeRows(reference);
  renderProbeTable();
}

function updateStrategyText() {
  const interval = Number(elements.interval.value);
  const intervalText = interval === 0 ? "脏即更新" : `${interval} ms`;
  elements.intervalLabel.textContent = interval === 0 ? "脏即更新" : `${interval} ms`;
  elements.modePill.textContent =
    currentMode === "frame" ? "逐帧全量" : `按需 ${intervalText}`;
  if (currentMode === "frame") {
    elements.strategyNote.textContent = `每帧重建全部 ${simulation.grid.count} 个探针，适合作为画质参考。`;
  } else if (interval === 0) {
    elements.strategyNote.textContent = "灯光移动超过阈值时立即重建旧/新影响力并集，不再等待固定间隔。";
  } else {
    elements.strategyNote.textContent = `灯光移动超过阈值且经过 ${interval} ms 时，重建旧/新影响力并集。`;
  }
}

function updateUi(now) {
  const summary = simulation.summary();
  const last = simulation.history.at(-1) || {
    rebuildMs: 0,
    interpolationMs: 0,
    totalMs: 0,
    updatedProbes: 0,
  };
  elements.updateMetric.textContent = summary.meanRebuildMs.toFixed(3);
  elements.interpolationMetric.textContent = summary.meanInterpolationMs.toFixed(3);
  elements.totalMetric.textContent = summary.meanTotalMs.toFixed(3);
  elements.p95Metric.textContent = summary.p95TotalMs.toFixed(3);
  elements.boundaryCount.textContent = String(summary.boundaryEvents);
  elements.boundaryJump.textContent = summary.maxBoundaryChannelJump.toFixed(4);
  elements.meanError.textContent = `${summary.meanLumErrorPct.toFixed(2)}%`;
  elements.updateCount.textContent = String(summary.updateCount);
  elements.trajectoryTime.textContent = `T+${simulation.time.toFixed(1)} s`;
  elements.fps.textContent = `${fpsEma.toFixed(0)} FPS`;

  const budgetRatio = summary.meanTotalMs / (1000 / 60);
  elements.budgetBar.style.width = `${Math.min(100, budgetRatio * 100).toFixed(1)}%`;
  elements.budgetText.textContent = `${(budgetRatio * 100).toFixed(1)}%`;

  if (summary.boundaryEvents === 0) {
    elements.continuityBadge.textContent = "采样中";
    elements.continuityBadge.className = "status-pill warn";
  } else if (summary.boundaryJumpRatio < 1.6) {
    elements.continuityBadge.textContent = "连续";
    elements.continuityBadge.className = "status-pill good";
  } else {
    elements.continuityBadge.textContent = "检查跳变";
    elements.continuityBadge.className = "status-pill warn";
  }

  const selectedRow = probeRows.find((row) => row.probe === selectedProbe);
  renderCoefficients(selectedRow);
  if (last.rebuild) {
    elements.modePill.title = `上次重建 ${last.updatedProbes} 个探针，${last.rebuildMs.toFixed(3)} ms`;
  }
  lastUiTime = now;
}

function applyMode(mode) {
  currentMode = mode;
  simulation.mode = mode;
  for (const button of elements.modeButtons) {
    button.classList.toggle("active", button.dataset.mode === mode);
  }
  simulation.resetMetrics();
  updateStrategyText();
}

function applyInterval(value) {
  simulation.intervalMs = value;
  simulation.resetMetrics();
  updateStrategyText();
}

function applySpeed(value) {
  const oldSpeed = simulation.speed;
  const newSpeed = value / 100;
  if (oldSpeed > 0 && Number.isFinite(simulation.time)) {
    const phase = simulation.time * oldSpeed;
    simulation.time = phase / newSpeed;
    if (Number.isFinite(simulation.lastUpdateTime)) {
      simulation.lastUpdateTime = (simulation.lastUpdateTime * oldSpeed) / newSpeed;
    }
  }
  simulation.speed = newSpeed;
  elements.speedLabel.textContent = `${(newSpeed).toFixed(1)}×`;
}

function applySmoothing(value) {
  simulation.smoothingTau = value / 1000;
  elements.smoothingLabel.textContent = `${value} ms`;
}

function exportProbes() {
  if (!probeRows.length) refreshProbeRows();
  const headers = [
    "probe",
    "row",
    "col",
    "x",
    "y",
    "z",
    ...SH_NAMES.flatMap((name) => [`${name}_r`, `${name}_g`, `${name}_b`]),
    "display_luminance",
    "reference_luminance",
    "absolute_error",
    "error_pct",
    "projection_error_pct",
    "update_age_ms",
  ];
  const lines = [headers.join(",")];
  for (const row of probeRows) {
    const values = [
      row.probe,
      row.row,
      row.col,
      row.x,
      row.y,
      row.z,
      ...row.coefficients,
      row.displayLuminance,
      row.referenceLuminance,
      row.absoluteError,
      row.errorPct,
      row.projectionErrorPct,
      row.updateAgeMs,
    ];
    lines.push(values.map((value) => String(value)).join(","));
  }
  const blob = new Blob([`${lines.join("\n")}\n`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "dynamic-sh-probes.csv";
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function makeCell(text, tag = "span") {
  const element = document.createElement(tag);
  element.textContent = text;
  return element;
}

async function loadBenchmark() {
  try {
    const response = await fetch("./artifacts/benchmark.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const rows = [
      {
        name: "逐帧全量",
        ...data.comparison.perFrame,
        highlight: false,
      },
      {
        name: "按需 50 ms",
        ...data.comparison.onDemand50ms,
        highlight: true,
      },
    ];

    const compareFragment = document.createDocumentFragment();
    const head = document.createElement("div");
    head.className = "compare-row head";
    for (const label of ["模式", "重建 ms", "插值 ms", "总计 ms", "误差"]) {
      head.append(makeCell(label));
    }
    compareFragment.append(head);
    for (const row of rows) {
      const line = document.createElement("div");
      line.className = `compare-row body ${row.highlight ? "highlight" : ""}`;
      line.append(makeCell(row.name));
      line.append(makeCell(row.meanRebuildMs.toFixed(3)));
      line.append(makeCell(row.meanInterpolationMs.toFixed(3)));
      line.append(makeCell(row.meanTotalMs.toFixed(3)));
      line.append(makeCell(`${row.meanLumErrorPct.toFixed(2)}%`));
      compareFragment.append(line);
    }
    elements.compareTable.replaceChildren(compareFragment);
    elements.rebuildRatio.textContent = `${data.comparison.updateCostRatio.toFixed(2)}×`;
    elements.totalRatio.textContent = `${data.comparison.totalCostRatio.toFixed(2)}×`;
    elements.benchmarkStatus.textContent = `${data.perProbe.count} probes · 已验证`;

    const body = document.createDocumentFragment();
    for (const entry of data.frequencies) {
      const tr = document.createElement("tr");
      tr.dataset.interval = String(entry.intervalMs);
      const interval =
        entry.intervalMs === 0 ? "脏即更新" : `${entry.intervalMs.toFixed(1)} ms`;
      const cells = [
        interval,
        entry.updateCount,
        entry.meanRebuildMs.toFixed(3),
        entry.meanInterpolationMs.toFixed(3),
        entry.meanTotalMs.toFixed(3),
        `${entry.meanLumErrorPct.toFixed(2)}%`,
        `${entry.meanP95LumErrorPct.toFixed(2)}%`,
        `${entry.maxLumErrorPct.toFixed(2)}%`,
        entry.maxBoundaryChannelJump.toFixed(4),
      ];
      for (const [index, value] of cells.entries()) {
        const td = makeCell(String(value), "td");
        if (index === 5) td.className = errorClass(entry.meanLumErrorPct);
        tr.append(td);
      }
      tr.title = "点击应用该更新间隔";
      body.append(tr);
    }
    elements.frequencyBody.replaceChildren(body);
  } catch (error) {
    elements.benchmarkStatus.textContent = "未生成基准";
    elements.compareTable.replaceChildren(
      makeCell("运行 npm run bench 后刷新页面", "p"),
    );
    elements.frequencyBody.replaceChildren();
    const row = document.createElement("tr");
    const cell = makeCell("运行 npm run bench 生成基准数据", "td");
    cell.colSpan = 9;
    cell.className = "empty";
    row.append(cell);
    elements.frequencyBody.append(row);
    console.warn("Benchmark artifact unavailable:", error);
  }
}

function handleSceneClick(event) {
  const bounds = elements.scene.getBoundingClientRect();
  const pointerX = event.clientX - bounds.left;
  const pointerY = event.clientY - bounds.top;
  const viewport = sceneViewport();
  const grid = simulation.grid;
  let nearest = -1;
  let nearestDistance = 22;
  for (let probe = 0; probe < grid.count; probe += 1) {
    const offset = probe * 3;
    const dx = viewport.mapX(grid.positions[offset]) - pointerX;
    const dz = viewport.mapZ(grid.positions[offset + 2]) - pointerY;
    const distance = Math.hypot(dx, dz);
    if (distance < nearestDistance) {
      nearest = probe;
      nearestDistance = distance;
    }
  }
  if (nearest < 0) return;
  selectedProbe = nearest;
  for (const row of elements.probeBody.children) {
    row.classList.toggle("selected", Number(row.dataset.probe) === selectedProbe);
  }
  renderCoefficients(probeRows.find((row) => row.probe === selectedProbe));
}

function restart() {
  createSimulation();
  applyMode(currentMode);
  updateStrategyText();
  refreshProbeRows();
  lastFrameTime = performance.now();
  updateUi(performance.now());
}

function animate(now) {
  const elapsed = Math.max(0, (now - lastFrameTime) / 1000);
  const dt = Math.min(elapsed, 0.05);
  lastFrameTime = now;
  if (dt > 0) {
    const instantFps = Math.min(240, 1 / dt);
    fpsEma += (instantFps - fpsEma) * 0.06;
  }

  if (playing) {
    simulation.step(dt);
    trail.push([simulation.objectPosition[0], simulation.objectPosition[2]]);
    if (trail.length > 150) trail.shift();
    if (simulation.history.length > 1600) simulation.history.splice(0, 400);
    if (simulation.qualityHistory.length > 180) simulation.qualityHistory.splice(0, 60);
  }

  frameCounter += 1;
  drawScene();
  drawHistory();
  if (now - lastUiTime > 220) updateUi(now);
  if (now - lastProbeRefresh > 720) {
    refreshProbeRows();
    lastProbeRefresh = now;
  }
  requestAnimationFrame(animate);
}

for (const button of elements.modeButtons) {
  button.addEventListener("click", () => applyMode(button.dataset.mode));
}

elements.interval.addEventListener("input", () => {
  applyInterval(Number(elements.interval.value));
});

elements.speed.addEventListener("input", () => {
  applySpeed(Number(elements.speed.value));
});

elements.smoothing.addEventListener("input", () => {
  applySmoothing(Number(elements.smoothing.value));
});

elements.play.addEventListener("click", () => {
  playing = !playing;
  elements.play.textContent = playing ? "Ⅱ" : "▶";
  elements.play.setAttribute("aria-label", playing ? "暂停" : "播放");
  lastFrameTime = performance.now();
});

elements.reset.addEventListener("click", restart);
elements.export.addEventListener("click", exportProbes);
elements.scene.addEventListener("click", handleSceneClick);

elements.probeBody.addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-probe]");
  if (!row) return;
  selectedProbe = Number(row.dataset.probe);
  for (const candidate of elements.probeBody.children) {
    candidate.classList.toggle(
      "selected",
      Number(candidate.dataset.probe) === selectedProbe,
    );
  }
  renderCoefficients(probeRows.find((entry) => entry.probe === selectedProbe));
});

elements.frequencyBody.addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-interval]");
  if (!row) return;
  const interval = Math.round(Number(row.dataset.interval));
  elements.interval.value = String(Math.max(0, Math.min(400, interval)));
  applyMode("ondemand");
  applyInterval(Number(elements.interval.value));
});

window.addEventListener("keydown", (event) => {
  if (event.target instanceof HTMLInputElement) return;
  if (event.code === "Space") {
    event.preventDefault();
    elements.play.click();
  }
  if (event.key.toLowerCase() === "r") restart();
});

document.addEventListener("visibilitychange", () => {
  lastFrameTime = performance.now();
});

createSimulation();
updateStrategyText();
refreshProbeRows();
updateUi(performance.now());
loadBenchmark();
requestAnimationFrame(animate);
