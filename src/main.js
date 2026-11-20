import { parse } from "../vendor/opentype.min.mjs";
import { BUILTIN_SPECIMENS, buildSpecimen, buildFontSpecimen } from "./glyphs.js";
import { generateDistanceField } from "./msdf.js";
import { evaluateSample, summarizeSweep } from "./evaluate.js";
import { GlyphRenderer } from "./renderer.js";
import { drawReference, drawThumbnail } from "./canvas-utils.js";

const $ = (id) => document.getElementById(id);

const ISSUE_LABELS = {
  "open-contour": "开放轮廓",
  "self-intersection": "轮廓自交",
  "duplicate-vertex": "重复顶点",
  "degenerate-contour": "退化轮廓",
  "zero-length-edge": "零长度边",
};

const VIEW_LABELS = {
  msdf: ["MSDF · 覆盖率", "屏幕导数重建 × 三通道中值"],
  sdf: ["SDF · 覆盖率", "屏幕导数重建 × 单通道"],
  reference: ["高分辨率轮廓", "Canvas 精确贝塞尔参考"],
  error: ["误差叠加", "青色断笔 / 琥珀边界偏差 / 洋红轮廓错误"],
};

const state = {
  selectedId: BUILTIN_SPECIMENS[0].id,
  cornerAngle: 42,
  textureSize: 128,
  testSize: 48,
  shiftX: 0,
  shiftY: 0,
  view: "msdf",
  raw: false,
  channelTint: true,
  showGrid: true,
  showAnatomy: true,
  specimen: null,
  field: null,
  evaluation: null,
  renderInfo: null,
  referenceInfo: null,
  font: null,
  fontName: "",
  fontSpecimens: [],
  sweep: [],
  sweepVersion: 0,
  evalVersion: 0,
  baseCache: new Map(),
};

let renderer = null;
let evaluateTimer = 0;
let rebuildTimer = 0;
let renderFrame = 0;

function setStatus(text, type = "ready") {
  const element = $("webglStatus");
  element.classList.toggle("is-ready", type === "ready");
  element.classList.toggle("is-error", type === "error");
  element.innerHTML = `<i></i> ${text}`;
}

function formatSigned(value, digits = 2) {
  const number = Math.abs(value) < 0.005 ? 0 : value;
  return `${number >= 0 ? "+" : "−"}${Math.abs(number).toFixed(digits)}`;
}

function escapeHtml(value) {
  return String(value).replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character],
  );
}

function setMetric(element, text, level = "") {
  element.textContent = text;
  element.classList.remove("is-good", "is-warn", "is-bad");
  if (level) element.classList.add(`is-${level}`);
}

function getDefinitions() {
  return [...BUILTIN_SPECIMENS, ...state.fontSpecimens];
}

function getDefinition(id = state.selectedId) {
  return getDefinitions().find((definition) => definition.id === id) || getDefinitions()[0];
}

function getThumbnailSpecimen(definition) {
  const key = `${definition.id}:${definition.path || definition.rawContours?.length}`;
  if (!state.baseCache.has(key)) {
    state.baseCache.set(
      key,
      definition.source === "font" ? definition : buildSpecimen(definition, 42),
    );
  }
  return state.baseCache.get(key);
}

function renderGlyphGrid() {
  const grid = $("glyphGrid");
  grid.innerHTML = "";
  for (const definition of getDefinitions()) {
    const specimen = getThumbnailSpecimen(definition);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "glyph-button";
    button.dataset.id = definition.id;
    button.title = definition.description || definition.title;
    button.classList.toggle("is-active", definition.id === state.selectedId);
    button.classList.toggle("has-fault", Boolean(definition.fault));
    button.setAttribute("aria-pressed", String(definition.id === state.selectedId));

    const canvas = document.createElement("canvas");
    canvas.width = 72;
    canvas.height = 72;
    drawThumbnail(canvas, specimen);
    button.append(canvas);

    const label = document.createElement("span");
    label.textContent = definition.source === "font" ? "font" : definition.char;
    button.append(label);
    button.addEventListener("click", () => selectSpecimen(definition.id));
    grid.append(button);
  }
}

