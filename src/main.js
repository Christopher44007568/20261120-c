import {
  SoftBody,
  validateSoftBody,
} from "./sim.js";
import {
  paintSpectrum,
  colorResponse,
  energyAudit,
  PAINT_PRESETS,
} from "./paint.js";
import {
  drawVolumeChart,
  drawErrorChart,
  drawSpectrumChart,
  drawColorChart,
  drawPaintCrossSection,
} from "./charts.js";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const state = {
  mode: "compress",
  strain: 0.18,
  iterations: 24,
  stiffness: 0.82,
  collision: true,
  paused: false,
  paintPreset: "cobalt",
  angle: 35,
  validation: null,
  softBody: null,
};

const softCanvas = $("#softCanvas");
const paintCanvas = $("#paintCanvas");
const volumeChart = $("#volumeChart");
const errorChart = $("#errorChart");
const spectrumChart = $("#spectrumChart");
const colorChart = $("#colorChart");

function currentSpectrum() {
  return paintSpectrum(state.paintPreset, state.angle);
}

function formatPercent(value, digits = 2) {
  return `${value.toFixed(digits)}%`;
}

function formatSignedPercent(value, digits = 2) {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(digits)}%`;
}

function formatScientific(value) {
  if (value === 0) return "0";
  const exponent = Math.floor(Math.log10(Math.abs(value)));
  const mantissa = value / 10 ** exponent;
  return `${mantissa.toFixed(1)}e−${Math.abs(exponent)}`;
}

function createSoftBody(reset = true) {
  state.softBody = new SoftBody({
    mode: state.mode,
    strain: state.strain,
    iterations: state.iterations,
    stiffness: state.stiffness,
    collision: state.collision,
    instant: false,
    seed: reset ? 1 : 0,
    grid: 5,
    volumeStiffness: 0.75,
  });
}

function project(point, width, height) {
  const yaw = -0.58;
  const scale = Math.min(width / 3.65, height / 3.18);
  const cos = Math.cos(yaw);
  const sin = Math.sin(yaw);
  const x = point.x * cos - point.y * sin;
  const depth = point.x * sin + point.y * cos;
  return {
    x: width * 0.49 + x * scale,
    y: height * 0.51 - point.z * scale + depth * 0.215 * scale,
    depth,
    scale,
  };
}

function polygon(ctx, points, fill, stroke, lineWidth = 1) {
  if (!points.length) return;
  ctx.beginPath();
  points.forEach((point, index) => {
    if (index === 0) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
  });
  ctx.closePath();
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }
}

function drawPlate(ctx, body, width, height, top) {
  const z = top ? body.topPlate + 0.085 : body.bottomPlate - 0.085;
  const x0 = -1.52;
  const x1 = 1.52;
  const y0 = -1.35;
  const y1 = 1.35;
  const corners = [
    { x: x0, y: y0, z },
    { x: x1, y: y0, z },
    { x: x1, y: y1, z },
    { x: x0, y: y1, z },
  ].map((point) => project(point, width, height));
  const depth = 0.08;
  const lower = corners.map((point) => ({
    x: point.x,
    y: point.y + (top ? -7 : 7),
  }));
  ctx.save();
  ctx.shadowColor = "rgba(102, 221, 255, 0.18)";
  ctx.shadowBlur = 18;
  const gradient = ctx.createLinearGradient(corners[0].x, corners[0].y, corners[2].x, corners[2].y);
  gradient.addColorStop(0, "rgba(100, 149, 172, 0.16)");
  gradient.addColorStop(0.5, "rgba(178, 218, 230, 0.08)");
  gradient.addColorStop(1, "rgba(57, 91, 108, 0.18)");
  polygon(ctx, corners, gradient, "rgba(143, 211, 230, 0.55)", 1);
  ctx.shadowBlur = 0;
  ctx.strokeStyle = "rgba(118, 185, 205, 0.22)";
  for (let i = 0; i < 7; i += 1) {
    const t = i / 6;
    const x = corners[0].x + (corners[1].x - corners[0].x) * t;
    const y = corners[0].y + (corners[1].y - corners[0].y) * t;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x, y + (top ? -7 : 7));
    ctx.stroke();
  }
  polygon(
    ctx,
    [corners[0], corners[1], lower[1], lower[0]],
    "rgba(22, 39, 49, 0.42)",
    "rgba(143, 211, 230, 0.28)",
    0.8,
  );
  ctx.restore();
  return { z, depth };
}

function drawAxisArrows(ctx, body, width, height) {
  const direction = state.mode === "compress" ? 1 : -1;
  const center = project({ x: 0, y: 0, z: body.topPlate }, width, height);
  const topArrowY = center.y - 29;
  const bottom = project({ x: 0, y: 0, z: body.bottomPlate }, width, height);
  ctx.save();
  ctx.fillStyle = "rgba(200, 245, 106, 0.72)";
  ctx.beginPath();
  if (state.mode === "compress") {
    ctx.moveTo(center.x, topArrowY + 10);
    ctx.lineTo(center.x - 4, topArrowY);
    ctx.lineTo(center.x + 4, topArrowY);
    ctx.closePath();
  } else {
    ctx.moveTo(center.x, topArrowY);
    ctx.lineTo(center.x - 4, topArrowY + 10);
    ctx.lineTo(center.x + 4, topArrowY + 10);
    ctx.closePath();
  }
  ctx.fill();
  ctx.fillStyle = "rgba(200, 245, 106, 0.72)";
  ctx.beginPath();
  if (state.mode === "compress") {
    ctx.moveTo(bottom.x, bottom.y + 29 - 10);
    ctx.lineTo(bottom.x - 4, bottom.y + 29);
    ctx.lineTo(bottom.x + 4, bottom.y + 29);
  } else {
    ctx.moveTo(bottom.x, bottom.y + 29);
    ctx.lineTo(bottom.x - 4, bottom.y + 29 - 10);
    ctx.lineTo(bottom.x + 4, bottom.y + 29 - 10);
  }
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = "rgba(200, 245, 106, 0.22)";
  ctx.setLineDash([3, 4]);
  ctx.beginPath();
  ctx.moveTo(bottom.x, bottom.y + 20);
  ctx.lineTo(center.x, center.y - 20);
  ctx.stroke();
  ctx.restore();
}

function drawCollider(ctx, body, width, height) {
  if (!state.collision) return;
  const center = project(body.sphereCenter, width, height);
  const radius = body.sphereRadius * center.scale;
  if (radius < 2) return;
  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  const gradient = ctx.createRadialGradient(
    center.x - radius * 0.34,
    center.y - radius * 0.38,
    radius * 0.05,
    center.x,
    center.y,
    radius,
  );
  gradient.addColorStop(0, "rgba(255, 235, 220, 0.32)");
  gradient.addColorStop(0.35, "rgba(255, 145, 105, 0.11)");
  gradient.addColorStop(0.8, "rgba(255, 100, 74, 0.035)");
  gradient.addColorStop(1, "rgba(255, 100, 74, 0)");
  ctx.fillStyle = gradient;
  ctx.beginPath();
  ctx.arc(center.x, center.y, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(255, 150, 120, 0.52)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(center.x, center.y, radius, -1.4, 1.6);
  ctx.stroke();
  ctx.strokeStyle = "rgba(255, 190, 165, 0.16)";
  ctx.beginPath();
  ctx.ellipse(center.x, center.y, radius * 0.86, radius * 0.25, -0.3, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

function drawMeasure(ctx, body, width, height) {
  const x = width * 0.86;
  const top = project({ x: 0, y: 0, z: body.topPlate }, width, height).y;
  const bottom = project({ x: 0, y: 0, z: body.bottomPlate }, width, height).y;
  const y0 = top - 8;
  const y1 = bottom + 8;
  ctx.save();
  ctx.strokeStyle = "rgba(102, 221, 255, 0.35)";
  ctx.fillStyle = "rgba(102, 221, 255, 0.55)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x, y0);
  ctx.lineTo(x, y1);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x - 4, y0);
  ctx.lineTo(x + 4, y0);
  ctx.moveTo(x - 4, y1);
  ctx.lineTo(x + 4, y1);
  ctx.stroke();
  ctx.save();
  ctx.translate(x + 11, (y0 + y1) / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.font = '7px "Forma Mono", monospace';
  ctx.textAlign = "center";
  ctx.fillStyle = "rgba(143, 196, 211, 0.75)";
  ctx.fillText(`ΔZ ${body.gap.toFixed(3)}`, 0, 0);
  ctx.restore();
  ctx.font = '7px "Forma Mono", monospace';
  ctx.textAlign = "left";
  ctx.fillStyle = "rgba(102, 221, 255, 0.72)";
  const strainText = body.mode === "compress"
    ? `−${(body.strainActual * 100).toFixed(1)}%`
    : `+${(body.strainActual * 100).toFixed(1)}%`;
  ctx.fillText(strainText, x + 6, y0 + 18);
  ctx.restore();
}

function drawSoftSimulation(time) {
  const rect = softCanvas.getBoundingClientRect();
  const width = Math.max(1, rect.width);
  const height = Math.max(1, rect.height);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (softCanvas.width !== Math.round(width * dpr) || softCanvas.height !== Math.round(height * dpr)) {
    softCanvas.width = Math.round(width * dpr);
    softCanvas.height = Math.round(height * dpr);
  }
  const ctx = softCanvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const body = state.softBody;
  if (!body) return;
  const projected = body.points.map((point) => project(point, width, height));

  drawPlate(ctx, body, width, height, false);
  drawPlate(ctx, body, width, height, true);

  ctx.save();
  for (const constraint of body.constraints) {
    const a = projected[constraint.a];
    const b = projected[constraint.b];
    const depth = (a.depth + b.depth) * 0.5;
    const alpha = constraint.axis
      ? 0.08 + clamp((depth + 1.5) / 3, 0, 1) * 0.11
      : 0.018 + clamp((depth + 1.5) / 3, 0, 1) * 0.035;
    ctx.strokeStyle = `rgba(133, 206, 217, ${alpha})`;
    ctx.lineWidth = constraint.axis ? 0.7 : 0.45;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }
  ctx.restore();

  const faceData = body.faces.map(([aIndex, bIndex, cIndex]) => {
    const a = body.points[aIndex];
    const b = body.points[bIndex];
    const c = body.points[cIndex];
    const ux = b.x - a.x;
    const uy = b.y - a.y;
    const uz = b.z - a.z;
    const vx = c.x - a.x;
    const vy = c.y - a.y;
    const vz = c.z - a.z;
    const nx = uy * vz - uz * vy;
    const ny = uz * vx - ux * vz;
    const nz = ux * vy - uy * vx;
    const length = Math.hypot(nx, ny, nz) || 1;
    const light = Math.max(0.12, Math.abs(
      (nx / length) * -0.38 + (ny / length) * -0.55 + (nz / length) * 0.74,
    ));
    const pa = projected[aIndex];
    const pb = projected[bIndex];
    const pc = projected[cIndex];
    return {
      points: [pa, pb, pc],
      depth: (pa.depth + pb.depth + pc.depth) / 3,
      light,
      centerZ: (a.z + b.z + c.z) / 3,
    };
  }).sort((a, b) => a.depth - b.depth);

  for (const face of faceData) {
    const light = face.light;
    const red = Math.round(56 + light * 87);
    const green = Math.round(139 + light * 92);
    const blue = Math.round(145 + light * 77);
    polygon(
      ctx,
      face.points,
      `rgba(${red}, ${green}, ${blue}, ${0.035 + light * 0.055})`,
      `rgba(151, 224, 220, ${0.035 + light * 0.08})`,
      0.55,
    );
  }

  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  for (const point of projected) {
    const size = 1 + clamp((point.depth + 1.5) / 3, 0, 1) * 1.8;
    const alpha = 0.3 + clamp((point.depth + 1.5) / 3, 0, 1) * 0.58;
    ctx.fillStyle = `rgba(160, 238, 227, ${alpha})`;
    ctx.beginPath();
    ctx.arc(point.x, point.y, size, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();

  drawCollider(ctx, body, width, height);
  drawAxisArrows(ctx, body, width, height);
  drawMeasure(ctx, body, width, height);

  const glow = ctx.createRadialGradient(
    width * 0.49,
    height * 0.52,
    0,
    width * 0.49,
    height * 0.52,
    width * 0.27,
  );
  glow.addColorStop(0, "rgba(92, 214, 191, 0.04)");
  glow.addColorStop(1, "rgba(92, 214, 191, 0)");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, width, height);
  void time;
}

function interpolationRow(iterations) {
  const rows = state.validation?.byIteration;
  if (!rows?.length) return null;
  if (iterations <= rows[0].iterations) return rows[0];
  if (iterations >= rows.at(-1).iterations) return rows.at(-1);
  const upperIndex = rows.findIndex((row) => row.iterations >= iterations);
  const lower = rows[upperIndex - 1];
  const upper = rows[upperIndex];
  const t = Math.log(iterations / lower.iterations) / Math.log(upper.iterations / lower.iterations);
  const mix = (key) => lower[key] + (upper[key] - lower[key]) * t;
  return {
    iterations,
    compressVolume: mix("compressVolume"),
    stretchVolume: mix("stretchVolume"),
    vertexError: mix("vertexError"),
    shapeError: mix("shapeError"),
    jitter: mix("jitter"),
    residual: mix("residual"),
    volumeError: mix("volumeError"),
    stability: mix("stability"),
    stable: lower.stable && upper.stable,
  };
}

function renderValidation() {
  const validation = state.validation;
  if (!validation) return;
  const { byIteration, summary } = validation;
  const row = interpolationRow(state.iterations);
  const volume = state.mode === "compress" ? row.compressVolume : row.stretchVolume;
  const volumeDelta = volume - 100;
  $("#metricVolume").textContent = volume.toFixed(2);
  $("#metricVolumeDelta").textContent = `ΔV ${formatSignedPercent(volumeDelta)}`;
  $("#metricError").innerHTML = `${row.vertexError < 0.001 ? "<0.001" : row.vertexError.toFixed(3)} <i>mm</i>`;
  $("#metricIterations").innerHTML = `${state.iterations} <i>×</i>`;
  $("#metricJitter").textContent = row.jitter.toFixed(3);
  $("#metricConverged").textContent = row.stable ? "PASS" : "ITERATE";
  $("#metricConverged").classList.toggle("ok", row.stable);
  $("#metricConverged").style.color = row.stable ? "var(--lime)" : "var(--amber)";
  $("#hudIterations").textContent = state.iterations;

  $("#validationRows").innerHTML = byIteration.map((entry) => `
    <tr data-iterations="${entry.iterations}">
      <td>${entry.iterations}× <span style="color:var(--faint)">${entry.stable ? "" : "LOW"}</span></td>
      <td class="${Math.abs(entry.compressVolume - 100) < 1 ? "good" : "warn"}">${entry.compressVolume.toFixed(3)}%</td>
      <td class="${Math.abs(entry.stretchVolume - 100) < 1 ? "good" : "warn"}">${entry.stretchVolume.toFixed(3)}%</td>
      <td>${entry.vertexError < 0.001 ? "0.000" : entry.vertexError.toFixed(3)} mm</td>
      <td>${entry.jitter.toFixed(3)}</td>
      <td>${entry.stable
        ? '<span class="pass-pill">PASS</span>'
        : '<span style="color:var(--amber)">ITERATE</span>'}</td>
    </tr>
  `).join("");

  const score = Math.round(row.stability);
  $("#stabilityScore").textContent = score;
  $("#stabilityRing").style.background = `
    radial-gradient(circle, #0e141b 54%, transparent 55%),
    conic-gradient(var(--lime) 0 ${score}%, rgba(255, 255, 255, 0.07) ${score}% 100%)
  `;
  $("#stabilityVerdict").textContent = row.stable ? "高迭代区稳定" : "低迭代区振荡";
  $("#stabilityDescription").textContent = row.stable
    ? `当前 ${state.iterations}× 迭代已进入稳定包络。1 → 64× 的残余抖动下降 ${summary.jitterReduction.toFixed(1)}%，32× 后趋于平台。`
    : `当前 ${state.iterations}× 迭代仍有明显投影残差。建议至少使用 ${summary.stableAt}× 迭代，再进入体积与颜色测量。`;

  $("#stabilityBars").innerHTML = byIteration.map((entry) => {
    const height = clamp((entry.stability - 50) * 1.75, 8, 100);
    return `<i class="${entry.stable ? "" : "is-low"}" style="height:${height}%" title="${entry.iterations}× · ${entry.stability.toFixed(1)}"></i>`;
  }).join("");
  $("#volumeInsight").textContent = `最大体积偏差 挤压 ${summary.maxCompressVolumeError.toFixed(2)}% / 拉伸 ${summary.maxStretchVolumeError.toFixed(2)}%`;
  const firstError = byIteration[0].vertexError;
  const lastError = byIteration.at(-1).vertexError;
  $("#errorInsight").textContent = `1 → 64×：${firstError.toFixed(2)} → ${lastError < 0.001 ? "0.00" : lastError.toFixed(2)} mm`;
  $("#stabilityRing").setAttribute("aria-label", `稳定性指数 ${score}`);
}

function drawValidationCharts() {
  if (!state.validation) return;
  drawVolumeChart(volumeChart, state.validation.byIteration);
  drawErrorChart(errorChart, state.validation.byIteration);
}

function updateLiveReadouts() {
  const body = state.softBody;
  if (!body) return;
  const metrics = body.measure();
  $("#hudResidual").textContent = metrics.residual.toFixed(4);
  $("#hudState").textContent = state.paused
    ? "PAUSED"
    : body.progress < 0.99
      ? "LOADING"
      : metrics.velocityRms > 0.35
        ? "SETTLING"
        : "STABLE";
  $("#hudStrain").textContent = body.mode === "compress"
    ? `−${(body.strainActual * 100).toFixed(1)}%`
    : `+${(body.strainActual * 100).toFixed(1)}%`;
  $("#stepLabel").textContent = `STEP ${String(body.stepCount).padStart(4, "0")}`;
  $("#progressFill").style.width = `${clamp(body.progress * 100, 2, 100)}%`;
  if (!state.validation) {
    $("#metricVolume").textContent = metrics.volumeRetention.toFixed(2);
    $("#metricVolumeDelta").textContent = `ΔV ${formatSignedPercent(metrics.volumeRetention - 100)}`;
    $("#metricError").innerHTML = `${metrics.vertexError.toFixed(3)} <i>mm</i>`;
    $("#metricJitter").textContent = metrics.velocityRms.toFixed(3);
  }
}

function renderPaintData() {
  const spectrum = currentSpectrum();
  state.paintSpectrum = spectrum;
  const preset = PAINT_PRESETS[state.paintPreset];
  $("#angleReadout").textContent = `${state.angle}°`;
  $("#angleOutput").textContent = `${state.angle}°`;
  $("#paintName").textContent = preset.name;
  $("#paintSwatch").style.background = spectrum.hex;
  $("#paintSwatch").style.boxShadow = `0 0 22px ${spectrum.hex}88, inset -4px -5px 8px rgba(0,0,0,.35)`;
  $("#reflectEnergy").textContent = formatPercent(spectrum.totals.R * 100, 1);
  $("#transmitEnergy").textContent = formatPercent(spectrum.totals.T * 100, 1);
  $("#absorbEnergy").textContent = formatPercent(spectrum.totals.A * 100, 1);
  $("#totalEnergy").textContent = `${(spectrum.energyTotal * 100).toFixed(3)}%`;
  const audit = energyAudit(state.paintPreset);
  const errorText = formatScientific(audit.maxError);
  $("#energyResidual").textContent = `MAX ERROR ${errorText}`;
  $("#energyResidualInline").textContent = errorText;
  $("#energyAudit").textContent = audit.maxError < 1e-12 ? "PASS" : "CHECK";
  $("#energyAudit").style.color = audit.maxError < 1e-12 ? "var(--lime)" : "var(--amber)";
  drawSpectrumChart(spectrumChart, spectrum);
}

function renderColorData() {
  const response = colorResponse(state.paintPreset);
  drawColorChart(colorChart, response);
  const gradient = `linear-gradient(90deg, ${response.map((entry) => entry.hex).join(", ")})`;
  $("#colorStrip").style.background = gradient;
}

function updatePaintCharts() {
  renderPaintData();
  renderColorData();
}

function bindSoftControls() {
  $$(".seg-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.mode = button.dataset.mode;
      $$(".seg-btn").forEach((item) => item.classList.toggle("is-active", item === button));
      $("#viewportMode").textContent = state.mode === "compress"
        ? "UNIAXIAL / COMPRESS"
        : "UNIAXIAL / STRETCH";
      createSoftBody();
      renderValidation();
    });
  });

  const iterationRange = $("#iterationRange");
  iterationRange.addEventListener("input", () => {
    state.iterations = Number(iterationRange.value);
    $("#iterationOutput").textContent = state.iterations;
    state.softBody?.setIterations(state.iterations);
    renderValidation();
  });

  const strainRange = $("#strainRange");
  strainRange.addEventListener("input", () => {
    state.strain = Number(strainRange.value) / 100;
    $("#strainOutput").textContent = `${strainRange.value}%`;
    createSoftBody();
    renderValidation();
  });

  const stiffnessRange = $("#stiffnessRange");
  stiffnessRange.addEventListener("input", () => {
    state.stiffness = Number(stiffnessRange.value) / 100;
    $("#stiffnessOutput").textContent = state.stiffness.toFixed(2);
    state.softBody?.setStiffness(state.stiffness);
  });

  const collisionToggle = $("#collisionToggle");
  collisionToggle.addEventListener("change", () => {
    state.collision = collisionToggle.checked;
    if (state.softBody) state.softBody.collision = state.collision;
  });

  $("#playButton").addEventListener("click", () => {
    state.paused = !state.paused;
    $("#playButton").classList.toggle("is-paused", state.paused);
    $("#playButton").setAttribute("aria-label", state.paused ? "继续仿真" : "暂停仿真");
  });

  $("#resetButton").addEventListener("click", () => {
    createSoftBody();
  });

  $("#exportButton").addEventListener("click", exportValidation);
}

function bindPaintControls() {
  const angleRange = $("#angleRange");
  angleRange.addEventListener("input", () => {
    state.angle = Number(angleRange.value);
    renderPaintData();
  });
  $$(".preset").forEach((button) => {
    button.addEventListener("click", () => {
      state.paintPreset = button.dataset.preset;
      $$(".preset").forEach((item) => item.classList.toggle("is-active", item === button));
      updatePaintCharts();
    });
  });
}

function exportValidation() {
  const spectrum = currentSpectrum();
  const audit = energyAudit(state.paintPreset);
  const payload = {
    generatedAt: new Date().toISOString(),
    model: "Position-Based Dynamics / distance constraints",
    simulation: {
      mode: state.mode,
      strainPercent: state.strain * 100,
      iterations: state.iterations,
      stiffness: state.stiffness,
      collisionProbe: state.collision,
      particles: 125,
      substeps: 2,
    },
    validation: state.validation,
    paint: {
      preset: state.paintPreset,
      angleDeg: state.angle,
      energy: {
        reflection: spectrum.totals.R,
        transmission: spectrum.totals.T,
        absorption: spectrum.totals.A,
        total: spectrum.energyTotal,
        maxAuditError: audit.maxError,
      },
      spectrum: {
        wavelengths: spectrum.wavelengths,
        reflection: spectrum.reflectances,
        transmission: spectrum.transmissions,
        absorption: spectrum.absorptions,
      },
    },
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `forma-validation-${state.mode}-${state.iterations}x.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function observeSections() {
  const links = $$(".rail-link");
  const observer = new IntersectionObserver((entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    links.forEach((link) => {
      link.classList.toggle("is-active", link.getAttribute("href") === `#${visible.target.id}`);
    });
  }, { rootMargin: "-20% 0px -55% 0px", threshold: [0.05, 0.25, 0.5] });
  $$("main section[id]").forEach((section) => observer.observe(section));
}

function initializeValidation() {
  $("#validationRows").innerHTML = `
    <tr><td colspan="6" style="color:var(--faint)">正在执行 42 组挤压 / 拉伸重复验证…</td></tr>
  `;
  window.setTimeout(() => {
    state.validation = validateSoftBody();
    renderValidation();
    drawValidationCharts();
  }, 90);
}

let lastFrame = performance.now();
let accumulator = 0;
let lastReadout = 0;

function animationFrame(now) {
  const elapsed = Math.min(0.05, (now - lastFrame) / 1000);
  lastFrame = now;
  if (!state.paused && state.softBody) {
    accumulator = Math.min(accumulator + elapsed, 0.12);
    let steps = 0;
    while (accumulator >= 1 / 60 && steps < 3) {
      state.softBody.step(1 / 60, 2);
      accumulator -= 1 / 60;
      steps += 1;
    }
  }
  drawSoftSimulation(now);
  drawPaintCrossSection(
    paintCanvas,
    state.paintSpectrum ?? currentSpectrum(),
    state.paintPreset,
    now,
  );
  if (now - lastReadout > 110) {
    updateLiveReadouts();
    lastReadout = now;
  }
  requestAnimationFrame(animationFrame);
}

let resizeTimer = 0;
window.addEventListener("resize", () => {
  window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => {
    drawValidationCharts();
    updatePaintCharts();
  }, 120);
});

document.fonts?.ready.then(() => {
  drawValidationCharts();
  updatePaintCharts();
});

createSoftBody();
state.paintSpectrum = currentSpectrum();
bindSoftControls();
bindPaintControls();
renderPaintData();
renderColorData();
observeSections();
initializeValidation();
requestAnimationFrame(animationFrame);
