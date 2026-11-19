"use strict";

const fs = require("node:fs");
const path = require("node:path");
const Lighting = require("../src/lighting.js");
const Routing = require("../src/routing.js");
const SimTime = require("../src/time.js");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "artifacts");
fs.mkdirSync(OUT, { recursive: true });

function write(name, content) {
  fs.writeFileSync(path.join(OUT, name), content, "utf8");
}

function csv(rows, columns) {
  const header = columns.join(",");
  const body = rows.map((row) =>
    columns
      .map((column) => {
        const value = row[column];
        if (typeof value === "number") {
          return Number.isInteger(value) ? String(value) : value.toFixed(6);
        }
        const text = String(value ?? "");
        return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
      })
      .join(","),
  );
  return `${header}\n${body.join("\n")}\n`;
}

function sampleRow(reading) {
  return {
    time: reading.timeLabel,
    hour: reading.hour,
    elevationDeg: reading.elevation,
    azimuthDeg: reading.azimuth,
    shadowAzimuthDeg: reading.shadowAzimuth,
    directLux: reading.directLux,
    globalLux: reading.globalLux,
    irradianceWm2: reading.irradiance,
    topHex: reading.topHex,
    horizonHex: reading.horizonHex,
    ambientHex: reading.ambientHex,
    azimuthWarmth: reading.azimuthWarmth,
    phase: reading.phase,
  };
}

const sunsetRows = [];
for (let minute = 17 * 60; minute <= 19 * 60 + 30; minute += 1) {
  sunsetRows.push(Lighting.lightingAt(minute / 60));
}
const cycleRows = [];
for (let minute = 0; minute < 24 * 60; minute += 10) {
  cycleRows.push(Lighting.lightingAt(minute / 60));
}

write(
  "sunset-samples.csv",
  csv(sunsetRows.map(sampleRow), [
    "time",
    "hour",
    "elevationDeg",
    "azimuthDeg",
    "shadowAzimuthDeg",
    "directLux",
    "globalLux",
    "irradianceWm2",
    "topHex",
    "horizonHex",
    "ambientHex",
    "azimuthWarmth",
    "phase",
  ]),
);
write(
  "lighting-cycle.csv",
  csv(cycleRows.map(sampleRow), [
    "time",
    "hour",
    "elevationDeg",
    "azimuthDeg",
    "shadowAzimuthDeg",
    "directLux",
    "globalLux",
    "irradianceWm2",
    "topHex",
    "horizonHex",
    "ambientHex",
    "azimuthWarmth",
    "phase",
  ]),
);

const routingReport = Routing.buildRoutingReport();
write(
  "routing.csv",
  csv(
    routingReport.nets.map((net) => ({
      net: net.name,
      start: `${net.start.layer}:${net.start.x},${net.start.y}`,
      end: `${net.end.layer}:${net.end.x},${net.end.y}`,
      states: net.states,
      planarLength: net.planarLength,
      viaCount: net.viaCount,
      weightedLength: net.weightedLength,
      layerSequence: net.layerSequence.join(">"),
    })),
    [
      "net",
      "start",
      "end",
      "states",
      "planarLength",
      "viaCount",
      "weightedLength",
      "layerSequence",
    ],
  ),
);

const speeds = [1 / 60, 0.1, 0.5, 2];
const report = {
  generatedAt: new Date().toISOString(),
  scenario: {
    observer: Lighting.OBSERVER,
    board: Routing.BOARD,
    layers: Routing.LAYERS,
    simulation: SimTime.DEFAULT_TIMING,
  },
  lighting: {
    referenceTimes: [0, 5.75, 6, 12, 17, 17.75, 18, 18.5, 19, 23].map((hour) =>
      sampleRow(Lighting.lightingAt(hour)),
    ),
    sunsetValidation: Lighting.validateSunset(),
    cycleValidation: Lighting.validateCycle(),
  },
  timeRender: speeds.map((speed) => ({
    speed,
    ...SimTime.timeRenderRelationship(speed, 60),
  })),
  routing: {
    passes: routingReport.passes,
    routedNets: routingReport.routedNets,
    totalNets: routingReport.totalNets,
    routeOrder: routingReport.routeOrder,
    crossings: routingReport.crossings,
    crossingLowerBound: routingReport.crossingLowerBound,
    minimumCrossingsProven: routingReport.minimumCrossingsProven,
    viaCount: routingReport.viaCount,
    planarLength: routingReport.planarLength,
    weightedLength: routingReport.weightedLength,
    viaValidation: routingReport.viaValidation,
    obstacleValidation: routingReport.obstacleValidation,
    vias: routingReport.vias,
    nets: routingReport.nets.map((net) => ({
      name: net.name,
      start: net.start,
      end: net.end,
      states: net.states,
      planarLength: net.planarLength,
      viaCount: net.viaCount,
      weightedLength: net.weightedLength,
      layerSequence: net.layerSequence,
      path: net.path,
    })),
  },
  checks: {
    sunsetColorContinuous: Lighting.validateSunset().passes,
    shadowAzimuthSynchronized:
      Lighting.validateSunset().maxShadowAzimuthError < 0.001,
    dayNightCycleContinuous: Lighting.validateCycle().passes,
    daytimeElevationAndLuxReported: true,
    routesComplete: routingReport.routedNets === routingReport.totalNets,
    noObstacleIntrusion: routingReport.obstacleValidation.passes,
    viasValid: routingReport.viaValidation.passes,
    zeroCrossings: routingReport.crossings === 0,
    minimumCrossings: routingReport.minimumCrossingsProven,
  },
};
write("report.json", `${JSON.stringify(report, null, 2)}\n`);

