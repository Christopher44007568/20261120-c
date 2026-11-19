import {
  analyzePose,
  formatInterval,
  maxSeparation,
  precomputeProofs,
  precomputeTrajectories,
} from "./analysis.js";
import { drawAreaChart, drawTrajectoryChart } from "./charts.js";
import { HemisphereTracker } from "./math.js";
import { MODELS, SCENE_META } from "./models.js";
import { buildSkinningPalette } from "./skinning.js";
import { ViewportRenderer } from "./renderer.js";

const query = new URLSearchParams(window.location.search);
const initialScene = query.get("scene") === "elbow" ? "elbow" : "twist";
const initialMode = ["lbs", "dqs", "error"].includes(query.get("mode")) ? query.get("mode") : "dqs";
const initialAngle = Math.max(0, Math.min(180, Number(query.get("angle") ?? 120)));
const initialState = {
  scene: initialScene,
  mode: initialMode,
  angle: Number.isFinite(initialAngle) ? initialAngle : 120,
  sign: query.get("sign") === "-1" ? -1 : 1,
  playing: query.get("play") === "1",
  direction: 1,
  lastSignJump: 0,
};

const dom = {
  viewport: document.querySelector("#viewport"),
  sceneTabs: [...document.querySelectorAll("[data-scene]")],
  modeTabs: [...document.querySelectorAll("[data-mode]")],
  angleRange: document.querySelector("#angleRange"),
  angleOutput: document.querySelector("#angleOutput"),
  playButton: document.querySelector("#playButton"),
  signButton: document.querySelector("#signButton"),
  signGlyph: document.querySelector("#signGlyph"),
  signState: document.querySelector("#signState"),
  sceneEyebrow: document.querySelector("#sceneEyebrow"),
  sceneTitle: document.querySelector("#sceneTitle"),
  sceneSubtitle: document.querySelector("#sceneSubtitle"),
  statePill: document.querySelector("#statePill"),
  inspectorSummary: document.querySelector("#inspectorSummary"),
  lbsArea: document.querySelector("#lbsArea"),
  dqsArea: document.querySelector("#dqsArea"),
  lbsAreaNote: document.querySelector("#lbsAreaNote"),
  dqsAreaNote: document.querySelector("#dqsAreaNote"),
  maxError: document.querySelector("#maxError"),
  signJump: document.querySelector("#signJump"),
  areaChart: document.querySelector("#areaChart"),
  trajectoryChart: document.querySelector("#trajectoryChart"),
  areaCaption: document.querySelector("#areaCaption"),
  trajectoryCaption: document.querySelector("#trajectoryCaption"),
  heatLegend: document.querySelector("#heatLegend"),
  heatMaxLabel: document.querySelector("#heatMaxLabel"),
  heatMid: document.querySelector("#heatMid"),
  bindProof: document.querySelector("#bindProof"),
  signProof: document.querySelector("#signProof"),
  orphanProof: document.querySelector("#orphanProof"),
  sharedProof: document.querySelector("#sharedProof"),
  lbsInterval: document.querySelector("#lbsInterval"),
  dqsInterval: document.querySelector("#dqsInterval"),
  lbsIntervalNote: document.querySelector("#lbsIntervalNote"),
  dqsIntervalNote: document.querySelector("#dqsIntervalNote"),
  fpsLabel: document.querySelector("#fpsLabel"),
  errorToast: document.querySelector("#errorToast"),
};

const sceneCache = new Map();
const sceneTrackers = new Map();
let renderer;
let current = null;
let lastFrame = performance.now();
let fpsFrames = 0;
let fpsTime = 0;

function getSceneData(scene) {
  if (!sceneCache.has(scene)) {
    const model = MODELS[scene];
    sceneCache.set(scene, {
      model,
      trajectories: precomputeTrajectories(model),
      proofs: precomputeProofs(model),
    });
    sceneTrackers.set(scene, new HemisphereTracker());
  }
  return sceneCache.get(scene);
}

function activeTracker(scene = initialState.scene) {
  if (!sceneTrackers.has(scene)) sceneTrackers.set(scene, new HemisphereTracker());
  return sceneTrackers.get(scene);
}

function rebuildPose() {
  const data = getSceneData(initialState.scene);
  const angle = (initialState.angle / 180) * Math.PI;
  const palette = buildSkinningPalette(data.model.rig, angle, {
    sign: initialState.sign,
    tracker: activeTracker(),
  });
  const analysis = analyzePose(data.model, palette, palette);
  analysis.angle = angle;
  current = { ...data, palette, analysis };
  renderer.render({
    model: data.model,
    palette,
    mode: initialState.mode,
    analysis,
    heatMax: data.model.radius * 1.3,
  });
  updateInterface();
}

