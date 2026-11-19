import {
  ATMOSPHERE,
  DEFAULT_PARAMS,
  cloudProfile,
  colorDistance,
  directIlluminance,
  luminance,
  rgbToHex,
  skyColor,
  sunColor,
  sunDirection,
  sunTransmittance
} from './atmosphere.js';
import { SkyRenderer } from './renderer.js';

const state = { ...DEFAULT_PARAMS };
const $ = (selector) => document.querySelector(selector);

const urlParams = new URLSearchParams(window.location.search);
for (const key of ['sunElevation', 'sunAzimuth', 'rayleighScale', 'mieScale',
  'cloudCoverage', 'cloudThickness']) {
  if (urlParams.has(key) && Number.isFinite(Number(urlParams.get(key)))) {
    state[key] = Number(urlParams.get(key));
  }
}
if (urlParams.has('cloudShadows')) {
  state.cloudShadows = urlParams.get('cloudShadows') !== '0';
}

const dom = {
  canvas: $('#sky-canvas'),
  error: $('#webgl-error'),
  panelElevation: $('#panel-elevation'),
  panelAzimuth: $('#panel-azimuth'),
  sunVector: $('#sun-vector'),
  sunSwatch: $('#sun-swatch'),
  sunHex: $('#sun-hex'),
  sunRgb: $('#sun-rgb'),
  zenithSwatch: $('#zenith-swatch'),
  zenithHex: $('#zenith-hex'),
  zenithRgb: $('#zenith-rgb'),
  horizonSwatch: $('#horizon-swatch'),
  horizonHex: $('#horizon-hex'),
  horizonRgb: $('#horizon-rgb'),
  transmissionReadout: $('#transmission-readout'),
  rayleighControl: $('#rayleigh-control'),
  rayleighValue: $('#rayleigh-value'),
  mieControl: $('#mie-control'),
  mieValue: $('#mie-value'),
  metricTransmission: $('#metric-transmission'),
  metricIlluminance: $('#metric-illuminance'),
  elevationControl: $('#elevation-control'),
  elevationReadout: $('#elevation-readout'),
  continuityStrip: $('#continuity-strip'),
  maxDelta: $('#max-delta'),
  coverageControl: $('#coverage-control'),
  coverageValue: $('#coverage-value'),
  thicknessControl: $('#thickness-control'),
  thicknessValue: $('#thickness-value'),
  cloudHeights: $('#cloud-heights'),
  cloudOpticalDepth: $('#cloud-optical-depth'),
  shadowPercent: $('#shadow-percent'),
  shadowFill: $('#shadow-fill'),
  cloudShadowToggle: $('#cloud-shadow-toggle'),
  directPath: $('#direct-path'),
  directArea: $('#direct-area'),
  diffusePath: $('#diffuse-path'),
  chartMarker: $('#chart-marker'),
  chartDot: $('#chart-dot')
};

const presetButtons = [...document.querySelectorAll('[data-preset]')];
let continuityTimer = 0;
let renderer = null;

function hex(rgb) {
  return rgbToHex(rgb).toUpperCase();
}

function updateSwatch(element, rgb) {
  element.style.backgroundColor = rgbToHex(rgb);
}

function formatLux(value) {
  if (value >= 1000) return (value / 1000).toFixed(1);
  return Math.round(value).toLocaleString('en-US');
}

function updatePresetState() {
  let closest = null;
  let distance = Infinity;
  for (const button of presetButtons) {
    const preset = Number(button.dataset.preset);
    const currentDistance = Math.abs(preset - state.sunElevation);
    button.classList.toggle('active', currentDistance < 0.13);
    if (currentDistance < distance) {
      distance = currentDistance;
      closest = button;
    }
  }
  if (distance > 0.13 && closest) closest.classList.remove('active');
}

