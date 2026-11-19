import { analyzeThinShadowEdge, compareEdgeQuality } from "./analysis.js";
import { createSceneMeshes, rayHitsMesh } from "./geometry.js";
import { smoothstep, vec3 } from "./math.js";
import { ShadowRenderer } from "./renderer.js";
import {
  buildShadowVolume,
  LIGHT_DIRECTION,
  measureVolumeCoverage,
} from "./shadow-volume.js";

const canvas = document.querySelector("#viewport");
const renderer = new ShadowRenderer(canvas);
const meshes = createSceneMeshes();

const MESH_META = {
  closed: {
    label: "CLOSED SPHERE",
    hud: "CLOSED SPHERE",
    center: [0, 3.05, 0],
    outside: [9.4, 6.5, 12.2],
    outsideTarget: [0, 1.35, 0.2],
  },
  open: {
    label: "OPEN SURFACE",
    hud: "OPEN SURFACE",
    center: [0, 3.05, 0],
    outside: [9.6, 6.9, 12.4],
    outsideTarget: [0, 1.3, 0],
  },
  plank: {
    label: "THIN PLANK",
    hud: "THIN PLANK",
    center: [0.4, 3.75, 0.1],
    outside: [10.2, 7.7, 13.3],
    outsideTarget: [0, 1.5, 0.4],
  },
};

const state = {
  mode: "stencil",
  meshKey: "closed",
  cameraMode: "outside",
  caps: true,
  zFail: true,
  shadowMapSize: 1024,
  debugMask: false,
  showVolume: false,
  paused: false,
  enterProgress: null,
  animationTime: 0,
};

let volume = null;
let volumeKey = "";
let lastFrame = performance.now();
let coverage = null;
let coverageDirty = true;
let coverageClock = -1;
let quality = null;
let qualityDirty = true;
let qualityBusy = false;
let lastHistogram = null;
let currentCamera = null;
let cameraInside = false;
let statsClock = 0;

const ui = {
  volumeTris: document.querySelector("#volume-tris"),
  meshTris: document.querySelector("#mesh-tris"),
  fillRate: document.querySelector("#fill-rate"),
  fillPixels: document.querySelector("#fill-pixels"),
  stencilNonzero: document.querySelector("#stencil-nonzero"),
  maxCount: document.querySelector("#max-count"),
  histogram: document.querySelector("#histogram"),
  histSource: document.querySelector("#hist-source"),
  meshHud: document.querySelector("#mesh-hud"),
  cameraHud: document.querySelector("#camera-hud"),
  frameHud: document.querySelector("#frame-hud"),
  insideBanner: document.querySelector("#inside-banner"),
  splitLabels: document.querySelector("#split-labels"),
  smapLabel: document.querySelector("#smap-label"),
  statusLine: document.querySelector("#status-line"),
  qualityVerdict: document.querySelector("#quality-verdict"),
  stencilEdge: document.querySelector("#stencil-edge"),
  smapEdge: document.querySelector("#smap-edge"),
  stencilEdgeBar: document.querySelector("#stencil-edge-bar"),
  smapEdgeBar: document.querySelector("#smap-edge-bar"),
  gpuName: document.querySelector("#gpu-name"),
  clock: document.querySelector("#clock"),
  pause: document.querySelector("#pause-toggle"),
  viewportWrap: document.querySelector(".viewport-wrap"),
};

function formatInteger(value) {
  return Number(value).toLocaleString("en-US");
}

function ensureVolume() {
  const key = `${state.meshKey}:${state.caps}`;
  if (key !== volumeKey) {
    volume = buildShadowVolume(meshes[state.meshKey], { caps: state.caps });
    volumeKey = key;
    coverageDirty = true;
  }
  return volume;
}

