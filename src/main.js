import { ANALYSIS_SIZE, analyzeNoisePair } from "./analysis.js";
import { FRAGMENT_SHADER } from "./noise-shader.js";
import { NOISE_NAMES, NoiseRenderer } from "./renderer.js";

const NOISE_COLORS = ["#ff7350", "#b9a8ff", "#7ce3bd"];
const ANALYSIS_DELAY = 380;

const elements = {
  canvas: document.querySelector("#noise-canvas"),
  frame: document.querySelector("#matrix-frame"),
  status: document.querySelector("#render-status"),
  footerStatus: document.querySelector("#footer-status"),
  fieldReadout: document.querySelector("#field-readout"),
  gpuLabel: document.querySelector("#gpu-label"),
  warpToggle: document.querySelector("#warp-toggle"),
  warpLabel: document.querySelector("#warp-state-label"),
  warpNote: document.querySelector("#warp-note"),
  octaves: document.querySelector("#octaves"),
  octavesValue: document.querySelector("#octaves-value"),
  scale: document.querySelector("#scale"),
  scaleValue: document.querySelector("#scale-value"),
  warp: document.querySelector("#warp"),
  warpValue: document.querySelector("#warp-value"),
  gain: document.querySelector("#gain"),
  gainValue: document.querySelector("#gain-value"),
  seedButton: document.querySelector("#seed-button"),
  snapshotButton: document.querySelector("#snapshot-button"),
  matrixSettings: document.querySelector("#matrix-settings"),
  seedReadout: document.querySelector("#seed-readout"),
  exportButton: document.querySelector("#export-button"),
  spectrum: document.querySelector("#spectrum-chart"),
  spectrumNote: document.querySelector("#spectrum-note"),
  timingBars: document.querySelector("#timing-bars"),
  timingMethod: document.querySelector("#timing-method"),
  timingNote: document.querySelector("#timing-note"),
  anisotropy: document.querySelector("#anisotropy-plots"),
  verdict: document.querySelector("#audit-verdict"),
  detailGain: document.querySelector("#detail-gain"),
  hfRatio: document.querySelector("#hf-ratio"),
  artifactScore: document.querySelector("#artifact-score"),
  auditRows: [...document.querySelectorAll(".audit-row")],
  shaderCode: document.querySelector("#shader-code code"),
};

const state = {
  warped: true,
  octaves: 5,
  scale: 4.2,
  warp: 0.34,
  gain: 0.52,
  seed: 0x2a6f,
  seedX: 18.631,
  seedY: 7.274,
  time: 0.4,
};

let renderer;
let metrics = [];
let timings = [];
let latestReport = null;
let analysisTimer = 0;
let analysisToken = 0;
let renderFrame = 0;

function params() {
  return { ...state };
}

