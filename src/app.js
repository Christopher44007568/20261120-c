import {
  buildContinuitySummary,
  buildConvergence,
  buildDirectionSets,
  summarizeContinuity,
} from "./analysis.js";
import {
  CHART_COLORS,
  drawBoundaryStrip,
  drawDirectionQuadrants,
  drawErrorChart,
  drawMesh,
  drawSeriesChart,
} from "./charts.js";
import { initLTCData, ltcMatrix3, sampleLTCMatrix } from "./ltc.js";
import { meshWireframe, validateScene } from "./mesh.js";
import {
  ROUGHNESS_BOUNDARIES,
  compareImages,
  evaluateBoundaryContinuity,
  imageToRGBA,
  maxSweepStep,
  matrixSweep,
  renderSurface,
} from "./render.js";

const $ = (id) => document.getElementById(id);
const nextFrame = () => new Promise((resolve) => {
  requestAnimationFrame(() => setTimeout(resolve, 0));
});

const state = {
  roughness: 0.12,
  spp: 32,
  seed: 7,
  renderVersion: 0,
  images: {},
  metrics: {},
  continuity: null,
  fixtures: { valid: null, invalid: null },
  sweep: null,
  convergence: null,
  directions: null,
};

let toastTimer = null;

function formatPercent(value, digits = 2) {
  return `${(value * 100).toFixed(digits)}%`;
}