function insidePosition(meshKey) {
  const center = MESH_META[meshKey].center;
  const y = 1.35;
  const distance = (center[1] - y) / LIGHT_DIRECTION[1];
  const lateral = meshKey === "plank" ? 0 : 1.15;
  const perpendicular = vec3.normalize([LIGHT_DIRECTION[2], 0, -LIGHT_DIRECTION[0]]);
  return [
    center[0] - LIGHT_DIRECTION[0] * distance + perpendicular[0] * lateral,
    y,
    center[2] - LIGHT_DIRECTION[2] * distance + perpendicular[2] * lateral,
  ];
}

function getEnterProgress() {
  if (state.enterProgress !== null) return state.enterProgress;
  const phase = state.animationTime % 12;
  if (phase < 4) return 0;
  if (phase < 6) return smoothstep(0, 1, (phase - 4) / 2);
  if (phase < 8) return 1;
  if (phase < 10) return 1 - smoothstep(0, 1, (phase - 8) / 2);
  return 0;
}

function getCamera() {
  const meta = MESH_META[state.meshKey];
  const outside = meta.outside;
  const outsideTarget = meta.outsideTarget;
  const inside = insidePosition(state.meshKey);
  const insideTarget = state.meshKey === "plank"
    ? [2.55, 0.05, -1.5]
    : [2.1, 0.05, -1.45];
  if (state.cameraMode === "outside") {
    return renderer.getCamera(outside, outsideTarget);
  }
  if (state.cameraMode === "inside") {
    return renderer.getCamera(inside, insideTarget);
  }
  const progress = getEnterProgress();
  const perpendicular = vec3.normalize([LIGHT_DIRECTION[2], 0, -LIGHT_DIRECTION[0]]);
  const enterOffset = state.meshKey === "plank" ? 0.75 : 2.25;
  const start = [
    inside[0] + perpendicular[0] * enterOffset,
    1.65,
    inside[2] + perpendicular[2] * enterOffset,
  ];
  const startTarget = [2.4, 0.6, -0.4];
  return renderer.getCamera(
    vec3.lerp(start, inside, progress),
    vec3.lerp(startTarget, insideTarget, progress),
  );
}

function updateCameraState() {
  currentCamera = getCamera();
  cameraInside = rayHitsMesh(
    meshes[state.meshKey],
    currentCamera.position,
    LIGHT_DIRECTION,
    100,
  );
  ui.insideBanner.classList.toggle("hidden", !cameraInside);
  ui.cameraHud.textContent = cameraInside
    ? "CAMERA INSIDE VOLUME"
    : `CAMERA ${state.cameraMode.toUpperCase()}`;
}

function refreshCoverage(force = false) {
  const now = performance.now();
  const interval = state.cameraMode === "enter" ? 350 : Infinity;
  if (!force && !coverageDirty && now - coverageClock < interval) return;
  coverage = measureVolumeCoverage(
    ensureVolume(),
    getCamera().viewProjection,
    renderer.width,
    renderer.height,
  );
  coverageDirty = false;
  coverageClock = now;
  updateCoverageUi();
}

function updateCoverageUi() {
  if (!coverage) return;
  ui.fillRate.textContent = `${(coverage.coverage * 100).toFixed(1)}%`;
  ui.fillPixels.textContent =
    `${formatInteger(Math.round(coverage.pixels / 1000))}k px · ${coverage.overdraw.toFixed(2)}×`;
}

function updateHistogram(values) {
  if (!values) {
    ui.histogram.replaceChildren();
    for (let bucket = 0; bucket < 10; bucket += 1) {
      const bar = document.createElement("div");
      bar.className = `hist-bar${bucket === 1 ? " hot" : ""}`;
      bar.style.height = "2px";
      bar.innerHTML = `<span>${bucket === 9 ? "9+" : bucket}</span>`;
      ui.histogram.append(bar);
    }
    return;
  }
  const maxValue = Math.max(...values, 1);
  const bars = [...ui.histogram.children];
  values.forEach((value, bucket) => {
    const bar = bars[bucket];
    bar.style.height = `${Math.max(2, (value / maxValue) * 43)}px`;
    bar.title = bucket === 9
      ? `9+ 次（含 255 回绕 / -1）：${formatInteger(value)} px`
      : `${bucket} 次：${formatInteger(value)} px`;
    bar.classList.toggle("hot", bucket > 0 && value === Math.max(...values.slice(1)));
  });
}