function formatPercent(value, digits = 1) {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(digits)}%`;
}

function formatMs(value) {
  return `${value.toFixed(value < 10 ? 2 : 1)} ms`;
}

function setStatus(text, tone = "mint") {
  elements.status.textContent = text;
  elements.status.style.color = tone === "warn" ? "var(--yellow)" : "var(--mint)";
}

function updateSliderFill(input) {
  const min = Number(input.min);
  const max = Number(input.max);
  const value = Number(input.value);
  input.style.setProperty("--fill", `${((value - min) / (max - min)) * 100}%`);
}

function syncControls() {
  elements.octaves.value = state.octaves;
  elements.scale.value = state.scale;
  elements.warp.value = state.warp;
  elements.gain.value = state.gain;
  elements.octavesValue.value = state.octaves;
  elements.scaleValue.value = state.scale.toFixed(1);
  elements.warpValue.value = state.warp.toFixed(2);
  elements.gainValue.value = state.gain.toFixed(2);
  elements.warpToggle.setAttribute("aria-pressed", String(state.warped));
  elements.warpLabel.textContent = state.warped ? "开启 · 两轴偏移" : "关闭 · 原始 fBm";
  elements.warpNote.textContent = state.warped ? "域扭曲当前开启。" : "域扭曲当前关闭。";
  elements.seedReadout.textContent = `0x${state.seed.toString(16).toUpperCase().padStart(4, "0")}`;
  elements.fieldReadout.textContent = `512 × 512 · ${state.octaves} OCT`;
  elements.matrixSettings.textContent =
    `${state.octaves} OCT · GAIN ${state.gain.toFixed(2)} · ` +
    (state.warped ? `WARP ${state.warp.toFixed(2)}` : "WARP OFF");
  for (const input of [elements.octaves, elements.scale, elements.warp, elements.gain]) {
    updateSliderFill(input);
  }
}

function renderMatrix() {
  if (!renderer || renderFrame) return;
  renderFrame = requestAnimationFrame(() => {
    renderFrame = 0;
    renderer.renderMatrix(params());
  });
}

function scheduleAnalysis(immediate = false) {
  window.clearTimeout(analysisTimer);
  latestReport = null;
  if (immediate) {
    runAnalysis();
    return;
  }
  analysisTimer = window.setTimeout(runAnalysis, ANALYSIS_DELAY);
}

function updateParameter(key, value) {
  state[key] = value;
  syncControls();
  renderMatrix();
  scheduleAnalysis();
}

function attachControlEvents() {
  elements.warpToggle.addEventListener("click", () => {
    state.warped = !state.warped;
    syncControls();
    renderMatrix();
    scheduleAnalysis(true);
  });

  elements.octaves.addEventListener("input", (event) => {
    updateParameter("octaves", Number(event.currentTarget.value));
  });
  elements.scale.addEventListener("input", (event) => {
    updateParameter("scale", Number(event.currentTarget.value));
  });
  elements.warp.addEventListener("input", (event) => {
    updateParameter("warp", Number(event.currentTarget.value));
  });
  elements.gain.addEventListener("input", (event) => {
    updateParameter("gain", Number(event.currentTarget.value));
  });

  elements.seedButton.addEventListener("click", () => {
    state.seed = crypto.getRandomValues(new Uint16Array(1))[0];
    state.seedX = 3.17 + (state.seed % 997) * 0.137;
    state.seedY = 1.43 + Math.floor(state.seed / 997) * 0.293;
    syncControls();
    renderMatrix();
    scheduleAnalysis(true);
  });

  elements.exportButton.addEventListener("click", exportReport);
  elements.snapshotButton.addEventListener("click", exportSnapshot);
}

function boot() {
  elements.shaderCode.textContent = FRAGMENT_SHADER;
  syncControls();
  attachControlEvents();
  try {
    renderer = new NoiseRenderer(elements.canvas);
    renderer.renderMatrix(params());
    const software = /swiftshader|llvmpipe|software/i.test(renderer.info.renderer);
    elements.gpuLabel.textContent = software
      ? `软件光栅化 · ${renderer.info.renderer}`
      : `GPU · ${renderer.info.renderer}`;
    elements.timingMethod.textContent = software ? "SW GPU" : "GPU";
    elements.footerStatus.textContent = software ? "SOFTWARE WEBGL2 SESSION" : "LOCAL GPU SESSION";
    setStatus("GPU 就绪 · 正在生成九宫格");
    scheduleAnalysis(true);
  } catch (error) {
    console.error(error);
    setStatus(`WebGL2 初始化失败：${error.message}`, "warn");
    elements.spectrumNote.textContent = "无法建立 WebGL2 上下文，分析暂不可用。";
  }

  const resizeObserver = new ResizeObserver(() => {
    if (!renderer) return;
    renderer.renderMatrix(params());
    drawSpectrum();
    drawAnisotropy();
  });
  resizeObserver.observe(elements.frame);
}

boot();

async function runAnalysis() {
  if (!renderer) return;
  const token = ++analysisToken;
  const signature = JSON.stringify(params());
  setStatus("分析中 · GPU 读回 6 个标量场");
  elements.spectrumNote.textContent = "正在读回 256² 标量场并计算径向 FFT…";
  elements.verdict.textContent = "分析中";
  elements.verdict.className = "verdict-pill";
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  if (token !== analysisToken) return;

  try {
    const nextMetrics = [];
    for (let noiseId = 0; noiseId < 3; noiseId++) {
      if (token !== analysisToken) return;
      const smooth = renderer.readField(noiseId, false, ANALYSIS_SIZE, params());
      const warped = renderer.readField(noiseId, true, ANALYSIS_SIZE, params());
      nextMetrics.push(analyzeNoisePair(smooth, warped));
      setStatus(`分析中 · ${NOISE_NAMES[noiseId]} 频谱完成`);
      await new Promise((resolve) => setTimeout(resolve, 0));
    }

    const nextTimings = [];
    for (let noiseId = 0; noiseId < 3; noiseId++) {
      if (token !== analysisToken) return;
      const warpedTime = await renderer.benchmark(noiseId, true, 512, params(), 4);
      const smoothTime = await renderer.benchmark(noiseId, false, 512, params(), 4);
      nextTimings.push({ warped: warpedTime, smooth: smoothTime });
      setStatus(`计时中 · ${NOISE_NAMES[noiseId]} 完成`);
      await new Promise((resolve) => setTimeout(resolve, 0));
    }

    if (token !== analysisToken || signature !== JSON.stringify(params())) return;
    metrics = nextMetrics;
    timings = nextTimings;
    latestReport = buildReport();
    updateTimingUI();
    updateAuditUI();
    drawSpectrum();
    drawAnisotropy();
    renderer.renderMatrix(params());
    setStatus("分析完成 · 域扭曲已审计");
    elements.gpuLabel.textContent = /swiftshader|llvmpipe|software/i.test(renderer.info.renderer)
      ? `软件光栅化 · ${renderer.info.renderer}`
      : `GPU · ${renderer.info.renderer}`;
  } catch (error) {
    console.error(error);
    setStatus(`分析失败：${error.message}`, "warn");
    elements.spectrumNote.textContent = "GPU 读回或频谱计算失败，请刷新后重试。";
  }
}

function updateTimingUI() {
  const maxTime = Math.max(...timings.flatMap((item) => [item.warped, item.smooth]), 0.01);
  elements.timingBars.replaceChildren();

  timings.forEach((timing, index) => {
    const row = document.createElement("div");
    row.className = "timing-bar";
    row.innerHTML = `<span>${NOISE_NAMES[index].toUpperCase()}</span><i><b></b></i><em>${timing.warped.toFixed(2)}</em>`;
    const bar = row.querySelector("b");
    bar.style.background = NOISE_COLORS[index];
    bar.style.width = `${Math.max(4, (timing.warped / maxTime) * 100)}%`;
    elements.timingBars.append(row);

    const key = NOISE_NAMES[index].toLowerCase();
    document.querySelector(`#time-${key}-on`).textContent = formatMs(timing.warped);
    document.querySelector(`#time-${key}-off`).textContent = formatMs(timing.smooth);
    const cost = timing.smooth > 0 ? timing.warped / timing.smooth : 1;
    document.querySelector(`#cost-${key}`).textContent = `${cost.toFixed(2)}×`;
  });

  const maxDetail = Math.max(...metrics.map((metric) => Math.abs(metric.detailGain)), 0.01);
  const slopes = metrics.map((metric) => Math.abs(metric.spectralSlope - metric.spectralSlopeSmooth));
  const averageTail = metrics.reduce((sum, metric) => sum + metric.tailRatio, 0) / metrics.length;
  elements.timingNote.textContent =
    `512 × 512 px · ${state.octaves} octaves · 4 次 GPU 计时查询中位数。` +
    ` 最大细节变化 ${formatPercent(maxDetail)}；谱斜率偏移 ≤ ${Math.max(...slopes).toFixed(2)} dB/decade。`;
  elements.spectrumNote.textContent =
    `域扭曲后高频尾能量为原始场的 ${averageTail.toFixed(2)}×；256² · Hann 窗 · 径向平均功率谱。`;
  elements.timingMethod.textContent = renderer.timerExt ? "GPU TIMER" : "SYNC FALLBACK";
}