function updateSourceNote() {
  const note = $("sourceNote");
  if (state.fontSpecimens.length) {
    const safeFontName = escapeHtml(state.fontName);
    note.innerHTML = `
      <span class="source-icon">⌁</span>
      <div>
        <strong>${safeFontName}</strong>
        <p>${state.fontSpecimens.length} 个本地字形与本组内置轮廓并列可复用。</p>
      </div>`;
  } else {
    note.innerHTML = `
      <span class="source-icon">⌁</span>
      <div>
        <strong>内置可复用轮廓</strong>
        <p>立方贝塞尔与折线混合，含刻意损坏样本。</p>
      </div>`;
  }
}

function syncSpecimenSummary() {
  const specimen = state.specimen;
  if (!specimen) return;
  const segments = specimen.contours.reduce((sum, contour) => sum + contour.segments.length, 0);
  $("glyphTitle").textContent = specimen.title;
  $("glyphClass").textContent = specimen.className;
  $("contourCount").textContent = String(specimen.contours.length);
  $("segmentCount").textContent = String(segments);
  $("cornerCount").textContent = String(specimen.analysis.corners.length);
  $("groupCount").textContent = String(specimen.analysis.groups.length);
  $("sampleDescription").textContent =
    `${state.testSize} px · ${state.textureSize}² 纹理 / ${state.cornerAngle}° 尖角分组`;
  $("stageEmpty").hidden = true;
  $("stageEmpty").innerHTML = "";
}

async function rebuildSelected({ resetSweep = true } = {}) {
  const definition = getDefinition();
  if (!definition) return;
  if (resetSweep) {
    state.sweep = [];
    state.sweepVersion += 1;
    resetSweepTable();
  }

  state.evalVersion += 1;
  const version = ++state.sweepVersion;
  setStatus("生成距离场", "ready");
  await new Promise((resolve) => setTimeout(resolve, 0));
  if (version !== state.sweepVersion) return;

  try {
    state.specimen = buildSpecimen(definition, state.cornerAngle);
    state.field = generateDistanceField(state.specimen, state.textureSize);
    renderer?.uploadField(state.field);
    syncSpecimenSummary();
    renderGlyphGrid();
    renderNow();
    await evaluateCurrent();
    setStatus("WebGL2 就绪");
  } catch (error) {
    console.error(error);
    setStatus("轮廓生成失败", "error");
  }
}

function selectSpecimen(id) {
  if (id === state.selectedId && state.specimen) return;
  state.selectedId = id;
  state.evaluation = null;
  renderGlyphGrid();
  rebuildSelected({ resetSweep: true });
}

function scheduleRebuild(delay = 150) {
  window.clearTimeout(rebuildTimer);
  rebuildTimer = window.setTimeout(() => rebuildSelected({ resetSweep: true }), delay);
}

function scheduleEvaluate(delay = 120) {
  window.clearTimeout(evaluateTimer);
  evaluateTimer = window.setTimeout(() => evaluateCurrent(), delay);
}

function scheduleRender() {
  if (renderFrame) return;
  renderFrame = window.requestAnimationFrame(() => {
    renderFrame = 0;
    renderNow();
  });
}

function renderNow() {
  if (!state.specimen || !state.field) return;
  const isReference = state.view === "reference";
  $("glCanvas").style.visibility = isReference ? "hidden" : "visible";
  $("referenceCanvas").hidden = !isReference;

  if (isReference) {
    state.referenceInfo = drawReference($("referenceCanvas"), state.specimen, {
      ink: "#182b2d",
      background: "#f1eee3",
    });
    state.renderInfo = null;
  } else if (renderer) {
    state.renderInfo = renderer.draw(state.field, {
      view: state.view,
      testPx: state.testSize,
      shiftX: state.shiftX,
      shiftY: state.shiftY,
      raw: state.raw,
      channelTint: state.channelTint,
      showGrid: state.showGrid,
    });
    state.referenceInfo = null;
  }

  const [label, detail] = VIEW_LABELS[state.view];
  $("viewLabel").textContent = state.raw && ["msdf", "sdf"].includes(state.view)
    ? `${state.view.toUpperCase()} · 原始距离场`
    : label;
  $("derivativeLabel").textContent = detail;
  $("stageZoom").textContent = state.renderInfo
    ? `${state.renderInfo.zoom.toFixed(1)}×`
    : "高分辨率";
  drawOverlay();
}