function updateStencilUi(values) {
  if (!values) return;
  lastHistogram = values;
  updateHistogram(values);
  const nonzero = values.slice(1).reduce((sum, value) => sum + value, 0);
  let maxBucket = 0;
  values.forEach((value, bucket) => {
    if (bucket > 0 && value > 0) maxBucket = bucket;
  });
  ui.stencilNonzero.textContent = formatInteger(nonzero);
  ui.maxCount.textContent = maxBucket;
  ui.histSource.textContent = "GPU QUERY";
}

function updateStatus() {
  const closed = meshes[state.meshKey].closed;
  const boundary = meshes[state.meshKey].boundaryEdges;
  if (!state.caps) {
    ui.statusLine.textContent = closed
      ? "封帽关闭：闭合体积端点未闭合，相机进入后计数会泄漏。"
      : "封帽关闭：开放网格棱柱端点未封口，模板掩码出现缺损。";
  } else if (cameraInside) {
    ui.statusLine.textContent = state.zFail
      ? "相机在阴影体内：Z-Fail 统计接收点之后的交点，封帽保持正确奇偶性。"
      : "相机在阴影体内：Z-Pass 会漏掉近裁剪面交点，阴影可能翻转。";
  } else if (!closed && state.caps) {
    ui.statusLine.textContent = `开放网格：${formatInteger(volume.triangleCount)} 个三角形，逐片棱柱封帽补偿边界边（${boundary} 条）。`;
  } else {
    ui.statusLine.textContent = "相机在阴影体外：轮廓挤出体积与近/远端封帽组成闭合边界。";
  }
  ui.frameHud.textContent =
    `${state.zFail ? "ZFAIL" : "ZPASS"} · CAPS ${state.caps ? "ON" : "OFF"} · ${formatInteger(volume.triangleCount)} TRI`;
  ui.meshHud.textContent = MESH_META[state.meshKey].hud;
}

function updateQualityUi(result) {
  if (!result) {
    ui.qualityVerdict.textContent = "SELECT PLANK";
    ui.stencilEdge.textContent = "—";
    ui.smapEdge.textContent = "—";
    ui.stencilEdgeBar.style.width = "0%";
    ui.smapEdgeBar.style.width = "0%";
    return;
  }
  ui.stencilEdge.textContent = result.stencilScore.toFixed(2);
  ui.smapEdge.textContent = result.shadowMapScore.toFixed(2);
  ui.stencilEdgeBar.style.width = `${Math.min(100, result.stencilScore / 2.5 * 100)}%`;
  ui.smapEdgeBar.style.width = `${Math.min(100, result.shadowMapScore / 2.5 * 100)}%`;
  ui.qualityVerdict.textContent =
    result.sharper === "stencil" ? "STENCIL SHARPER" : "SHADOW MAP SHARPER";
}

function runQualityAnalysis() {
  if (qualityBusy || !qualityDirty) return;
  if (state.meshKey !== "plank") {
    qualityDirty = false;
    updateQualityUi(null);
    return;
  }
  qualityBusy = true;
  qualityDirty = false;
  const meta = MESH_META.plank;
  const camera = renderer.getCamera(meta.outside, meta.outsideTarget);
  const plankVolume = buildShadowVolume(meshes.plank, { caps: true });
  const meshGpu = renderer.ensureMeshGpu("plank", meshes.plank);
  const stencilMask = renderer.captureMask("stencil", camera, meshGpu, plankVolume, true);
  const shadowMask = renderer.captureMask("shadowmap", camera, meshGpu, plankVolume, true);
  const stencil = analyzeThinShadowEdge(
    stencilMask.mask,
    stencilMask.width,
    stencilMask.height,
  );
  const shadowMap = analyzeThinShadowEdge(
    shadowMask.mask,
    shadowMask.width,
    shadowMask.height,
  );
  quality = compareEdgeQuality(stencil, shadowMap);
  qualityBusy = false;
  updateQualityUi(quality);
}

