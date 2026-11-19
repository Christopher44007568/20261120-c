import {
  projectPickToScreen,
  measureRelocationJump,
  measureThinLineJitter,
  samplePick,
} from "./metrics.js";
import {
  HANGARS,
  ROUTE,
  STATIC_BOXES,
  WORLD,
  createCamera,
  dynamicVehicleBoxes,
  localToWorld,
  nearestHangar,
  pickBoxes,
  routeStartDistance,
  worldTileOrigin,
} from "./scene.js";
import { SceneRenderer } from "./renderer.js";

const $ = (selector) => document.querySelector(selector);
const canvas = $("#gl-canvas");
const stage = $("#stage");
const renderer = new SceneRenderer(canvas);

const ui = {
  clock: $("#clock"),
  playButton: $("#play-button"),
  speedRange: $("#speed-range"),
  speedLabel: $(".speed-control span"),
  restart: $("#restart-button"),
  routeState: $("#route-state"),
  lapCount: $("#lap-count"),
  progress: $("#route-progress"),
  cameraCoord: $("#camera-coord"),
  originCoord: $("#origin-coord"),
  altitude: $("#altitude-value"),
  fps: $("#fps-value"),
  rawJitterCaption: $("#raw-jitter-caption"),
  relativeJitterCaption: $("#relative-jitter-caption"),
  relativeJitterValue: $("#relative-jitter-value"),
  rawJitterValue: $("#raw-jitter-value"),
  jitterFill: $("#jitter-fill"),
  jitterStatus: $("#jitter-status"),
  relativePickValue: $("#relative-pick-value"),
  rawPickValue: $("#raw-pick-value"),
  rawPickBar: $("#raw-pick-bar"),
  relativePickBar: $("#relative-pick-bar"),
  relativePickInline: $("#relative-pick-value-inline"),
  pickStatus: $("#pick-status"),
  relativeJumpValue: $("#relative-jump-value"),
  rawJumpValue: $("#raw-jump-value"),
  jumpStatus: $("#jump-status"),
  sparkline: $("#sparkline"),
  probeId: $("#probe-id"),
  pickX: $("#pick-x"),
  pickZ: $("#pick-z"),
  pickTarget: $("#pick-target"),
  pickDistance: $("#pick-distance"),
  pickDrift: $("#pick-drift"),
  probeButton: $("#probe-button"),
  crossingTrack: $("#crossing-track"),
  flash: $("#relocation-flash"),
  flashDetail: $("#flash-detail"),
  crosshair: $("#crosshair"),
  pipelineOrigin: $("#pipeline-origin"),
  cameraRelativeDistance: $("#camera-relative-distance"),
  uploadRate: $("#upload-rate"),
  frameTime: $("#frame-time"),
  helpButton: $("#help-button"),
  helpDialog: $("#help-dialog"),
  fullscreenButton: $("#fullscreen-button"),
  dragHint: $("#drag-hint"),
};

const state = {
  playing: true,
  speed: 120,
  traveled: 0,
  distance: routeStartDistance(),
  simTime: 0,
  lap: 1,
  origin: null,
  camera: null,
  yawOffset: -0.11,
  pitchOffset: 0,
  pickWorld: null,
  pickTarget: null,
  pickProbeId: 0,
  pickNdc: [0, -0.48],
  rawPickError: 0,
  relativePickError: 0,
  maxPickDrift: 0,
  metrics: {
    rawJitter: 0,
    relativeJitter: 0,
    rawJump: 0,
    relativeJump: 0,
  },
  crossings: [],
  stageWidth: 1,
  stageHeight: 1,
  paneWidth: 1,
  lastMetricUpdate: 0,
  fps: 60,
};

const pointer = {
  down: false,
  moved: false,
  x: 0,
  y: 0,
  startX: 0,
  startY: 0,
};