function updateAuditUI() {
  const averageGain = metrics.reduce((sum, metric) => sum + metric.detailGain, 0) / metrics.length;
  const meanTail = metrics.reduce((sum, metric) => sum + metric.tailRatio, 0) / metrics.length;
  const worstArtifact = Math.max(...metrics.map((metric) => metric.artifactScore));
  const allDetailsGrew = metrics.every((metric) => metric.detailGain > 0.01);
  const pass = allDetailsGrew && worstArtifact < 2.4;

  elements.detailGain.textContent = formatPercent(averageGain);
  elements.hfRatio.textContent = `${meanTail.toFixed(2)}×`;
  elements.artifactScore.textContent = worstArtifact.toFixed(2);
  elements.verdict.textContent = pass ? "PASS · 细节增强 / 无尖峰" : "CHECK · 见频谱";
  elements.verdict.className = `verdict-pill ${pass ? "pass" : "warn"}`;

  const { auditRows } = elements;
  metrics.forEach((metric, index) => {
    const bar = auditRows[index].querySelector("b");
    const gain = metric.detailGain;
    bar.style.width = `${Math.max(3, Math.min(100, (gain / 0.5) * 100))}%`;
    bar.style.background = NOISE_COLORS[index];
    auditRows[index].querySelector("em").textContent =
      `${formatPercent(gain, 0)} · ${metric.artifactScore.toFixed(2)}`;
    const key = NOISE_NAMES[index].toLowerCase();
    const note = document.querySelector(`#${key}-note`);
    if (note) {
      note.textContent =
        `细节 ${formatPercent(gain, 0)} · 各向异性 ${metric.anisotropy.toFixed(3)} · ` +
        `斜率 ${metric.spectralSlope.toFixed(2)}`;
    }
  });
}