function activeChannelMode() {
  return state.view === "sdf" ? "sdf" : "msdf";
}

async function evaluateCurrent() {
  if (!state.specimen || !state.field) return;
  const version = ++state.evalVersion;
  const button = $("evaluateCurrent");
  button.disabled = true;
  button.textContent = "计算中…";
  await new Promise((resolve) => setTimeout(resolve, 0));
  if (version !== state.evalVersion) {
    button.disabled = false;
    button.textContent = "评估当前采样";
    return;
  }

  try {
    state.evaluation = evaluateSample(state.specimen, state.field, {
      sizePx: state.testSize,
      shiftX: state.shiftX,
      shiftY: state.shiftY,
    });
    updateMetrics();
    updateDiagnosis();
    drawOverlay();
  } catch (error) {
    console.error(error);
  } finally {
    button.disabled = false;
    button.textContent = "评估当前采样";
  }
}

function updateMetrics() {
  const result = state.evaluation;
  if (!result) return;
  const mode = activeChannelMode();
  const metrics = result[mode];
  const biasLevel = Math.abs(metrics.biasPx) < 0.12
    ? "good"
    : Math.abs(metrics.biasPx) < 0.45
      ? "warn"
      : "bad";
  setMetric($("biasMetric"), `${formatSigned(metrics.biasPx)} px`, biasLevel);
  setMetric(
    $("brokenMetric"),
    String(metrics.brokenPixels),
    metrics.brokenPixels === 0 ? "good" : "bad",
  );
  setMetric(
    $("boundaryMetric"),
    String(metrics.boundaryMismatch),
    metrics.boundaryMaePx < 0.12 ? "good" : metrics.boundaryMaePx < 0.35 ? "warn" : "bad",
  );
  $("boundaryMetricNote").textContent =
    `平均 ${metrics.boundaryMaePx.toFixed(2)} px · P95 ${metrics.boundaryP95Px.toFixed(2)} px`;

  const errors = state.specimen.analysis.contourErrors;
  if (errors.length) {
    const uniqueTypes = [...new Set(errors.map((issue) => ISSUE_LABELS[issue.type] || issue.type))];
    setMetric($("contourMetric"), `错误 ${errors.length}`, "bad");
    $("contourMetricNote").textContent = uniqueTypes.join(" / ");
  } else {
    setMetric($("contourMetric"), "干净", "good");
    const holes = state.specimen.analysis.holes.length;
    $("contourMetricNote").textContent = holes ? `闭合 · ${holes} 个内孔` : "闭合 · 无自交";
  }

  $("sampleDescription").textContent =
    `${state.testSize} px · Δ${state.shiftX.toFixed(2)}×${state.shiftY.toFixed(2)} / ${state.textureSize}² 纹理`;
}