function formatWorld(value, decimals = 1) {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatCoordinate(value, decimals = 3) {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatError(value) {
  if (!Number.isFinite(value)) return "∞";
  if (value === 0) return "0.0000";
  if (value < 0.0001) return value.toExponential(2);
  if (value < 1) return value.toFixed(4);
  return value.toFixed(3);
}

function setStatus(element, text, level) {
  element.textContent = text;
  element.classList.remove("good", "warn", "bad");
  if (level) element.classList.add(level);
}

function resize() {
  const rect = stage.getBoundingClientRect();
  state.stageWidth = Math.max(1, rect.width);
  state.stageHeight = Math.max(1, rect.height);
  state.paneWidth = state.stageWidth / 3;
  renderer.resize(state.stageWidth, state.stageHeight, Math.min(window.devicePixelRatio || 1, 2));
}

function currentAspect() {
  return state.paneWidth / state.stageHeight;
}

function updateCamera() {
  state.camera = createCamera(state.distance, state.yawOffset, state.pitchOffset);
  return state.camera;
}

function selectDefaultPick() {
  const sampled = samplePick(
    state.camera,
    state.origin,
    currentAspect(),
    state.pickNdc[0],
    state.pickNdc[1],
  );
  if (sampled) {
    state.pickWorld = sampled.reference;
    state.rawPickError = sampled.rawError;
    state.relativePickError = sampled.relativeError;
    const nearest = nearestHangar(state.pickWorld[0], state.pickWorld[2]);
    state.pickTarget = nearest.hangar;
    state.pickProbeId += 1;
  }
}

function relativeProbeDrift() {
  if (!state.pickWorld || !state.pickTarget || !state.origin) return 0;
  const target = localToWorld(state.pickTarget.x, state.pickTarget.z);
  const pickRelX = Math.fround(state.pickWorld[0] - state.origin[0]);
  const pickRelZ = Math.fround(state.pickWorld[2] - state.origin[1]);
  const targetRelX = Math.fround(target[0] - state.origin[0]);
  const targetRelZ = Math.fround(target[2] - state.origin[1]);
  const quantizedDistance = Math.hypot(targetRelX - pickRelX, targetRelZ - pickRelZ);
  const exactDistance = Math.hypot(target[0] - state.pickWorld[0], target[2] - state.pickWorld[2]);
  return Math.abs(quantizedDistance - exactDistance);
}

function updateProbePanel() {
  if (!state.pickWorld) return;
  const nearest = nearestHangar(state.pickWorld[0], state.pickWorld[2]);
  state.pickTarget = nearest.hangar;
  const target = localToWorld(nearest.hangar.x, nearest.hangar.z);
  const distance = Math.hypot(
    target[0] - state.pickWorld[0],
    target[2] - state.pickWorld[2],
  );
  const drift = relativeProbeDrift();
  state.maxPickDrift = Math.max(state.maxPickDrift, drift);
  ui.probeId.textContent = `#${String(state.pickProbeId).padStart(4, "0")}`;
  ui.pickX.textContent = formatCoordinate(state.pickWorld[0]);
  ui.pickZ.textContent = formatCoordinate(state.pickWorld[2]);
  ui.pickTarget.textContent = nearest.hangar.name;
  ui.pickDistance.textContent = `${distance.toFixed(3)} m`;
  ui.pickDrift.textContent = `${(state.maxPickDrift * 1000).toFixed(3)} mm`;
}

function updateMetrics(force = false) {
  if (!state.camera || !state.origin) return;
  const now = performance.now();
  if (!force && now - state.lastMetricUpdate < 90) return;
  state.lastMetricUpdate = now;

  const aspect = currentAspect();
  const jitter = measureThinLineJitter(
    state.camera,
    state.distance,
    state.origin,
    aspect,
    state.paneWidth,
    state.stageHeight,
  );
  const pick = samplePick(
    state.camera,
    state.origin,
    aspect,
    state.pickNdc[0],
    state.pickNdc[1],
  );

  state.metrics.rawJitter = jitter.raw;
  state.metrics.relativeJitter = jitter.relative;
  if (pick) {
    state.rawPickError = pick.rawError;
    state.relativePickError = pick.relativeError;
  }

  const rawJitterText = `${jitter.raw.toFixed(3)} px`;
  const relativeJitterText = `${jitter.relative.toFixed(3)} px`;
  ui.rawJitterCaption.textContent = rawJitterText;
  ui.relativeJitterCaption.textContent = relativeJitterText;
  ui.relativeJitterValue.textContent = jitter.relative.toFixed(3);
  ui.rawJitterValue.textContent = rawJitterText;
  ui.jitterFill.style.width = `${Math.min(100, (jitter.relative / 1.5) * 100)}%`;
  setStatus(
    ui.jitterStatus,
    jitter.relative < 0.05 ? "稳定" : jitter.relative < 0.25 ? "轻微" : "可见",
    jitter.relative < 0.05 ? "good" : jitter.relative < 0.25 ? "warn" : "bad",
  );

  ui.relativePickValue.textContent = formatError(state.relativePickError);
  ui.rawPickValue.textContent = `${formatError(state.rawPickError)} m`;
  ui.relativePickInline.textContent = `${formatError(state.relativePickError)} m`;
  ui.rawPickBar.style.width = `${Math.min(100, 14 + Math.log10(Math.max(state.rawPickError, 1e-6) * 1e5 + 1) * 30)}%`;
  ui.relativePickBar.style.width = `${Math.min(30, Math.max(1, state.relativePickError * 1000))}%`;
  setStatus(
    ui.pickStatus,
    state.relativePickError < 0.001 ? "亚毫米" : state.relativePickError < 0.05 ? "毫米级" : "明显",
    state.relativePickError < 0.001 ? "good" : state.relativePickError < 0.05 ? "warn" : "bad",
  );

  ui.relativeJumpValue.textContent = state.metrics.relativeJump.toFixed(3);
  ui.rawJumpValue.textContent = `${state.metrics.rawJump.toFixed(3)} px`;
  setStatus(
    ui.jumpStatus,
    state.metrics.relativeJump < 0.05 ? "连续" : state.metrics.relativeJump < 0.2 ? "微跳" : "跳变",
    state.metrics.relativeJump < 0.05 ? "good" : state.metrics.relativeJump < 0.2 ? "warn" : "bad",
  );

  updateProbePanel();
  drawSparkline();
}

function drawSparkline() {
  const canvas2d = ui.sparkline;
  const context = canvas2d.getContext("2d");
  const width = canvas2d.width;
  const height = canvas2d.height;
  context.clearRect(0, 0, width, height);
  const records = state.crossings.slice(-16);
  if (records.length === 0) {
    context.strokeStyle = "rgba(108, 234, 224, 0.24)";
    context.setLineDash([4, 6]);
    context.beginPath();
    context.moveTo(2, height - 9);
    context.lineTo(width - 2, height - 9);
    context.stroke();
    context.setLineDash([]);
    return;
  }

  const maxValue = Math.max(0.25, ...records.map((record) => record.rawJump));
  const xAt = (index) => (
    records.length === 1 ? width - 4 : 3 + (index / (records.length - 1)) * (width - 7)
  );
  const yAt = (value) => height - 6 - Math.min(1, value / maxValue) * (height - 13);

  context.strokeStyle = "rgba(255, 124, 114, 0.85)";
  context.lineWidth = 2;
  context.beginPath();
  records.forEach((record, index) => {
    const x = xAt(index);
    const y = yAt(record.rawJump);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.stroke();

  context.strokeStyle = "#6ceae0";
  context.lineWidth = 2.5;
  context.beginPath();
  records.forEach((record, index) => {
    const x = xAt(index);
    const y = yAt(record.relativeJump);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.stroke();

  context.fillStyle = "#ffbd6b";
  context.beginPath();
  context.arc(xAt(records.length - 1), yAt(records[records.length - 1].relativeJump), 2.8, 0, Math.PI * 2);
  context.fill();
}

function updateCrossingStrip() {
  const records = state.crossings.slice(-9);
  if (records.length === 0) {
    ui.crossingTrack.innerHTML = '<div class="crossing-empty">等待首次分区过界…</div>';
    return;
  }
  ui.crossingTrack.innerHTML = records.map((record) => {
    const axis = record.dx !== 0 ? "X" : "Z";
    const delta = record.dx !== 0 ? record.dx : record.dz;
    const clean = record.relativeJump < 0.05;
    return `
      <div class="crossing-tick${clean ? " clean" : ""}" title="RAW JITTER ${record.rawJitter.toFixed(3)} px | REL JITTER ${record.relativeJitter.toFixed(3)} px | RAW JUMP ${record.rawJump.toFixed(3)} px | REL JUMP ${record.relativeJump.toFixed(3)} px | PICK ${record.relativePickError.toExponential(2)} m">
        <span>#${String(record.index).padStart(2, "0")} · Δ${axis} ${delta > 0 ? "+" : ""}${delta}</span>
        <b>JMP ${record.relativeJump.toFixed(3)} px</b>
        <em>JIT ${record.relativeJitter.toFixed(3)} · P ${(record.relativePickError * 1000).toFixed(2)} mm</em>
      </div>
    `;
  }).join("");
}

function showRelocationFlash(dx, dz) {
  ui.flashDetail.textContent = `ΔX ${dx >= 0 ? "+" : ""}${dx} m / ΔZ ${dz >= 0 ? "+" : ""}${dz} m`;
  ui.flash.classList.remove("show");
  void ui.flash.offsetWidth;
  ui.flash.classList.add("show");
}

function onOriginChange(oldOrigin, newOrigin, cameraBefore) {
  const aspect = currentAspect();
  const anchors = [];
  for (const hangar of HANGARS) {
    const top = localToWorld(hangar.x, hangar.z, hangar.height * 0.7);
    anchors.push(top);
  }
  if (state.pickWorld) anchors.push(state.pickWorld);

  const jump = measureRelocationJump(
    cameraBefore,
    state.camera,
    oldOrigin,
    newOrigin,
    anchors,
    aspect,
    state.paneWidth,
    state.stageHeight,
  );
  const jitter = measureThinLineJitter(
    state.camera,
    state.distance,
    newOrigin,
    aspect,
    state.paneWidth,
    state.stageHeight,
  );
  const pick = samplePick(state.camera, newOrigin, aspect, state.pickNdc[0], state.pickNdc[1]);
  const dx = newOrigin[0] - oldOrigin[0];
  const dz = newOrigin[1] - oldOrigin[1];
  state.metrics.relativeJump = jump.relative;
  state.metrics.rawJump = jump.raw;
  state.crossings.push({
    index: state.crossings.length + 1,
    originX: newOrigin[0],
    originZ: newOrigin[1],
    dx,
    dz,
    rawJump: jump.raw,
    relativeJump: jump.relative,
    rawJitter: jitter.raw,
    relativeJitter: jitter.relative,
    rawPickError: pick?.rawError ?? Infinity,
    relativePickError: pick?.relativeError ?? Infinity,
  });
  if (state.crossings.length > 24) state.crossings.shift();
  updateCrossingStrip();
  drawSparkline();
  showRelocationFlash(dx, dz);
}

function updateRouteHud() {
  const maxTravel = ROUTE.length * WORLD.routeLaps;
  const progress = Math.min(1, state.traveled / maxTravel);
  ui.progress.style.width = `${progress * 100}%`;
  ui.lapCount.textContent = `${String(Math.min(state.lap, WORLD.routeLaps)).padStart(2, "0")} / ${String(WORLD.routeLaps).padStart(2, "0")}`;
  if (state.traveled >= maxTravel) {
    ui.routeState.textContent = "REPLAY COMPLETE / 03 LAPS";
    ui.playButton.classList.add("paused");
  } else if (!state.playing) {
    ui.routeState.textContent = "PAUSED / 03 LAPS";
    ui.playButton.classList.add("paused");
  } else {
    ui.routeState.textContent = "AUTO REPLAY / 03 LAPS";
    ui.playButton.classList.remove("paused");
  }
}

function updateHud() {
  const camera = state.camera;
  if (!camera || !state.origin) return;
  const cameraX = camera.eye[0];
  const cameraZ = camera.eye[2];
  ui.cameraCoord.textContent = `X ${formatWorld(cameraX, 1)} / Z ${formatWorld(cameraZ, 1)}`;
  ui.originCoord.textContent = `X ${formatWorld(state.origin[0], 0)} / Z ${formatWorld(state.origin[1], 0)}`;
  ui.altitude.textContent = `${camera.eye[1].toFixed(1)} m`;
  ui.pipelineOrigin.textContent = `${Math.floor(state.origin[0] / WORLD.tileSize)} / ${Math.floor(state.origin[1] / WORLD.tileSize)}`;
  const relativeDistance = Math.hypot(camera.eye[0] - state.origin[0], camera.eye[2] - state.origin[1]);
  ui.cameraRelativeDistance.textContent = `${relativeDistance.toFixed(1)} m`;
  const now = new Date();
  ui.clock.textContent = `${now.toLocaleTimeString("en-GB", { hour12: false })}.${String(now.getMilliseconds()).padStart(3, "0")}`;
  updateRouteHud();

  const projected = projectPickToScreen(
    camera,
    state.origin,
    state.pickWorld,
    currentAspect(),
    state.paneWidth,
    state.stageHeight,
  );
  if (projected) {
    ui.crosshair.style.left = `${state.paneWidth + projected.x}px`;
    ui.crosshair.style.top = `${projected.y}px`;
    ui.crosshair.classList.add("visible");
  } else {
    ui.crosshair.classList.remove("visible");
  }
}

function advance(dt) {
  const maxTravel = ROUTE.length * WORLD.routeLaps;
  const previousCamera = state.camera;
  state.simTime += dt;

  if (state.playing && state.traveled < maxTravel) {
    state.traveled = Math.min(maxTravel, state.traveled + state.speed * dt);
  }
  if (state.traveled >= maxTravel && state.playing) {
    state.playing = false;
  }
  state.lap = Math.min(WORLD.routeLaps, Math.floor(state.traveled / ROUTE.length) + 1);
  state.distance = routeStartDistance() + state.traveled;
  updateCamera();

  const newOrigin = worldTileOrigin(state.camera.eye[0], state.camera.eye[2]);
  if (!state.origin) {
    state.origin = newOrigin;
  } else if (newOrigin[0] !== state.origin[0] || newOrigin[1] !== state.origin[1]) {
    const oldOrigin = state.origin;
    state.origin = newOrigin;
    onOriginChange(oldOrigin, newOrigin, previousCamera || state.camera);
  }
}

function buildInstances() {
  return [
    ...STATIC_BOXES,
    ...dynamicVehicleBoxes(state.simTime),
    ...pickBoxes(state.pickWorld, state.pickTarget),
  ];
}

function renderFrame() {
  updateHud();
  renderer.render({
    camera: state.camera,
    origin: state.origin,
    instances: buildInstances(),
  });
}

let frameCounter = 0;
let fpsTimer = 0;
let lastFrameTime = performance.now();

function animationLoop(now) {
  const dt = Math.min(0.05, Math.max(0.001, (now - lastFrameTime) / 1000));
  lastFrameTime = now;
  const start = performance.now();

  advance(dt);
  updateMetrics();
  renderFrame();

  frameCounter += 1;
  fpsTimer += dt;
  if (fpsTimer >= 0.5) {
    state.fps = Math.round(frameCounter / fpsTimer);
    ui.fps.textContent = state.fps;
    frameCounter = 0;
    fpsTimer = 0;
  }
  ui.frameTime.textContent = `${(performance.now() - start).toFixed(2)} ms`;
  requestAnimationFrame(animationLoop);
}

function sampleAtPointer(event) {
  const rect = stage.getBoundingClientRect();
  const localX = event.clientX - rect.left;
  const localY = event.clientY - rect.top;
  const pane = Math.max(0, Math.min(2, Math.floor(localX / state.paneWidth)));
  const paneX = localX - pane * state.paneWidth;
  const ndcX = (paneX / state.paneWidth) * 2 - 1;
  const ndcY = 1 - (localY / state.stageHeight) * 2;
  const result = samplePick(state.camera, state.origin, currentAspect(), ndcX, ndcY);
  if (!result) return;
  state.pickWorld = result.reference;
  state.pickNdc = [ndcX, ndcY];
  state.rawPickError = result.rawError;
  state.relativePickError = result.relativeError;
  state.pickProbeId += 1;
  state.maxPickDrift = 0;
  const nearest = nearestHangar(state.pickWorld[0], state.pickWorld[2]);
  state.pickTarget = nearest.hangar;
  updateMetrics(true);
}

function restartRoute() {
  state.traveled = 0;
  state.lap = 1;
  state.playing = true;
  state.simTime = 0;
  state.crossings = [];
  state.maxPickDrift = 0;
  state.metrics.rawJump = 0;
  state.metrics.relativeJump = 0;
  state.distance = routeStartDistance();
  updateCamera();
  state.origin = worldTileOrigin(state.camera.eye[0], state.camera.eye[2]);
  updateCrossingStrip();
  drawSparkline();
  updateMetrics(true);
}

function togglePlayback() {
  const maxTravel = ROUTE.length * WORLD.routeLaps;
  if (state.traveled >= maxTravel) {
    restartRoute();
    return;
  }
  state.playing = !state.playing;
  updateRouteHud();
}

function installInteractions() {
  ui.playButton.addEventListener("click", togglePlayback);
  ui.restart.addEventListener("click", restartRoute);
  ui.probeButton.addEventListener("click", () => {
    state.pickNdc = [0, -0.48];
    selectDefaultPick();
    state.maxPickDrift = 0;
    updateMetrics(true);
  });
  ui.speedRange.addEventListener("input", () => {
    state.speed = Number(ui.speedRange.value);
    ui.speedLabel.textContent = `${state.speed} m/s`;
  });

  stage.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    pointer.down = true;
    pointer.moved = false;
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    pointer.startX = event.clientX;
    pointer.startY = event.clientY;
    stage.setPointerCapture(event.pointerId);
    ui.dragHint.classList.remove("visible");
  });

  stage.addEventListener("pointermove", (event) => {
    if (!pointer.down) return;
    const dx = event.clientX - pointer.x;
    const dy = event.clientY - pointer.y;
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    if (Math.hypot(event.clientX - pointer.startX, event.clientY - pointer.startY) > 4) {
      pointer.moved = true;
    }
    state.yawOffset -= dx * 0.0034;
    state.pitchOffset = Math.max(-0.28, Math.min(0.28, state.pitchOffset - dy * 0.0026));
  });

  stage.addEventListener("pointerup", (event) => {
    if (!pointer.down) return;
    pointer.down = false;
    if (!pointer.moved) sampleAtPointer(event);
    stage.releasePointerCapture(event.pointerId);
  });

  stage.addEventListener("pointercancel", () => {
    pointer.down = false;
  });

  stage.addEventListener("wheel", (event) => {
    event.preventDefault();
    state.pitchOffset = Math.max(-0.28, Math.min(0.28, state.pitchOffset + event.deltaY * 0.00016));
  }, { passive: false });

  ui.helpButton.addEventListener("click", () => ui.helpDialog.showModal());
  ui.fullscreenButton.addEventListener("click", async () => {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  });

  window.addEventListener("keydown", (event) => {
    if (event.target instanceof HTMLInputElement) return;
    if (event.code === "Space") {
      event.preventDefault();
      togglePlayback();
    } else if (event.key.toLowerCase() === "r") {
      restartRoute();
    }
  });

  const observer = new ResizeObserver(() => {
    resize();
    updateMetrics(true);
  });
  observer.observe(stage);
}

function initialize() {
  resize();
  updateCamera();
  state.origin = worldTileOrigin(state.camera.eye[0], state.camera.eye[2]);
  selectDefaultPick();
  updateMetrics(true);
  updateRouteHud();
  updateHud();
  installInteractions();
  drawSparkline();
  renderFrame();
  window.setTimeout(() => ui.dragHint.classList.add("visible"), 1600);
  window.setTimeout(() => ui.dragHint.classList.remove("visible"), 8500);
  requestAnimationFrame(animationLoop);
}

initialize();

window.__ORIGIN_SHIFT__ = {
  state,
  restart: restartRoute,
  pause() {
    state.playing = false;
    updateRouteHud();
  },
  resume() {
    state.playing = true;
    updateRouteHud();
  },
  jumpTo(routeDistance) {
    const wrapped = Math.max(0, routeDistance);
    state.traveled = wrapped;
    state.distance = routeStartDistance() + wrapped;
    updateCamera();
    state.origin = worldTileOrigin(state.camera.eye[0], state.camera.eye[2]);
    updateMetrics(true);
    updateHud();
  },
};