function buildReport() {
  return {
    generatedAt: new Date().toISOString(),
    parameters: { ...state },
    renderer: renderer.info,
    benchmark: timings.map((timing, index) => ({
      noise: NOISE_NAMES[index],
      milliseconds: { warped: timing.warped, unwarped: timing.smooth },
      costMultiplier: timing.smooth > 0 ? timing.warped / timing.smooth : 1,
    })),
    analysis: metrics.map((metric, index) => ({
      noise: NOISE_NAMES[index],
      detailGain: metric.detailGain,
      highFrequencyTailRatio: metric.tailRatio,
      artifactScore: metric.artifactScore,
      spectralSlope: metric.spectralSlope,
      spectralSlopeUnwarped: metric.spectralSlopeSmooth,
      anisotropy: metric.anisotropy,
      anisotropyUnwarped: metric.anisotropySmooth,
      orientationDegrees: metric.orientation,
      warpedSpectrum: metric.warpedSpectrum.map(({ frequency, power }) => ({ frequency, power })),
      unwarpedSpectrum: metric.smoothSpectrum.map(({ frequency, power }) => ({ frequency, power })),
    })),
  };
}

function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportReport() {
  if (!latestReport) {
    setStatus("分析尚未完成，请稍后再导出", "warn");
    return;
  }
  downloadBlob(JSON.stringify(latestReport, null, 2), "noise-field-report.json", "application/json");
  setStatus("实验报告已导出");
}

function exportSnapshot() {
  if (!renderer) return;
  renderer.renderMatrix(params());
  renderer.canvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `noise-field-${state.seed.toString(16)}.png`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setStatus("九宫格快照已导出");
  }, "image/png");
}

function prepareCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.round(rect.width * dpr);
  const height = Math.round(rect.height * dpr);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const context = canvas.getContext("2d");
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.clearRect(0, 0, rect.width, rect.height);
  return { context, width: rect.width, height: rect.height };
}

function frequencyToX(frequency, left, width) {
  return left + (Math.log(frequency / 0.004) / Math.log(0.5 / 0.004)) * width;
}

function decibelsToY(db, top, height) {
  return top + ((4 - db) / 68) * height;
}