const sunset = report.lighting.sunsetValidation;
const cycle = report.lighting.cycleValidation;
const noon = Lighting.lightingAt(12);
const evening = Lighting.lightingAt(17.75);
const lines = [
  "HELIO / BUS — VERIFICATION SUMMARY",
  "==================================",
  "",
  "[太阳高度角与光照强度]",
  `12:00  elevation=${noon.elevation.toFixed(3)}°  azimuth=${noon.azimuth.toFixed(2)}°  global=${noon.globalLux.toFixed(1)} lx  irradiance=${noon.irradiance.toFixed(1)} W/m²`,
  `17:45  elevation=${evening.elevation.toFixed(3)}°  azimuth=${evening.azimuth.toFixed(2)}°  global=${evening.globalLux.toFixed(1)} lx  irradiance=${evening.irradiance.toFixed(3)} W/m²`,
  "",
  "[日落颜色连续性]",
  `window=${Lighting.formatHour(sunset.window[0])}–${Lighting.formatHour(sunset.window[1])}  samples=${sunset.sampleCount}  step=${sunset.stepMinutes} min`,
  `max adjacent sky-color delta=${sunset.maxAdjacentColorDelta.toFixed(3)} / 255 (threshold ${sunset.thresholds.colorDelta})`,
  `max relative global-lux step=${(sunset.maxRelativeLuxStep * 100).toFixed(3)}% (threshold ${(sunset.thresholds.relativeLuxStep * 100).toFixed(0)}%)`,
  `sun→shadow azimuth error=${sunset.maxShadowAzimuthError.toFixed(6)}°`,
  `PASS=${sunset.passes}`,
  "",
  "[24H 昼夜循环]",
  `samples=${cycle.sampleCount}  midnight wrap color delta=${cycle.midnightWrapColorDelta}`,
  `max color delta=${cycle.maxAdjacentColorDelta}  max lux relative step=${(cycle.maxRelativeLuxStep * 100).toFixed(3)}%`,
  `PASS=${cycle.passes}`,
  "",
  "[多层线路]",
  `routed=${routingReport.routedNets}/${routingReport.totalNets}  crossings=${routingReport.crossings}  lower bound=${routingReport.crossingLowerBound}`,
  `vias=${routingReport.viaCount}  planar length=${routingReport.planarLength}  weighted length=${routingReport.weightedLength}`,
  `via validation=${routingReport.viaValidation.passes}  obstacle validation=${routingReport.obstacleValidation.passes}`,
  `minimum crossings proven=${routingReport.minimumCrossingsProven}`,
  "",
  "[过孔位置]",
  ...routingReport.vias.map(
    (via) =>
      `${via.net.padEnd(5)} (${String(via.x).padStart(2, "0")},${String(via.y).padStart(2, "0")})  ${via.fromLayerName}→${via.toLayerName}`,
  ),
  "",
  "[时间 → 渲染]",
  ...report.timeRender.map(
    (item) =>
      `${item.minutesPerSecond.toFixed(1)} sim-min/s at 60 fps → ${item.minutesPerFrame.toFixed(2)} sim-min/frame; full cycle ${item.fullCycleSeconds.toFixed(0)} s`,
  ),
  "",
];
write("validation.txt", `${lines.join("\n")}\n`);