function updateColorRows(sunElevation) {
  const sun = sunColor(sunElevation, state.rayleighScale, state.mieScale);
  const zenith = skyColor(89.5, sunElevation, state);
  const horizon = skyColor(0.8, sunElevation, state);
  updateSwatch(dom.sunSwatch, sun);
  updateSwatch(dom.zenithSwatch, zenith);
  updateSwatch(dom.horizonSwatch, horizon);
  dom.sunHex.textContent = hex(sun);
  dom.zenithHex.textContent = hex(zenith);
  dom.horizonHex.textContent = hex(horizon);
  dom.sunRgb.textContent = sun.join(' ');
  dom.zenithRgb.textContent = zenith.join(' ');
  dom.horizonRgb.textContent = horizon.join(' ');
  return { sun, zenith, horizon };
}

function updateSunMetrics() {
  const direction = sunDirection(state.sunElevation, state.sunAzimuth);
  const transmittance = luminance(sunTransmittance(
    state.sunElevation,
    state.rayleighScale,
    state.mieScale
  ));
  const illuminance = directIlluminance(
    state.sunElevation,
    state.rayleighScale,
    state.mieScale
  );
  dom.panelElevation.textContent = state.sunElevation.toFixed(1);
  dom.elevationReadout.textContent = state.sunElevation.toFixed(1);
  dom.sunVector.textContent = [direction.x, direction.y, direction.z]
    .map((value) => value.toFixed(3)).join(', ');
  dom.transmissionReadout.textContent = `${(transmittance * 100).toFixed(1)}%`;
  dom.metricTransmission.textContent = (transmittance * 100).toFixed(1);
  dom.metricIlluminance.textContent = formatLux(illuminance);
  return { transmittance, illuminance, direction };
}

function updateCloudMetrics() {
  const cloud = cloudProfile(state);
  dom.coverageValue.textContent = `${Math.round(cloud.coverage * 100)}%`;
  dom.thicknessValue.textContent = `${cloud.thickness.toFixed(2)} km`;
  dom.cloudHeights.textContent =
    `${cloud.baseKm.toFixed(2)} / ${cloud.topKm.toFixed(2)} km`;
  dom.cloudOpticalDepth.textContent = cloud.opticalDepth.toFixed(2);
  const shadow = cloud.shadowFraction * 100;
  dom.shadowPercent.textContent = shadow.toFixed(1);
  dom.shadowFill.style.width = `${Math.max(3, shadow)}%`;
}

function chartCoordinates() {
  const width = 300;
  const top = 8;
  const height = 64;
  const x = (scale) => 4 + (scale - 0.2) / 2.8 * (width - 8);
  const y = (value) => top + (1 - Math.max(0, Math.min(1, value))) * height;
  const directValues = [];
  const diffuseValues = [];
  const samples = 26;
  for (let i = 0; i < samples; i += 1) {
    const scale = 0.2 + (2.8 * i) / (samples - 1);
    directValues.push(luminance(sunTransmittance(
      state.sunElevation, scale, state.mieScale
    )));
    diffuseValues.push(luminance(skyColor(89.5, state.sunElevation, {
      ...state,
      rayleighScale: scale,
      exposure: 21
    })));
  }
  const maxDiffuse = Math.max(...diffuseValues, 1e-6);
  const normalizedDiffuse = diffuseValues.map((value) => value / maxDiffuse);
  const toPath = (values) => values.map((value, index) => {
    const scale = 0.2 + (2.8 * index) / (samples - 1);
    return `${index === 0 ? 'M' : 'L'}${x(scale).toFixed(2)},${y(value).toFixed(2)}`;
  }).join(' ');
  const directPath = toPath(directValues);
  const diffusePath = toPath(normalizedDiffuse);
  const markerX = x(state.rayleighScale);
  const currentDirect = luminance(sunTransmittance(
    state.sunElevation, state.rayleighScale, state.mieScale
  ));
  dom.directPath.setAttribute('d', directPath);
  dom.diffusePath.setAttribute('d', diffusePath);
  dom.directArea.setAttribute('d',
    `${directPath} L${width - 4},72 L4,72 Z`);
  dom.chartMarker.setAttribute('x1', markerX.toFixed(2));
  dom.chartMarker.setAttribute('x2', markerX.toFixed(2));
  dom.chartDot.setAttribute('cx', markerX.toFixed(2));
  dom.chartDot.setAttribute('cy', y(currentDirect).toFixed(2));
}