function updateDiagnosis() {
  const result = state.evaluation;
  const errors = state.specimen?.analysis.contourErrors || [];
  const contourCard = $("contourDiagnosis");
  const shadingCard = $("shadingDiagnosis");

  if (errors.length) {
    const counts = new Map();
    for (const issue of errors) {
      const label = ISSUE_LABELS[issue.type] || issue.type;
      counts.set(label, (counts.get(label) || 0) + 1);
    }
    const summary = [...counts.entries()].map(([label, count]) => `${label} ×${count}`).join("，");
    $("contourVerdict").textContent = "发现错误";
    $("contourDetail").textContent = `${summary}。在高分辨率参考中可直接看到破口，且不会随字号消失。`;
    contourCard.classList.add("is-active");
    contourCard.classList.remove("is-clean");
  } else {
    $("contourVerdict").textContent = "拓扑干净";
    $("contourDetail").textContent =
      `轮廓闭合、无自交；检测到 ${state.specimen?.analysis.holes.length || 0} 个内孔。`;
    contourCard.classList.remove("is-active");
    contourCard.classList.add("is-clean");
  }

  const metrics = result?.msdf;
  const summary = summarizeSweep(state.sweep);
  if (!metrics) {
    $("shadingVerdict").textContent = "待评估";
    $("shadingDetail").textContent = "当前采样尚未完成像素比较。";
    shadingCard.classList.remove("is-active", "is-clean");
    return;
  }

  const sampled =
    metrics.brokenPixels > 0 ||
    Math.abs(metrics.biasPx) > 0.45 ||
    metrics.boundaryMaePx > 0.35 ||
    metrics.boundaryP95Px > 0.8 ||
    summary.unstable;
  if (sampled) {
    $("shadingVerdict").textContent = "可见偏差";
    const sweepText = state.sweep.length
      ? ` 扫描最坏边界 ${summary.worstBias.toFixed(2)} px、断笔 ${summary.maxBroken}。`
      : "";
    $("shadingDetail").textContent =
      `${state.testSize}px 边界偏差 ${formatSigned(metrics.biasPx)} px，断笔 ${metrics.brokenPixels} 像素。${sweepText}`;
    shadingCard.classList.add("is-active");
    shadingCard.classList.remove("is-clean");
  } else {
    $("shadingVerdict").textContent = "稳定";
    $("shadingDetail").textContent =
      `${state.testSize}px 下边界偏差 ${formatSigned(metrics.biasPx)} px、断笔 ${metrics.brokenPixels} 像素；参考轮廓与重建覆盖一致。`;
    shadingCard.classList.remove("is-active");
    shadingCard.classList.add("is-clean");
  }

  if (errors.length) {
    $("shadingDetail").textContent += " 轮廓错误会污染覆盖比较，应先修复轮廓。";
  }
}