function formatNumber(value, digits = 5) {
  if (!Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function setLoading(loading) {
  document.body.classList.toggle("loading", loading);
}

function blitImage(canvas, image, scale) {
  const context = canvas.getContext("2d");
  const rgba = imageToRGBA(image, scale);
  context.putImageData(new ImageData(rgba, image.width, image.height), 0, 0);
}

function updatePair(prefix, analytic, sampled) {
  const scale = 1 / Math.max(analytic.peak * 1.04, 1e-9);
  blitImage($(`canvas-${prefix}-ltc`), analytic, scale);
  blitImage($(`canvas-${prefix}-mc`), sampled, scale);
  const metrics = compareImages(analytic, sampled, scale);
  state.metrics[prefix] = metrics;
  state.images[`${prefix}-analytic`] = analytic;
  state.images[`${prefix}-sampled`] = sampled;
  state.images[`${prefix}-scale`] = scale;
  $(`metric-${prefix}-iou`).textContent = metrics.shapeIoU.toFixed(3);
  $(`metric-${prefix}-l1`).textContent = formatPercent(metrics.energyError, 2);
  $(`metric-${prefix}-noise`).textContent = formatPercent(metrics.residualStd, 1);
}

async function renderAll() {
  const version = ++state.renderVersion;
  setLoading(true);
  const width = 280;
  const height = 172;
  $("rect-spp-label").textContent = state.spp;
  $("disk-spp-label").textContent = state.spp;
  $("gradient-spp-label").textContent = state.spp;

  await nextFrame();
  const rectAnalytic = renderSurface({
    width,
    height,
    emitter: "rect",
    roughnessMode: "fixed",
    roughness: state.roughness,
    method: "ltc",
  });
  if (version !== state.renderVersion) return;
  const rectSampled = renderSurface({
    width,
    height,
    emitter: "rect",
    roughnessMode: "fixed",
    roughness: state.roughness,
    method: "mc",
    spp: state.spp,
    seed: state.seed,
  });
  if (version !== state.renderVersion) return;
  updatePair("rect", rectAnalytic, rectSampled);

  await nextFrame();
  const diskAnalytic = renderSurface({
    width,
    height,
    emitter: "disk",
    roughnessMode: "fixed",
    roughness: state.roughness,
    method: "ltc",
  });
  if (version !== state.renderVersion) return;
  const diskSampled = renderSurface({
    width,
    height,
    emitter: "disk",
    roughnessMode: "fixed",
    roughness: state.roughness,
    method: "mc",
    spp: state.spp,
    seed: state.seed + 1,
  });
  if (version !== state.renderVersion) return;
  updatePair("disk", diskAnalytic, diskSampled);

  const peakRatio = (state.metrics.rect.peakRatio + state.metrics.disk.peakRatio) / 2;
  $("metric-peak-ratio").textContent =
    `${state.metrics.rect.peakRatio.toFixed(3)} / ${state.metrics.disk.peakRatio.toFixed(3)}` +
    `  (${formatPercent(peakRatio - 1, 1)})`;

  await nextFrame();
  const gradWidth = 620;
  const gradHeight = 168;
  const gradientAnalytic = renderSurface({
    width: gradWidth,
    height: gradHeight,
    emitter: "rect",
    roughnessMode: "gradient",
    method: "ltc",
  });
  if (version !== state.renderVersion) return;
  const gradientSampled = renderSurface({
    width: gradWidth,
    height: gradHeight,
    emitter: "rect",
    roughnessMode: "gradient",
    method: "mc",
    spp: state.spp,
    seed: state.seed + 2,
  });
  if (version !== state.renderVersion) return;
  const gradientScale = 1 / Math.max(gradientAnalytic.peak * 1.04, 1e-9);
  blitImage($("canvas-gradient-ltc"), gradientAnalytic, gradientScale);
  blitImage($("canvas-gradient-mc"), gradientSampled, gradientScale);
  state.images.gradientAnalytic = gradientAnalytic;
  state.images.gradientSampled = gradientSampled;
  state.images.gradientScale = gradientScale;
  state.metrics.gradient = compareImages(gradientAnalytic, gradientSampled, gradientScale);
  $("gradient-jump").textContent = formatPercent(state.continuity.rect.maxContinuousJump, 3);
  $("gradient-quantized").textContent = formatPercent(state.continuity.rect.maxQuantizedJump, 1);
  $("gradient-pill").textContent =
    state.continuity.rect.maxContinuousJump < 0.01 ? "边界零跳变" : "存在跳变";
  $("gradient-pill").className =
    `continuity-pill ${state.continuity.rect.maxContinuousJump < 0.01 ? "ok" : "error"}`;

  setLoading(false);
}

let renderDebounce = null;
function scheduleRender() {
  clearTimeout(renderDebounce);
  renderDebounce = setTimeout(renderAll, 130);
}

function matrixCell(values) {
  return ltcMatrix3(values)
    .map((row) => `[${row.map((value) => `${value >= 0 ? " " : ""}${value.toFixed(3)}`).join(" ")}]`)
    .join("\n");
}

function initMatrixChart() {
  state.sweep = matrixSweep(0.7, 257);
  const channels = [
    { index: 0, label: "a", color: CHART_COLORS.teal },
    { index: 1, label: "b", color: CHART_COLORS.blue },
    { index: 2, label: "c", color: CHART_COLORS.amber },
    { index: 3, label: "d", color: CHART_COLORS.rose },
  ];
  drawSeriesChart($("chart-matrix"), {
    series: channels.map((channel) => ({
      label: `M⁻¹ ${channel.label}`,
      color: channel.color,
      points: state.sweep.map((entry) => [entry.roughness, entry.values[channel.index]]),
    })),
    xLabel: "粗糙度 α",
    yLabel: "矩阵元素",
    yMin: -0.42,
    yMax: 1.42,
    markers: ROUGHNESS_BOUNDARIES.map((entry) => ({ value: entry.roughness })),
  });
  $("matrix-max-step").textContent = `max Δ ${maxSweepStep(state.sweep).toFixed(4)}`;

  const presets = [0.08, 0.24, 0.48, 0.72, 1];
  const body = $("matrix-table").querySelector("tbody");
  body.innerHTML = "";
  for (const roughness of presets) {
    const values = sampleLTCMatrix(roughness, 0.7);
    const determinant = values[0] * values[3] - values[1] * values[2];
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${roughness.toFixed(2)}</td>
      <td>${matrixCell(values)}</td>
      <td>${determinant.toFixed(4)}</td>
    `;
    body.appendChild(row);
  }
  drawBoundaryStrip($("chart-boundary"), state.continuity.rect);
}

function initDirections() {
  state.directions = buildDirectionSets(512, 19);
  drawDirectionQuadrants($("chart-directions"), state.directions);
}

function initConvergence() {
  const rect = buildConvergence("rect", { roughness: 0.24, seeds: 8 });
  const disk = buildConvergence("disk", { roughness: 0.24, seeds: 8 });
  state.convergence = { rect, disk };
  const series = [
    {
      label: "RECT · MC 误差",
      color: CHART_COLORS.amber,
      points: rect.points.map((point) => [point.spp, Math.max(point.relativeError, 1e-7)]),
    },
    {
      label: "DISK · MC 误差",
      color: CHART_COLORS.teal,
      points: disk.points.map((point) => [point.spp, Math.max(point.relativeError, 1e-7)]),
    },
  ];
  drawErrorChart($("chart-error"), series, rect.points.map((point) => point.spp), rect.analytic);
  $("error-rect-analytic").textContent = rect.analytic.toFixed(5);
  $("error-rect-sampled").textContent =
    `${rect.points[rect.points.length - 1].mean.toFixed(5)} · ${formatPercent(rect.points[rect.points.length - 1].relativeError, 2)}`;
  $("error-disk-analytic").textContent = disk.analytic.toFixed(5);
  $("error-disk-sampled").textContent =
    `${disk.points[disk.points.length - 1].mean.toFixed(5)} · ${formatPercent(disk.points[disk.points.length - 1].relativeError, 2)}`;
}

let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    initMatrixChart();
    initDirections();
    initConvergence();
  }, 160);
});

function setFixtureStats(kind, scene, report) {
  const stats = report.mesh.stats;
  const prefix = kind === "valid" ? "valid" : "invalid";
  const container = $(`${prefix}-mesh-stats`);
  container.innerHTML = `
    <span>v <b>${stats.weldedVertices}</b></span>
    <span>f <b>${stats.triangles}</b></span>
    <span>e <b>${stats.edges}</b></span>
    <span>χ <b>${stats.euler}</b></span>
  `;
  const finding = report.valid
    ? "每条边恰好被两个三角形共享；0 条边界边、0 条非流形边，接受。"
    : report.findings.filter((item) => item.startsWith("mesh：")).join(" ");
  $(`${prefix}-finding`).textContent = finding;
  $(`${prefix}-badge`).textContent = report.valid ? "PASS" : "REJECT";
  drawMesh($(`canvas-${prefix}-mesh`), meshWireframe(scene.mesh), report.valid);
}

function setInputStatus(kind) {
  const fixture = state.fixtures[kind];
  if (!fixture) return;
  const { scene, report } = fixture;
  const chip = $("status-validation");
  const chipWrap = chip.parentElement;
  const meshChip = $("status-mesh");
  const meshWrap = meshChip.parentElement;
  chip.textContent = report.valid ? "输入合法" : "输入被拒绝";
  chipWrap.className = `status-chip ${report.valid ? "ok" : "error"}`;
  meshChip.textContent = `${report.mesh.stats.boundaryEdges} boundary edges · χ ${report.mesh.stats.euler}`;
  meshWrap.className = `status-chip ${report.valid ? "" : "error"}`;
  const inputReport = $("input-report");
  inputReport.className = `input-report ${report.valid ? "ok" : "error"}`;
  inputReport.innerHTML = report.valid
    ? `<strong>ACCEPT · ${scene.name}</strong><span>schema、发射体尺寸、粗糙度范围与网格拓扑全部通过。</span>`
    : `<strong>REJECT · ${scene.name}</strong><span>${report.findings.join(" ")}</span>`;
}

async function loadFixture(kind, announce = true) {
  const path = kind === "valid"
    ? "./fixtures/valid-scene.json"
    : "./fixtures/nonwatertight-scene.json";
  const response = await fetch(path);
  if (!response.ok) throw new Error(`无法读取 ${path}`);
  const scene = await response.json();
  const report = validateScene(scene);
  state.fixtures[kind] = { scene, report };
  setFixtureStats(kind, scene, report);
  setInputStatus(kind);
  $("validation-summary").textContent =
    `A：${state.fixtures.valid?.report.valid ? "PASS" : "待载入"} · ` +
    `B：${state.fixtures.invalid?.report.valid ? "PASS" : "REJECT"} · 门禁 = 边界边 / 非流形边 / 绕序 / Euler`;
  if (announce) {
    showToast(report.valid
      ? "合法样例通过：0 条边界边，χ = 2"
      : `非水密样例被拒绝：${report.mesh.stats.boundaryEdges} 条边界边，χ = ${report.mesh.stats.euler}`);
  }
  return state.fixtures[kind];
}

async function initFixtures() {
  try {
    await loadFixture("valid", false);
    await loadFixture("invalid", false);
    setInputStatus("valid");
  } catch (error) {
    $("status-validation").textContent = "样例读取失败";
    $("status-validation").parentElement.className = "status-chip error";
    $("validation-summary").textContent = error.message;
  }
}

function downloadBlob(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function buildReport() {
  const sweep = matrixSweep(0.7, 257);
  const fixtureSummary = {};
  for (const kind of ["valid", "invalid"]) {
    const fixture = state.fixtures[kind];
    if (!fixture) continue;
    fixtureSummary[kind] = {
      name: fixture.scene.name,
      valid: fixture.report.valid,
      findings: fixture.report.findings,
      mesh: fixture.report.mesh,
    };
  }
  return {
    schema: "ltc-area-light-validation/1",
    generatedAt: new Date().toISOString(),
    source: {
      method: "Heitz et al. 2016, Real-Time Polygonal-Light Shading with LTC",
      table: "three.js r170 RectAreaLightTexturesLib, 64x64 RGBA x 2",
      tableSha256: "8e897cb72bfa6a20f7737d21bc9e9d6d47bb1405c2cb067aabe4b02a8ba68263",
    },
    liveState: {
      roughness: state.roughness,
      spp: state.spp,
      seed: state.seed,
      fixedImages: state.metrics,
      gradient: state.metrics.gradient,
    },
    probes: {
      fixedRoughness: 0.24,
      ndotv: state.convergence.rect.ndotv,
      matrix: state.convergence.rect.matrix,
      analyticRect: state.convergence.rect.analytic,
      analyticDisk: state.convergence.disk.analytic,
    },
    continuity: {
      boundaries: ROUGHNESS_BOUNDARIES,
      rect: state.continuity.rect,
      disk: state.continuity.disk,
      summary: summarizeContinuity(state.continuity),
    },
    matrixSweep: sweep.map((entry) => ({
      roughness: entry.roughness,
      a: entry.values[0],
      b: entry.values[1],
      c: entry.values[2],
      d: entry.values[3],
      determinant: entry.values[0] * entry.values[3] - entry.values[1] * entry.values[2],
    })),
    directions: state.directions,
    convergence: state.convergence,
    fixtures: fixtureSummary,
  };
}

function exportReport() {
  const report = buildReport();
  downloadBlob(
    "ltc-validation-report.json",
    `${JSON.stringify(report, null, 2)}\n`,
    "application/json",
  );
  showToast("已导出 JSON：矩阵、方向分布、误差、连续性与网格验收");
}

function exportMatrixCSV() {
  const sweep = matrixSweep(0.7, 1001);
  const lines = ["roughness,ndotv,a,b,c,d,determinant"];
  for (const entry of sweep) {
    const [a, b, c, d] = entry.values;
    const determinant = a * d - b * c;
    lines.push([
      entry.roughness.toFixed(6),
      "0.7",
      a.toFixed(9),
      b.toFixed(9),
      c.toFixed(9),
      d.toFixed(9),
      determinant.toFixed(9),
    ].join(","));
  }
  downloadBlob("ltc-matrix-sweep.csv", `${lines.join("\n")}\n`, "text/csv");
  showToast("已导出 1001 行 LTC 矩阵连续扫描 CSV");
}

function wireControls() {
  $("roughness-range").addEventListener("input", (event) => {
    state.roughness = Number(event.target.value);
    $("roughness-value").textContent = state.roughness.toFixed(2);
    $("fixed-r-label").textContent = state.roughness.toFixed(2);
    scheduleRender();
  });

  $("spp-group").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-spp]");
    if (!button) return;
    state.spp = Number(button.dataset.spp);
    for (const item of $("spp-group").querySelectorAll("button")) {
      item.classList.toggle("active", item === button);
    }
    scheduleRender();
  });

  $("seed-input").addEventListener("change", (event) => {
    state.seed = Math.max(1, Math.round(Number(event.target.value) || 1));
    event.target.value = state.seed;
    scheduleRender();
  });

  $("btn-rerun").addEventListener("click", () => {
    state.seed = (state.seed * 1664525 + 1013904223) >>> 0;
    $("seed-input").value = state.seed;
    scheduleRender();
  });

  $("btn-export-report").addEventListener("click", exportReport);
  $("btn-export-csv").addEventListener("click", exportMatrixCSV);

  $("fixture-valid").addEventListener("click", async () => {
    try {
      await loadFixture("valid");
    } catch (error) {
      showToast(error.message);
    }
  });
  $("fixture-invalid").addEventListener("click", async () => {
    try {
      await loadFixture("invalid");
    } catch (error) {
      showToast(error.message);
    }
  });
  for (const button of document.querySelectorAll("[data-load]")) {
    button.addEventListener("click", async () => {
      try {
        await loadFixture(button.dataset.load);
      } catch (error) {
        showToast(error.message);
      }
    });
  }
}

async function boot() {
  try {
    const response = await fetch("./src/ltc-data.bin");
    if (!response.ok) throw new Error("无法读取 LTC 数据表");
    initLTCData(await response.arrayBuffer());
    state.continuity = buildContinuitySummary();
    initMatrixChart();
    initDirections();
    initConvergence();
    wireControls();
    initFixtures();
    await renderAll();
  } catch (error) {
    setLoading(false);
    $("status-validation").textContent = "初始化失败";
    $("status-validation").parentElement.className = "status-chip error";
    $("validation-summary").textContent = error.message;
    showToast(`${error.message}；请通过 npm start 启动本地服务器`);
    console.error(error);
  }
}

boot();