function buildContinuity() {
  const rows = [];
  let maxDelta = 0;
  let maxDeltaAt = 0;
  let previous = null;
  for (let elevation = -6; elevation <= 90.0001; elevation += 0.25) {
    const row = {
      elevation,
      zenith: skyColor(89.5, elevation, state),
      horizon: skyColor(0.8, elevation, state)
    };
    rows.push(row);
    if (previous) {
      const delta = Math.max(
        colorDistance(previous.zenith, row.zenith),
        colorDistance(previous.horizon, row.horizon)
      );
      if (delta > maxDelta) {
        maxDelta = delta;
        maxDeltaAt = elevation;
      }
    }
    previous = row;
  }
  const cells = [];
  for (let i = 0; i < 42; i += 1) {
    const index = Math.round(i / 41 * (rows.length - 1));
    const row = rows[index];
    const zenith = rgbToHex(row.zenith);
    const horizon = rgbToHex(row.horizon);
    cells.push(`<span class="continuity-cell" style="background:linear-gradient(180deg,${horizon},${zenith})"></span>`);
  }
  dom.continuityStrip.innerHTML = cells.join('');
  dom.maxDelta.textContent = maxDelta.toFixed(3);
  dom.continuityStrip.title =
    `最大相邻变化 ${maxDelta.toFixed(3)}，出现在 ${maxDeltaAt.toFixed(2)}°`;
  dom.continuityStrip.dataset.maxDelta = maxDelta.toFixed(4);
  dom.continuityStrip.dataset.maxDeltaAt = maxDeltaAt.toFixed(2);
  const badge = $('.pass-badge');
  badge.textContent = maxDelta < 0.2 ? 'PASS' : 'CHECK';
  badge.classList.toggle('fail', maxDelta >= 0.2);
}

function scheduleContinuity() {
  clearTimeout(continuityTimer);
  continuityTimer = setTimeout(buildContinuity, 70);
}

function updateAll() {
  updatePresetState();
  updateColorRows(state.sunElevation);
  updateSunMetrics();
  dom.rayleighValue.textContent = `${state.rayleighScale.toFixed(2)}×`;
  dom.mieValue.textContent = `${state.mieScale.toFixed(2)}×`;
  updateCloudMetrics();
  chartCoordinates();
}

function bindRange(control, key, formatter) {
  control.addEventListener('input', () => {
    state[key] = Number(control.value);
    formatter();
    updateAll();
  });
}

bindRange(dom.elevationControl, 'sunElevation', () => {
  dom.elevationControl.value = state.sunElevation;
});
bindRange(dom.rayleighControl, 'rayleighScale', () => {
  dom.rayleighValue.textContent = `${state.rayleighScale.toFixed(2)}×`;
  scheduleContinuity();
});
bindRange(dom.mieControl, 'mieScale', () => {
  dom.mieValue.textContent = `${state.mieScale.toFixed(2)}×`;
  scheduleContinuity();
});
bindRange(dom.coverageControl, 'cloudCoverage', () => {});
bindRange(dom.thicknessControl, 'cloudThickness', () => {});

dom.cloudShadowToggle.addEventListener('change', () => {
  state.cloudShadows = dom.cloudShadowToggle.checked;
  updateCloudMetrics();
});

for (const button of presetButtons) {
  button.addEventListener('click', () => {
    state.sunElevation = Number(button.dataset.preset);
    dom.elevationControl.value = state.sunElevation;
    updateAll();
  });
}

updateAll();
buildContinuity();
dom.elevationControl.value = state.sunElevation;
dom.rayleighControl.value = state.rayleighScale;
dom.mieControl.value = state.mieScale;
dom.coverageControl.value = state.cloudCoverage;
dom.thicknessControl.value = state.cloudThickness;
dom.cloudShadowToggle.checked = state.cloudShadows;

try {
  renderer = new SkyRenderer(dom.canvas, state);
  renderer.start();
  document.body.classList.add('webgl-ready');
} catch (error) {
  dom.error.hidden = false;
  dom.error.querySelector('span').textContent = error.message;
  console.error(error);
}

window.__ATMOS__ = {
  state,
  update: updateAll,
  constants: ATMOSPHERE,
  getRenderer: () => renderer
};