function prepareOverlay() {
  const canvas = $("overlayCanvas");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(canvas.clientWidth * dpr));
  const height = Math.max(1, Math.round(canvas.clientHeight * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const context = canvas.getContext("2d");
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
  return { context, width: canvas.clientWidth, height: canvas.clientHeight, dpr };
}

function stagePoint(u, v) {
  const overlay = $("overlayCanvas");
  if (state.renderInfo) {
    const info = state.renderInfo;
    return {
      x: ((info.originX + u * info.displayPx) / info.width) * overlay.clientWidth,
      y:
        overlay.clientHeight -
        ((info.originY + (1 - v) * info.displayPx) / info.height) * overlay.clientHeight,
    };
  }
  if (state.referenceInfo) {
    const info = state.referenceInfo;
    return {
      x: ((info.left + u * info.side) / info.width) * overlay.clientWidth,
      y: ((info.top + v * info.side) / info.height) * overlay.clientHeight,
    };
  }
  return { x: 0, y: 0 };
}

function drawOverlayGrid(context, cssWidth, cssHeight) {
  if (!state.showGrid) return;
  const stepSource = state.renderInfo
    ? (state.renderInfo.displayPx / state.testSize / state.renderInfo.width) * cssWidth
    : state.referenceInfo
      ? (state.referenceInfo.side / state.testSize / state.referenceInfo.width) * cssWidth
      : 0;
  if (stepSource < 3) return;

  const p0 = stagePoint(0, 0);
  const p1 = stagePoint(1, 1);
  const left = Math.min(p0.x, p1.x);
  const right = Math.max(p0.x, p1.x);
  const top = Math.min(p0.y, p1.y);
  const bottom = Math.max(p0.y, p1.y);
  context.save();
  context.strokeStyle = state.view === "reference"
    ? "rgba(232, 92, 47, 0.13)"
    : "rgba(113, 214, 213, 0.08)";
  context.lineWidth = 0.6;
  context.beginPath();
  for (let x = left; x <= right + 0.1; x += stepSource) {
    context.moveTo(x, top);
    context.lineTo(x, bottom);
  }
  for (let y = top; y <= bottom + 0.1; y += stepSource) {
    context.moveTo(left, y);
    context.lineTo(right, y);
  }
  context.stroke();
  context.restore();
}

function drawErrorOverlay(context, cssWidth) {
  if (state.view !== "error" || !state.evaluation || !state.renderInfo) return;
  const evaluation = state.evaluation;
  const reference = evaluation.reference;
  const info = state.renderInfo;
  const cellSize = (info.displayPx / info.width) * cssWidth / state.testSize;
  const colors = [
    "",
    "rgba(223, 155, 32, 0.56)",
    "rgba(23, 167, 176, 0.72)",
    "rgba(232, 92, 47, 0.38)",
  ];

  context.save();
  for (let y = 0; y < reference.height; y += 1) {
    for (let x = 0; x < reference.width; x += 1) {
      const error = evaluation.msdf.errorMap[y * reference.width + x];
      if (!error) continue;
      const u = (x + 0.5 - reference.paddingPx - reference.shiftX) / reference.sizePx;
      const v = (y + 0.5 - reference.paddingPx - reference.shiftY) / reference.sizePx;
      if (u < 0 || u > 1 || v < 0 || v > 1) continue;
      const point = stagePoint(u, v);
      context.fillStyle = colors[error] || colors[1];
      context.fillRect(point.x - cellSize * 0.5, point.y - cellSize * 0.5, cellSize + 0.4, cellSize + 0.4);
      if (error === 2) {
        context.strokeStyle = "rgba(133, 238, 236, 0.9)";
        context.lineWidth = 0.7;
        context.strokeRect(
          point.x - cellSize * 0.5,
          point.y - cellSize * 0.5,
          cellSize + 0.4,
          cellSize + 0.4,
        );
      }
    }
  }
  context.restore();
}

function drawAnatomyOverlay(context, cssWidth, cssHeight) {
  if (!state.showAnatomy || !state.specimen) return;
  const specimen = state.specimen;
  const analysis = specimen.analysis;

  context.save();
  context.lineCap = "round";
  context.lineJoin = "round";

  const corners = [...analysis.corners].sort((a, b) => b.angle - a.angle).slice(0, 32);
  for (const corner of corners) {
    const point = stagePoint(corner.point.x, corner.point.y);
    context.strokeStyle = "rgba(79, 133, 225, 0.95)";
    context.lineWidth = 1.2;
    context.beginPath();
    context.arc(point.x, point.y, 2.8, 0, Math.PI * 2);
    context.stroke();
  }

  for (const hole of analysis.holes) {
    const point = stagePoint(hole.x, hole.y);
    context.strokeStyle = "rgba(23, 167, 176, 0.95)";
    context.lineWidth = 1.4;
    context.beginPath();
    context.arc(point.x, point.y, 5, 0, Math.PI * 2);
    context.stroke();
    context.beginPath();
    context.moveTo(point.x - 2, point.y);
    context.lineTo(point.x + 2, point.y);
    context.stroke();
  }

  for (const issue of analysis.contourErrors) {
    const point = issue.point ? stagePoint(issue.point.x, issue.point.y) : null;
    if (!point) continue;
    context.strokeStyle = "rgba(215, 53, 116, 0.98)";
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(point.x - 6, point.y - 6);
    context.lineTo(point.x + 6, point.y + 6);
    context.moveTo(point.x + 6, point.y - 6);
    context.lineTo(point.x - 6, point.y + 6);
    context.stroke();

    if (issue.type === "open-contour") {
      const start = specimen.contours[issue.contourIndex]?.start;
      if (start) {
        const startPoint = stagePoint(start.x, start.y);
        context.setLineDash([3, 4]);
        context.lineWidth = 1.4;
        context.beginPath();
        context.moveTo(startPoint.x, startPoint.y);
        context.lineTo(point.x, point.y);
        context.stroke();
        context.setLineDash([]);
      }
    }
  }

  const annotationColors = {
    sharp: "#4f85e1",
    counter: "#17a7b0",
    thin: "#df9b20",
    gap: "#df9b20",
    curve: "#4f85e1",
    fault: "#d73574",
  };

  for (const annotation of specimen.annotations) {
    const point = stagePoint(annotation.x, annotation.y);
    const color = annotationColors[annotation.kind] || "#df9b20";
    const labelX = Math.min(cssWidth - 74, point.x + 10);
    const labelY = Math.max(13, Math.min(cssHeight - 10, point.y - 10));

    context.fillStyle = color;
    context.beginPath();
    context.arc(point.x, point.y, 2.2, 0, Math.PI * 2);
    context.fill();
    context.strokeStyle = color;
    context.lineWidth = 0.8;
    context.beginPath();
    context.moveTo(point.x + 2, point.y - 2);
    context.lineTo(labelX - 3, labelY + 3);
    context.stroke();

    context.font = '8px "SFMono-Regular", Menlo, "Noto Sans SC", monospace';
    const textWidth = context.measureText(annotation.label).width;
    context.fillStyle = "rgba(10, 25, 27, 0.82)";
    context.fillRect(labelX - 3, labelY - 8, textWidth + 6, 12);
    context.fillStyle = "#f7f4eb";
    context.fillText(annotation.label, labelX, labelY + 1);
  }

  context.restore();
}

function drawOverlay() {
  const overlay = prepareOverlay();
  if (!state.specimen) return;
  if (state.view === "reference") {
    drawOverlayGrid(overlay.context, overlay.width, overlay.height);
  } else if (state.view === "error") {
    drawErrorOverlay(overlay.context, overlay.width);
  }
  drawAnatomyOverlay(overlay.context, overlay.width, overlay.height);
}

function resetSweepTable() {
  for (const row of $("sweepBody").rows) {
    for (let index = 1; index < row.cells.length; index += 1) {
      const cell = row.cells[index];
      cell.className = "";
      cell.textContent = "—";
    }
  }
  $("sweepProgress").style.width = "0%";
  $("exportCsv").disabled = true;
}

function setSweepCell(rowIndex, columnIndex, result) {
  const row = $("sweepBody").rows[rowIndex];
  if (!row) return;
  const cell = row.cells[columnIndex + 1];
  if (!cell) return;
  if (!result) {
    cell.className = "is-running";
    cell.textContent = "···";
    return;
  }
  const metrics = result.msdf;
  const bias = Math.abs(metrics.biasPx);
  const level = metrics.brokenPixels > 0
    ? "is-bad"
    : bias > 0.35 || metrics.boundaryMismatch > 4
      ? "is-warn"
      : "is-good";
  cell.className = level;
  cell.innerHTML = `<b>${formatSigned(metrics.biasPx)}</b><span>${metrics.brokenPixels} 断</span>`;
}

async function runSweep() {
  if (!state.specimen || !state.field) return;
  const button = $("runSweep");
  const version = state.sweepVersion;
  const runId = (runSweep.runId || 0) + 1;
  runSweep.runId = runId;
  button.disabled = true;
  button.textContent = "扫描中…";
  state.sweep = [];
  resetSweepTable();
  const scales = [14, 28, 56, 96];
  const shifts = [0, 0.25, 0.5, 0.75];

  try {
    for (let rowIndex = 0; rowIndex < scales.length; rowIndex += 1) {
      for (let columnIndex = 0; columnIndex < shifts.length; columnIndex += 1) {
        if (version !== state.sweepVersion || runId !== runSweep.runId) return;
        setSweepCell(rowIndex, columnIndex, null);
        await new Promise((resolve) => setTimeout(resolve, 18));
        if (version !== state.sweepVersion || runId !== runSweep.runId) return;
        const offset = shifts[columnIndex];
        const result = evaluateSample(state.specimen, state.field, {
          sizePx: scales[rowIndex],
          shiftX: offset,
          shiftY: offset,
        });
        state.sweep.push({
          sizePx: scales[rowIndex],
          shiftX: offset,
          shiftY: offset,
          ...result,
        });
        setSweepCell(rowIndex, columnIndex, result);
        const complete = state.sweep.length / (scales.length * shifts.length);
        $("sweepProgress").style.width = `${complete * 100}%`;
      }
    }
    $("exportCsv").disabled = state.sweep.length === 0;
    updateDiagnosis();
  } finally {
    if (runId === runSweep.runId) {
      button.disabled = false;
      button.textContent = "重新运行 16 组扫描";
    }
  }
}

function exportSweepCsv() {
  if (!state.sweep.length) return;
  const header = [
    "glyph",
    "texture_size",
    "corner_angle",
    "font_px",
    "shift_x",
    "shift_y",
    "channel_mode",
    "boundary_bias_px",
    "boundary_mae_px",
    "boundary_p95_px",
    "broken_pixels",
    "boundary_mismatch",
    "coverage_mae",
    "sampled_error_pixels",
  ];
  const rows = [header];
  for (const result of state.sweep) {
    for (const mode of ["msdf", "sdf"]) {
      const metrics = result[mode];
      rows.push([
        state.specimen.title,
        state.textureSize,
        state.cornerAngle,
        result.sizePx,
        result.shiftX,
        result.shiftY,
        mode,
        metrics.biasPx.toFixed(5),
        metrics.boundaryMaePx.toFixed(5),
        metrics.boundaryP95Px.toFixed(5),
        metrics.brokenPixels,
        metrics.boundaryMismatch,
        metrics.coverageMae.toFixed(6),
        metrics.sampledErrorPixels,
      ]);
    }
  }
  const csv = `\ufeff${rows.map((row) => row.join(",")).join("\n")}`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `msdf-diagnostics-${state.specimen.id}-${state.textureSize}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

async function importFont(file) {
  if (!file) return;
  setStatus("解析字体", "ready");
  $("fontHint").textContent = `正在读取 ${file.name}…`;
  try {
    const buffer = await file.arrayBuffer();
    const font = parse(buffer);
    state.font = font;
    state.fontName =
      font.getEnglishName?.("fullName") ||
      font.names?.fullName?.en ||
      font.names?.fontFamily?.en ||
      file.name;
    $("fontHint").textContent = `${state.fontName} · ${file.name}`;
    $("importedTools").hidden = false;
    const firstGlyphs = Array.from($("glyphChars").value).filter((char) => char.trim());
    await generateFontSpecimens(firstGlyphs);
    setStatus("字体已导入");
  } catch (error) {
    console.error(error);
    setStatus("字体解析失败", "error");
    $("fontHint").textContent = `无法解析：${error.message}`;
  }
}

async function generateFontSpecimens(characters) {
  if (!state.font) return;
  const uniqueCharacters = [...new Set(characters)].filter((char) => char.trim());
  const specimens = [];
  for (let index = 0; index < uniqueCharacters.length; index += 1) {
    const character = uniqueCharacters[index];
    try {
      const glyph = state.font.charToGlyph(character);
      if (!glyph || glyph.index === 0) continue;
      const specimen = buildFontSpecimen({
        glyph,
        font: state.font,
        character,
        index,
      });
      if (specimen.rawContours.length) specimens.push(specimen);
    } catch (error) {
      console.warn("Skipped glyph", character, error);
    }
  }
  if (!specimens.length) {
    $("fontHint").textContent = "输入字符没有可用轮廓。";
    return;
  }
  state.fontSpecimens = specimens;
  state.baseCache.clear();
  state.selectedId = specimens[0].id;
  updateSourceNote();
  renderGlyphGrid();
  await rebuildSelected({ resetSweep: true });
}

function syncControlLabels() {
  $("textureSizeTag").textContent = `${state.textureSize}²`;
  $("cornerAngleValue").textContent = `${state.cornerAngle}°`;
  $("testSizeValue").textContent = `${state.testSize} px`;
  $("sampleTag").textContent = `${state.testSize} px`;
  $("shiftXValue").textContent = `${formatSigned(state.shiftX, 2)} px`;
  $("shiftYValue").textContent = `${formatSigned(state.shiftY, 2)} px`;
  $("rawField").checked = state.raw;
  $("channelTint").checked = state.channelTint;
  $("showGrid").checked = state.showGrid;
  $("showAnatomy").checked = state.showAnatomy;
}

function setView(view) {
  state.view = view;
  for (const tab of document.querySelectorAll(".view-tab")) {
    const active = tab.dataset.view === view;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  }
  const rawApplicable = view === "msdf" || view === "sdf";
  $("rawField").disabled = !rawApplicable;
  $("channelTint").disabled = view !== "msdf";
  renderNow();
  updateMetrics();
  if (!state.evaluation) scheduleEvaluate(20);
}

function bindEvents() {
  $("textureSize").addEventListener("change", (event) => {
    state.textureSize = Number(event.target.value);
    syncControlLabels();
    state.evaluation = null;
    rebuildSelected({ resetSweep: true });
  });

  $("cornerAngle").addEventListener("input", (event) => {
    state.cornerAngle = Number(event.target.value);
    syncControlLabels();
    scheduleRebuild();
  });

  $("testSize").addEventListener("input", (event) => {
    state.testSize = Number(event.target.value);
    syncControlLabels();
    renderNow();
    scheduleEvaluate();
  });

  for (const [id, key] of [
    ["shiftX", "shiftX"],
    ["shiftY", "shiftY"],
  ]) {
    $(id).addEventListener("input", (event) => {
      state[key] = Number(event.target.value);
      syncControlLabels();
      renderNow();
      scheduleEvaluate();
    });
  }

  for (const tab of document.querySelectorAll(".view-tab")) {
    tab.addEventListener("click", () => setView(tab.dataset.view));
  }

  $("rawField").addEventListener("change", (event) => {
    state.raw = event.target.checked;
    renderNow();
  });

  $("channelTint").addEventListener("change", (event) => {
    state.channelTint = event.target.checked;
    renderNow();
  });

  $("showGrid").addEventListener("change", (event) => {
    state.showGrid = event.target.checked;
    renderNow();
  });

  $("showAnatomy").addEventListener("change", (event) => {
    state.showAnatomy = event.target.checked;
    drawOverlay();
  });

  $("evaluateCurrent").addEventListener("click", () => evaluateCurrent());
  $("runSweep").addEventListener("click", () => runSweep());
  $("exportCsv").addEventListener("click", exportSweepCsv);

  $("fontFile").addEventListener("change", (event) => {
    importFont(event.target.files?.[0]);
    event.target.value = "";
  });

  $("applyFontGlyphs").addEventListener("click", () => {
    generateFontSpecimens(Array.from($("glyphChars").value));
  });

  window.addEventListener("resize", scheduleRender);
  if ("ResizeObserver" in window) {
    new ResizeObserver(scheduleRender).observe($("stage"));
  }
}

async function init() {
  syncControlLabels();
  bindEvents();
  renderGlyphGrid();
  resetSweepTable();

  try {
    renderer = new GlyphRenderer($("glCanvas"));
    setStatus("WebGL2 就绪");
  } catch (error) {
    console.error(error);
    setStatus("WebGL2 不可用", "error");
    $("stageEmpty").hidden = false;
    $("stageEmpty").innerHTML =
      `<strong>WebGL2 不可用</strong><span>${escapeHtml(error.message)}</span>`;
  }

  await new Promise((resolve) => requestAnimationFrame(resolve));
  await rebuildSelected({ resetSweep: false });
}

init();