function drawFrame() {
  updateCameraState();
  const activeVolume = ensureVolume();
  const meshGpu = renderer.ensureMeshGpu(state.meshKey, meshes[state.meshKey]);
  renderer.render({
    mode: state.mode,
    camera: currentCamera,
    meshGpu,
    volume: activeVolume,
    shadowMapSize: state.shadowMapSize,
    zFail: state.zFail,
    debugMask: state.debugMask,
    showVolume: state.showVolume,
  });
  const histogram = renderer.pollHistogram();
  if (histogram !== lastHistogram) updateStencilUi(histogram);
  refreshCoverage();
  updateStatus();
}

function geometryUi() {
  ensureVolume();
  ui.volumeTris.textContent = formatInteger(volume.triangleCount);
  ui.meshTris.textContent =
    `mesh triangles ${formatInteger(meshes[state.meshKey].indices.length / 3)}`;
}

function syncControls() {
  document.querySelectorAll(".mode-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === state.mode);
  });
  document.querySelectorAll("[data-mesh]").forEach((button) => {
    button.classList.toggle("active", button.dataset.mesh === state.meshKey);
  });
  document.querySelectorAll("[data-camera]").forEach((button) => {
    button.classList.toggle("active", button.dataset.camera === state.cameraMode);
  });
  document.querySelector("#caps-input").checked = state.caps;
  document.querySelector("#zfail-input").checked = state.zFail;
  document.querySelector("#smap-size").value = String(state.shadowMapSize);
  document.querySelector("#debug-toggle").setAttribute("aria-pressed", String(state.debugMask));
  document.querySelector("#volume-toggle").setAttribute("aria-pressed", String(state.showVolume));
  ui.pause.classList.toggle("paused", state.paused);
  ui.splitLabels.classList.toggle("hidden", state.mode !== "split");
  ui.smapLabel.textContent = `SHADOW MAP / ${state.shadowMapSize}²`;
  ui.viewportWrap.classList.toggle("split", state.mode === "split");
}

function invalidate(partial) {
  const meshChanged = partial.meshKey !== undefined && partial.meshKey !== state.meshKey;
  Object.assign(state, partial);
  if (meshChanged && state.cameraMode === "enter") state.enterProgress = null;
  volumeKey = "";
  coverageDirty = true;
  qualityDirty = true;
  renderer.requestStats();
  syncControls();
  geometryUi();
  updateCameraState();
  drawFrame();
  refreshCoverage(true);
  updateStatus();
}

document.querySelectorAll(".mode-tab").forEach((button) => {
  button.addEventListener("click", () => invalidate({ mode: button.dataset.mode }));
});

document.querySelectorAll("[data-mesh]").forEach((button) => {
  button.addEventListener("click", () => invalidate({ meshKey: button.dataset.mesh }));
});

document.querySelectorAll("[data-camera]").forEach((button) => {
  button.addEventListener("click", () => {
    state.enterProgress = null;
    invalidate({ cameraMode: button.dataset.camera });
  });
});

document.querySelector("#caps-input").addEventListener("change", (event) => {
  invalidate({ caps: event.target.checked });
});

document.querySelector("#zfail-input").addEventListener("change", (event) => {
  invalidate({ zFail: event.target.checked });
});

document.querySelector("#smap-size").addEventListener("change", (event) => {
  invalidate({ shadowMapSize: Number(event.target.value) });
});

document.querySelector("#debug-toggle").addEventListener("click", () => {
  invalidate({ debugMask: !state.debugMask });
});

document.querySelector("#volume-toggle").addEventListener("click", () => {
  invalidate({ showVolume: !state.showVolume });
});