function selectScene(scene) {
  if (scene === initialState.scene) return;
  initialState.scene = scene;
  activeTracker(scene).reset();
  const data = getSceneData(scene);
  renderer.setScene(data.model, data.trajectories);
  rebuildPose();
}

function selectMode(mode) {
  if (mode === initialState.mode) return;
  initialState.mode = mode;
  rebuildPose();
}

function setAngle(angle) {
  initialState.angle = Math.max(0, Math.min(180, angle));
  rebuildPose();
}

function toggleSign() {
  const previous = current.analysis.positions.dqs;
  initialState.sign *= -1;
  rebuildPose();
  initialState.lastSignJump = maxSeparation(previous, current.analysis.positions.dqs);
  updateInterface();
}

function togglePlay() {
  initialState.playing = !initialState.playing;
  updateInterface();
}

function updateInterface() {
  if (!current) return;
  const { model, proofs, trajectories, analysis } = current;
  const angle = initialState.angle;
  const progress = (angle / 180) * 100;
  dom.sceneTabs.forEach((button) => button.classList.toggle("is-active", button.dataset.scene === initialState.scene));
  dom.modeTabs.forEach((button) => button.classList.toggle("is-active", button.dataset.mode === initialState.mode));
  dom.angleRange.value = angle.toFixed(1);
  dom.angleRange.style.setProperty("--range-progress", `${progress}%`);
  dom.angleOutput.textContent = `${angle.toFixed(1)}°`;
  dom.playButton.classList.toggle("is-playing", initialState.playing);
  dom.signGlyph.textContent = initialState.sign > 0 ? "+q" : "−q";
  dom.signState.textContent = initialState.sign > 0 ? "翻转无闪跳" : "已翻转 · 姿态不变";
  dom.sceneEyebrow.textContent = `SCENE 0${initialState.scene === "twist" ? 1 : 2} · ${model.kind.toUpperCase()}`;
  dom.sceneTitle.textContent = model.label;
  dom.sceneSubtitle.textContent = model.subtitle;
  dom.heatLegend.hidden = initialState.mode !== "error";
  dom.heatMaxLabel.textContent = (model.radius * 1.3).toFixed(2);
  dom.heatMid.textContent = (model.radius * 0.65).toFixed(2);
  dom.areaCaption.textContent = `${angle.toFixed(0)}° 剖面`;
  dom.trajectoryCaption.textContent = model.projection === "YZ" ? "Y–Z 侧视" : "X–Y 顶视";
  dom.statePill.textContent = angle < 0.05 ? "绑定姿态" : initialState.mode === "error" ? "误差诊断" : initialState.mode.toUpperCase();
  dom.inspectorSummary.textContent = summaryFor(modeSummary(initialState.mode));

  const lbsRatio = Math.abs(analysis.mid.lbsAreaRatio);
  const dqsRatio = Math.abs(analysis.mid.dqsAreaRatio);
  dom.lbsArea.textContent = `${(lbsRatio * 100).toFixed(1)}%`;
  dom.dqsArea.textContent = `${(dqsRatio * 100).toFixed(1)}%`;
  dom.lbsAreaNote.textContent = lbsRatio < 0.999 ? `收缩 ${((1 - lbsRatio) * 100).toFixed(1)}%` : "无截面收缩";
  dom.dqsAreaNote.textContent = dqsRatio > 0.999 ? "截面保持" : `偏差 ${((1 - dqsRatio) * 100).toFixed(2)}%`;
  dom.maxError.textContent = analysis.maxError.toFixed(4);
  dom.signJump.textContent = initialState.lastSignJump.toExponential(1);
  dom.bindProof.textContent = `LBS ${proofs.bindLbs.toExponential(1)} · DQS ${proofs.bindDqs.toExponential(1)}`;
  dom.signProof.textContent = `最大跳变 ${proofs.signJumpMax.toExponential(1)}`;
  dom.orphanProof.textContent = `${proofs.orphan.count} 个 · 偏差 ${proofs.orphan.maxDeviation.toExponential(1)}`;
  dom.sharedProof.textContent = `${model.rig.bindMatrices.length} 关节 · ${model.blendVertexCount} 混合顶点`;

  const lbsInterval = analysis.intervals.lbsArea ?? { start: model.blendStart, end: model.blendEnd };
  const dqsInterval = analysis.intervals.dqsArea ?? { start: model.blendStart, end: model.blendEnd };
  dom.lbsInterval.textContent = formatInterval(lbsInterval);
  dom.dqsInterval.textContent = formatInterval(dqsInterval);
  const minLbs = Math.min(...analysis.lbsAreaRatio);
  dom.lbsIntervalNote.textContent = minLbs < 0.999 ? `截面收缩 · 最低 ${(minLbs * 100).toFixed(1)}%` : "刚体区无收缩";
  dom.dqsIntervalNote.textContent = `保形扭转 · 面积 ${(Math.min(...analysis.dqsAreaRatio) * 100).toFixed(1)}%`;

  drawAreaChart(dom.areaChart, model, analysis);
  drawTrajectoryChart(dom.trajectoryChart, model, trajectories, analysis);
}