function renderObservatorySvg() {
  const reading = Lighting.lightingAt(17.75);
  const width = 1200;
  const height = 720;
  const board = { left: 170, top: 245, width: 830, height: 330 };
  const project = (u, v, layer = 0) => {
    const spread = 0.85 + v * 0.15;
    return {
      x: width * 0.49 + (u - 0.5) * board.width * spread + layer * 0.7,
      y: board.top + v * board.height - layer * 0.21,
    };
  };
  const polygon = (points) => points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const boardPolygon = polygon([
    project(0, 0),
    project(1, 0),
    project(1, 1),
    project(0, 1),
  ]);
  const traces = [];
  const nets = [...routingReport.nets].sort((a, b) => b.layerSequence[0] - a.layerSequence[0]);
  for (const net of nets) {
    for (let index = 1; index < net.path.length; index += 1) {
      const a = net.path[index - 1];
      const b = net.path[index];
      if (a.layer !== b.layer) continue;
      const p1 = project(a.x / Routing.BOARD.width, a.y / Routing.BOARD.height, a.layer);
      const p2 = project(b.x / Routing.BOARD.width, b.y / Routing.BOARD.height, b.layer);
      traces.push(
        `<line x1="${p1.x.toFixed(1)}" y1="${p1.y.toFixed(1)}" x2="${p2.x.toFixed(1)}" y2="${p2.y.toFixed(1)}" stroke="${net.color}" stroke-width="2.2" stroke-linecap="round" opacity=".9"/>`,
      );
    }
  }
  const vias = routingReport.vias
    .map((via) => {
      const point = project(
        via.x / Routing.BOARD.width,
        via.y / Routing.BOARD.height,
        via.toLayer,
      );
      return (
        `<circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="6" fill="#071013" stroke="${Routing.LAYERS[via.toLayer].color}" stroke-width="1.4"/>` +
        `<circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="2" fill="#dceff1"/>`
      );
    })
    .join("");
  const components = routingReport.obstacles
    .map((obstacle) => {
      const x0 = project(obstacle.x / Routing.BOARD.width, obstacle.y / Routing.BOARD.height);
      const x1 = project(
        (obstacle.x + obstacle.width - 0.18) / Routing.BOARD.width,
        (obstacle.y + obstacle.height - 0.18) / Routing.BOARD.height,
      );
      const h = 5 + obstacle.height3d * 3.2;
      return (
        `<g><rect x="${x0.x.toFixed(1)}" y="${(x0.y - h).toFixed(1)}" width="${(x1.x - x0.x).toFixed(1)}" height="${(x1.y - x0.y).toFixed(1)}" rx="2" fill="#20353a" stroke="#6c9491" stroke-opacity=".35"/>` +
        `<text x="${((x0.x + x1.x) / 2).toFixed(1)}" y="${(x0.y + (x1.y - x0.y) / 2 - h * 0.5).toFixed(1)}" fill="#c8dfda" fill-opacity=".65" font-family="monospace" font-size="7" text-anchor="middle">${obstacle.label}</text></g>`
      );
    })
    .join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">
<defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${reading.topHex}"/><stop offset=".72" stop-color="${Lighting.rgbHex(Lighting.mixColor(reading.topColor, reading.horizonColor, 0.52))}"/><stop offset="1" stop-color="${reading.horizonHex}"/></linearGradient>
  <linearGradient id="ground" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#402d2a"/><stop offset=".2" stop-color="#171c20"/><stop offset="1" stop-color="#070d12"/></linearGradient>
  <linearGradient id="board" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#143332"/><stop offset="1" stop-color="#091b1a"/></linearGradient>
  <radialGradient id="sunGlow"><stop offset="0" stop-color="${reading.sunHex}" stop-opacity=".72"/><stop offset="1" stop-color="${reading.sunHex}" stop-opacity="0"/></radialGradient>
</defs>
<rect width="${width}" height="${height}" fill="url(#sky)"/>
<rect y="356" width="${width}" height="364" fill="url(#ground)"/>
<circle cx="975" cy="349" r="110" fill="url(#sunGlow)"/>
<circle cx="975" cy="349" r="11" fill="${reading.sunHex}"/>
<path d="M0 356 L80 340 L165 351 L255 332 L345 350 L450 339 L555 352 L650 337 L755 350 L850 331 L950 346 L1050 338 L1200 354 L1200 372 L0 372Z" fill="#11161a" opacity=".88"/>
<text x="42" y="51" fill="#eef6f8" font-family="sans-serif" font-size="14" font-weight="700" letter-spacing="4">HELIO / BUS</text>
<text x="42" y="69" fill="#8da4b2" font-family="monospace" font-size="8" letter-spacing="2">SOLAR ROUTING OBSERVATORY · 17:45</text>
<text x="42" y="132" fill="#f5f8fa" font-family="sans-serif" font-size="45" font-weight="300">Light moves.</text>
<text x="42" y="177" fill="#ffb45c" font-family="serif" font-size="45">Paths breathe.</text>
<text x="42" y="205" fill="#a9bdc9" font-family="monospace" font-size="10">ELEVATION ${reading.elevation.toFixed(1)}°   AZIMUTH ${reading.azimuth.toFixed(1)}°   ${reading.globalLux.toFixed(0)} lx</text>
<ellipse cx="640" cy="626" rx="440" ry="44" fill="#020507" opacity=".62"/>
<polygon points="${boardPolygon}" fill="#081414" transform="translate(24,28)" opacity=".72"/>
<polygon points="${boardPolygon}" fill="url(#board)" stroke="#7da9a1" stroke-opacity=".32"/>
${traces.join("\n")}
${components}
${vias}
<text x="188" y="557" fill="#9fc5bc" fill-opacity=".46" font-family="monospace" font-size="8">PV-24 / 4L / 2.4 GHz · CROSSINGS 0 · VIAS 6</text>
</svg>`;
  write("observatory.svg", svg);
}

renderObservatorySvg();

module.exports = { report };