document.querySelector("#pause-toggle").addEventListener("click", () => {
  state.paused = !state.paused;
  syncControls();
});

function statsSnapshot() {
  const histogram = renderer.histogram ?? lastHistogram;
  const nonzero = histogram
    ? histogram.slice(1).reduce((sum, value) => sum + value, 0)
    : null;
  return {
    mode: state.mode,
    mesh: state.meshKey,
    meshClosed: meshes[state.meshKey].closed,
    boundaryEdges: meshes[state.meshKey].boundaryEdges,
    cameraMode: state.cameraMode,
    cameraInside,
    cameraPosition: currentCamera ? [...currentCamera.position] : null,
    caps: state.caps,
    zFail: state.zFail,
    shadowMapSize: state.shadowMapSize,
    volumeMethod: volume.method,
    meshTriangles: meshes[state.meshKey].indices.length / 3,
    volumeTriangles: volume.triangleCount,
    sideTriangles: volume.sideTriangles,
    capTriangles: volume.capTriangles,
    silhouetteEdges: volume.silhouetteEdges.length,
    fillRate: coverage?.coverage ?? null,
    fillPixels: coverage?.pixels ?? null,
    overdraw: coverage?.overdraw ?? null,
    stencilHistogram: histogram ? [...histogram] : null,
    stencilNonzero: nonzero,
    quality: quality ? {
      stencilScore: quality.stencilScore,
      shadowMapScore: quality.shadowMapScore,
      sharper: quality.sharper,
      improvement: quality.improvement,
      stencil: quality.stencil,
      shadowMap: quality.shadowMap,
    } : null,
  };
}

function renderNow() {
  updateCameraState();
  drawFrame();
  refreshCoverage(true);
  return statsSnapshot();
}

window.__stencilLab = {
  setState(partial) {
    if (partial.enterProgress !== undefined) state.enterProgress = partial.enterProgress;
    invalidate(partial);
    return renderNow();
  },
  setEnterProgress(progress) {
    state.enterProgress = Math.max(0, Math.min(1, progress));
    invalidate({ cameraMode: "enter" });
    return renderNow();
  },
  setAnimationTime(seconds) {
    state.animationTime = seconds;
    state.enterProgress = null;
    if (state.cameraMode === "enter") {
      invalidate({ cameraMode: "enter" });
      return renderNow();
    }
    return statsSnapshot();
  },
  renderNow,
  getStats: statsSnapshot,
  getQuality: () => quality,
  refreshCoverage: () => {
    refreshCoverage(true);
    return coverage;
  },
  captureMask(mode = state.mode) {
    updateCameraState();
    const camera = currentCamera;
    const meshGpu = renderer.ensureMeshGpu(state.meshKey, meshes[state.meshKey]);
    return renderer.captureMask(mode, camera, meshGpu, ensureVolume(), state.zFail);
  },
  getGpuInfo: () => renderer.getInfo(),
  getState: () => ({ ...state }),
  getRenderer: () => renderer,
};

function animate(now) {
  const delta = Math.min(0.05, Math.max(0, (now - lastFrame) / 1000));
  lastFrame = now;
  if (!state.paused) state.animationTime += delta;
  if (state.cameraMode === "enter" && now - statsClock > 450) {
    renderer.requestStats();
    statsClock = now;
  }
  drawFrame();
  if (qualityDirty && !qualityBusy) runQualityAnalysis();
  requestAnimationFrame(animate);
}

geometryUi();
updateHistogram(null);
updateQualityUi(null);
syncControls();
updateCameraState();
renderer.requestStats();
drawFrame();
refreshCoverage(true);
const gpuInfo = renderer.getInfo();
ui.gpuName.textContent = `${gpuInfo.vendor} / ${gpuInfo.renderer}`.slice(0, 94);
lastFrame = performance.now();
requestAnimationFrame(animate);

setInterval(() => {
  const now = new Date();
  ui.clock.textContent = now.toLocaleTimeString("zh-CN", { hour12: false });
}, 1000);