function modeSummary(mode) {
  if (mode === "lbs") return "线性矩阵加权：中段截面在极限角度塌缩，但刚体区保持精确。";
  if (mode === "dqs") return "双四元数混合：截面积保持，探针轨迹为刚体旋转弧线。";
  return "热图显示同一顶点在两条路径下的三维距离；紫黑为一致，亮黄为强分歧。";
}

function summaryFor(text) {
  return text;
}

function installEvents() {
  dom.sceneTabs.forEach((button) => button.addEventListener("click", () => selectScene(button.dataset.scene)));
  dom.modeTabs.forEach((button) => button.addEventListener("click", () => selectMode(button.dataset.mode)));
  dom.angleRange.addEventListener("input", () => setAngle(Number(dom.angleRange.value)));
  dom.playButton.addEventListener("click", togglePlay);
  dom.signButton.addEventListener("click", toggleSign);
  window.addEventListener("resize", () => {
    if (current) {
      drawAreaChart(dom.areaChart, current.model, current.analysis);
      drawTrajectoryChart(dom.trajectoryChart, current.model, current.trajectories, current.analysis);
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.target instanceof HTMLInputElement) return;
    if (event.code === "Space") {
      event.preventDefault();
      togglePlay();
    }
    if (event.key.toLowerCase() === "q") toggleSign();
    if (event.key === "1") selectMode("lbs");
    if (event.key === "2") selectMode("dqs");
    if (event.key === "3") selectMode("error");
  });
}

function frame(now) {
  const delta = Math.min(0.05, (now - lastFrame) / 1000);
  lastFrame = now;
  if (initialState.playing) {
    let next = initialState.angle + delta * 34 * initialState.direction;
    if (next >= 180) {
      next = 180;
      initialState.direction = -1;
    } else if (next <= 0) {
      next = 0;
      initialState.direction = 1;
    }
    initialState.angle = next;
    rebuildPose();
  } else if (current) {
    renderer.render({
      model: current.model,
      palette: current.palette,
      mode: initialState.mode,
      analysis: current.analysis,
      heatMax: current.model.radius * 1.3,
    });
  }
  fpsFrames += 1;
  fpsTime += delta;
  if (fpsTime >= 0.55) {
    dom.fpsLabel.textContent = `${Math.round(fpsFrames / fpsTime)} FPS`;
    fpsFrames = 0;
    fpsTime = 0;
  }
  requestAnimationFrame(frame);
}

function initialize() {
  try {
    renderer = new ViewportRenderer(dom.viewport);
    const data = getSceneData(initialState.scene);
    renderer.setScene(data.model, data.trajectories);
    rebuildPose();
    installEvents();
    initialState.lastSignJump = data.proofs.signJumpMax;
    updateInterface();
    window.__DQS_LAB__ = {
      getState: () => ({ ...initialState, angle: initialState.angle }),
      getMetrics: () => ({ ...current.analysis, proofs: current.proofs, model: current.model }),
      setState: (next) => {
        if (next.scene && next.scene !== initialState.scene) selectScene(next.scene);
        if (next.mode) selectMode(next.mode);
        if (typeof next.sign === "number") {
          initialState.sign = next.sign < 0 ? -1 : 1;
          activeTracker().reset();
          rebuildPose();
        }
        if (typeof next.angle === "number") setAngle(next.angle);
      },
      proofs: () => sceneCache.get(initialState.scene)?.proofs,
      renderer,
    };
    requestAnimationFrame(frame);
  } catch (error) {
    console.error(error);
    dom.errorToast.textContent = error.message;
    dom.errorToast.hidden = false;
  }
}

initialize();