function drawSpectrum() {
  const prepared = prepareCanvas(elements.spectrum);
  if (!prepared) return;
  const { context, width, height } = prepared;
  const margin = { top: 27, right: 11, bottom: 11, left: 39 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;

  context.font = '8px "DejaVu Sans Mono", monospace';
  context.textBaseline = "middle";

  for (let db = 0; db >= -60; db -= 12) {
    const y = decibelsToY(db, margin.top, plotHeight);
    context.strokeStyle = db === 0 ? "rgba(238,232,220,0.15)" : "rgba(238,232,220,0.065)";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(margin.left, y + 0.5);
    context.lineTo(width - margin.right, y + 0.5);
    context.stroke();
    context.fillStyle = "rgba(146,139,127,0.72)";
    context.textAlign = "right";
    context.fillText(db === 0 ? "0 dB" : `${db}`, margin.left - 7, y);
  }

  for (const frequency of [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5]) {
    const x = frequencyToX(frequency, margin.left, plotWidth);
    context.strokeStyle = frequency === 0.5 ? "rgba(238,232,220,0.14)" : "rgba(238,232,220,0.045)";
    context.beginPath();
    context.moveTo(x + 0.5, margin.top);
    context.lineTo(x + 0.5, margin.top + plotHeight);
    context.stroke();
  }

  const tailX = frequencyToX(0.22, margin.left, plotWidth);
  context.setLineDash([3, 4]);
  context.strokeStyle = "rgba(231,211,106,0.38)";
  context.beginPath();
  context.moveTo(tailX, margin.top);
  context.lineTo(tailX, margin.top + plotHeight);
  context.stroke();
  context.setLineDash([]);
  context.fillStyle = "rgba(231,211,106,0.68)";
  context.textAlign = "left";
  context.fillText("HF TAIL", tailX + 5, margin.top + 8);

  if (!metrics.length) {
    context.fillStyle = "rgba(146,139,127,0.72)";
    context.textAlign = "center";
    context.fillText("正在采集频谱…", width / 2, height / 2);
    return;
  }

  metrics.forEach((metric, index) => {
    const drawCurve = (spectrum, alpha, dashed) => {
      context.beginPath();
      spectrum.forEach((point, pointIndex) => {
        const x = frequencyToX(point.frequency, margin.left, plotWidth);
        const y = decibelsToY(point.db, margin.top, plotHeight);
        if (pointIndex === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
      context.strokeStyle = NOISE_COLORS[index];
      context.globalAlpha = alpha;
      context.lineWidth = dashed ? 1 : 1.55;
      context.setLineDash(dashed ? [3, 4] : []);
      context.stroke();
      context.setLineDash([]);
      context.globalAlpha = 1;
    };
    drawCurve(metric.smoothSpectrum, 0.3, true);
    drawCurve(metric.warpedSpectrum, 0.92, false);
  });

  context.textAlign = "left";
  context.textBaseline = "top";
  metrics.forEach((metric, index) => {
    const x = margin.left + 4 + index * 88;
    context.fillStyle = NOISE_COLORS[index];
    context.fillRect(x, 5, 7, 2);
    context.fillStyle = "rgba(201,194,180,0.8)";
    context.fillText(`P ${NOISE_NAMES[index].toUpperCase()}`, x + 12, 1);
  });
}

function drawAnisotropy() {
  elements.anisotropy.replaceChildren();
  if (!metrics.length) {
    const placeholder = document.createElement("p");
    placeholder.className = "panel-footnote";
    placeholder.textContent = "正在计算结构张量…";
    elements.anisotropy.append(placeholder);
    return;
  }

  metrics.forEach((metric, index) => {
    const item = document.createElement("div");
    item.className = "anisotropy-item";
    item.innerHTML = `
      <header><b>${NOISE_NAMES[index].toUpperCase()}</b><span>${metric.anisotropy.toFixed(3)}</span></header>
      <canvas></canvas>
      <p><span>主轴</span><strong>${metric.orientation.toFixed(1)}°</strong></p>
    `;
    elements.anisotropy.append(item);
    const canvas = item.querySelector("canvas");
    drawRose(canvas, metric.histogram, metric.histogramSmooth, NOISE_COLORS[index]);
  });
}

function drawRose(canvas, histogram, smoothHistogram, color) {
  const size = 190;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = size * dpr;
  canvas.height = size * dpr;
  const context = canvas.getContext("2d");
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  const center = size / 2;
  const radius = size * 0.41;

  context.strokeStyle = "rgba(238,232,220,0.1)";
  context.lineWidth = 1;
  for (const scale of [0.33, 0.66, 1]) {
    context.beginPath();
    context.arc(center, center, radius * scale, 0, Math.PI * 2);
    context.stroke();
  }
  for (let i = 0; i < 6; i++) {
    const angle = (i / 6) * Math.PI * 2;
    context.beginPath();
    context.moveTo(center, center);
    context.lineTo(center + Math.cos(angle) * radius, center + Math.sin(angle) * radius);
    context.stroke();
  }

  const drawShape = (values, fillAlpha, strokeAlpha, dashed) => {
    context.beginPath();
    values.forEach((value, bin) => {
      const angle = -Math.PI + ((bin + 0.5) / values.length) * Math.PI * 2;
      const scaledRadius = radius * (0.08 + value * 0.92);
      const x = center + Math.cos(angle) * scaledRadius;
      const y = center + Math.sin(angle) * scaledRadius;
      if (bin === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.closePath();
    context.fillStyle = color;
    context.globalAlpha = fillAlpha;
    context.fill();
    context.strokeStyle = color;
    context.globalAlpha = strokeAlpha;
    context.setLineDash(dashed ? [2, 3] : []);
    context.stroke();
    context.setLineDash([]);
    context.globalAlpha = 1;
  };

  drawShape(smoothHistogram, 0, 0.28, true);
  drawShape(histogram, 0.18, 0.92, false);
  context.fillStyle = color;
  context.beginPath();
  context.arc(center, center, 1.5, 0, Math.PI * 2);
  context.fill();
}
