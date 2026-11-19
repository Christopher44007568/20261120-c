import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { deflateSync } from "node:zlib";
import { buildContinuitySummary, buildConvergence, buildDirectionSets, summarizeContinuity } from "../src/analysis.js";
import { initLTCData } from "../src/ltc.js";
import { validateScene } from "../src/mesh.js";
import {
  compareImages,
  imageToRGBA,
  matrixSweep,
  maxSweepStep,
  renderSurface,
} from "../src/render.js";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const artifacts = resolve(root, "artifacts");
mkdirSync(artifacts, { recursive: true });

const tablePath = resolve(root, "src/ltc-data.bin");
const table = readFileSync(tablePath);
const tableSha256 = createHash("sha256").update(table).digest("hex");
initLTCData(table.buffer.slice(table.byteOffset, table.byteOffset + table.byteLength));

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const typeBuffer = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])));
  return Buffer.concat([length, typeBuffer, data, crc]);
}

function encodePNG(width, height, rgba) {
  const stride = width * 4;
  const raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y += 1) {
    raw[y * (stride + 1)] = 0;
    Buffer.from(rgba.buffer, rgba.byteOffset + y * stride, stride)
      .copy(raw, y * (stride + 1) + 1);
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = 6;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk("IHDR", header),
    pngChunk("IDAT", deflateSync(raw, { level: 9 })),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function writePNG(name, image, scale) {
  const rgba = imageToRGBA(image, scale);
  const buffer = encodePNG(image.width, image.height, rgba);
  writeFileSync(resolve(artifacts, name), buffer);
  return { file: `artifacts/${name}`, bytes: buffer.length };
}

function escapeXML(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function continuitySVG(sweep, continuity) {
  const width = 1000;
  const height = 500;
  const left = 72;
  const top = 50;
  const right = 970;
  const bottom = 430;
  const yMin = -0.42;
  const yMax = 1.42;
  const x = (roughness) => left + (right - left) * roughness;
  const y = (value) => bottom - (bottom - top) * ((value - yMin) / (yMax - yMin));
  const colors = ["#58c9c1", "#6f9dff", "#f0b45f", "#e7869b"];
  const names = ["a", "b", "c", "d"];
  const lines = names.map((name, channel) => {
    const points = sweep
      .map((entry) => `${x(entry.roughness).toFixed(2)},${y(entry.values[channel]).toFixed(2)}`)
      .join(" ");
    return `<polyline points="${points}" fill="none" stroke="${colors[channel]}" stroke-width="2.2"/>`;
  }).join("\n");
  const markers = continuity.boundaries.map((entry) =>
    `<line x1="${x(entry.roughness)}" y1="${top}" x2="${x(entry.roughness)}" y2="${bottom}" stroke="#f0b45f" stroke-opacity=".35" stroke-dasharray="4 5"/>` +
    `<text x="${x(entry.roughness)}" y="${bottom + 24}" fill="#8b95a8" font-size="11" text-anchor="middle">α ${entry.roughness.toFixed(2)}</text>`,
  ).join("\n");
  const legend = names.map((name, channel) =>
    `<rect x="${left + channel * 120}" y="20" width="18" height="3" fill="${colors[channel]}"/>` +
    `<text x="${left + 24 + channel * 120}" y="25" fill="#e8ebf2" font-size="12">M⁻¹ ${name}</text>`,
  ).join("\n");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="${width}" height="${height}" fill="#0a0d13"/>
  <text x="${left}" y="${height - 16}" fill="#8b95a8" font-size="12">roughness α · continuous bilinear sampling</text>
  <text x="18" y="${top + 6}" fill="#8b95a8" font-size="12" transform="rotate(-90 18 ${top + 6})">LTC matrix element</text>
  ${legend}
  ${markers}
  <line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}" stroke="#2a3040"/>
  <line x1="${left}" y1="${top}" x2="${left}" y2="${bottom}" stroke="#2a3040"/>
  ${lines}
  <text x="${right - 10}" y="${bottom - 16}" fill="#f0b45f" font-size="12" text-anchor="end">max adjacent Δ ${maxSweepStep(sweep).toFixed(5)}</text>
  <text x="${right - 10}" y="${bottom - 34}" fill="#6fd1a1" font-size="12" text-anchor="end">continuous boundary jump ${(continuity.maxContinuousJump * 100).toFixed(4)}%</text>
  <text x="${right - 10}" y="${bottom - 52}" fill="#e37b72" font-size="12" text-anchor="end">quantized control jump ${(continuity.maxQuantizedJump * 100).toFixed(2)}%</text>
  <text x="${left}" y="${top - 14}" fill="#e8ebf2" font-size="16">LTC matrix vs roughness — no step at α = 0.14 / 0.32 / 0.58</text>
</svg>\n`;
}

const roughness = 0.12;
const renderWidth = 360;
const renderHeight = 220;
const sampleCount = 32;
const images = {};
const imageMetrics = {};

for (const emitter of ["rect", "disk"]) {
  const analytic = renderSurface({
    width: renderWidth,
    height: renderHeight,
    emitter,
    roughnessMode: "fixed",
    roughness,
    method: "ltc",
  });
  const sampled = renderSurface({
    width: renderWidth,
    height: renderHeight,
    emitter,
    roughnessMode: "fixed",
    roughness,
    method: "mc",
    spp: sampleCount,
    seed: 7,
  });
  const scale = 1 / Math.max(analytic.peak * 1.04, 1e-9);
  imageMetrics[emitter] = compareImages(analytic, sampled, scale);
  images[`${emitter}Analytic`] = writePNG(`${emitter}-ltc.png`, analytic, scale);
  images[`${emitter}Sampled`] = writePNG(`${emitter}-mc-${sampleCount}spp.png`, sampled, scale);
}

const gradientAnalytic = renderSurface({
  width: 620,
  height: 168,
  emitter: "rect",
  roughnessMode: "gradient",
  method: "ltc",
});
const gradientSampled = renderSurface({
  width: 620,
  height: 168,
  emitter: "rect",
  roughnessMode: "gradient",
  method: "mc",
  spp: sampleCount,
  seed: 9,
});
const gradientScale = 1 / Math.max(gradientAnalytic.peak * 1.04, 1e-9);
imageMetrics.gradient = compareImages(gradientAnalytic, gradientSampled, gradientScale);
images.gradientAnalytic = writePNG("roughness-gradient-ltc.png", gradientAnalytic, gradientScale);
images.gradientSampled = writePNG(`roughness-gradient-mc-${sampleCount}spp.png`, gradientSampled, gradientScale);

const sweep = matrixSweep(0.7, 401);
const continuity = buildContinuitySummary();
const continuitySummary = summarizeContinuity(continuity);
const directions = buildDirectionSets(512, 19);
const convergence = {
  rect: buildConvergence("rect", { roughness: 0.24, seeds: 8 }),
  disk: buildConvergence("disk", { roughness: 0.24, seeds: 8 }),
};

const validScene = JSON.parse(readFileSync(resolve(root, "fixtures/valid-scene.json"), "utf8"));
const invalidScene = JSON.parse(readFileSync(resolve(root, "fixtures/nonwatertight-scene.json"), "utf8"));
const validReport = validateScene(validScene);
const invalidReport = validateScene(invalidScene);

const checks = [
  {
    name: "valid fixture passes",
    pass: validReport.valid && validReport.mesh.stats.boundaryEdges === 0,
  },
  {
    name: "non-watertight fixture rejected",
    pass: !invalidReport.valid && invalidReport.mesh.stats.boundaryEdges === 4,
  },
  {
    name: "rect highlight shape",
    pass: imageMetrics.rect.shapeIoU > 0.75 && imageMetrics.rect.energyError < 0.15,
  },
  {
    name: "disk highlight shape",
    pass: imageMetrics.disk.shapeIoU > 0.75 && imageMetrics.disk.energyError < 0.15,
  },
  {
    name: "continuous roughness boundary",
    pass: continuitySummary.maxContinuousJump < 0.01,
  },
  {
    name: "quantized control exposes jump",
    pass: continuitySummary.maxQuantizedJump > 0.1,
  },
  {
    name: "matrix sweep is continuous",
    pass: maxSweepStep(sweep) < 0.02,
  },
  {
    name: "1024 spp luminance error",
    pass: convergence.rect.points.at(-1).relativeError < 0.02 &&
      convergence.disk.points.at(-1).relativeError < 0.02,
  },
];

const report = {
  schema: "ltc-area-light-validation/1",
  generatedAt: new Date().toISOString(),
  success: checks.every((check) => check.pass),
  source: {
    method: "Real-Time Polygonal-Light Shading with Linearly Transformed Cosines",
    citation: "Heitz, Dupuy, Hill, Neubelt, ACM TOG 35(4), 2016",
    table: "three.js r170 RectAreaLightTexturesLib, 64x64 RGBA x 2",
    tableBytes: table.length,
    tableSha256,
  },
  configuration: {
    roughness,
    sampleCount,
    resolution: [renderWidth, renderHeight],
    matrixSweepNdotV: 0.7,
    matrixSweepSamples: sweep.length,
    directionCountPerRoughness: 512,
    convergenceProbeRoughness: 0.24,
  },
  matrixSweep: sweep.map((entry) => ({
    roughness: entry.roughness,
    a: entry.values[0],
    b: entry.values[1],
    c: entry.values[2],
    d: entry.values[3],
    determinant: entry.values[0] * entry.values[3] - entry.values[1] * entry.values[2],
  })),
  continuity: {
    boundaries: continuity.boundaryRoughness,
    rect: continuity.rect,
    disk: continuity.disk,
    summary: continuitySummary,
  },
  directions,
  convergence,
  imageMetrics,
  images,
  fixtures: {
    valid: { name: validScene.name, valid: validReport.valid, findings: validReport.findings, mesh: validReport.mesh },
    invalid: { name: invalidScene.name, valid: invalidReport.valid, findings: invalidReport.findings, mesh: invalidReport.mesh },
  },
  checks,
};

const csvRows = ["roughness,ndotv,a,b,c,d,determinant"];
for (const entry of matrixSweep(0.7, 1001)) {
  const [a, b, c, d] = entry.values;
  csvRows.push([
    entry.roughness.toFixed(6),
    "0.7",
    a.toFixed(9),
    b.toFixed(9),
    c.toFixed(9),
    d.toFixed(9),
    (a * d - b * c).toFixed(9),
  ].join(","));
}

const directionRows = ["roughness,index,x,y,z"];
for (const set of directions) {
  set.directions.forEach((direction, index) => {
    directionRows.push([
      set.roughness.toFixed(3),
      index,
      direction[0].toFixed(9),
      direction[1].toFixed(9),
      direction[2].toFixed(9),
    ].join(","));
  });
}

writeFileSync(resolve(artifacts, "validation-report.json"), `${JSON.stringify(report, null, 2)}\n`);
writeFileSync(resolve(artifacts, "ltc-matrix-sweep.csv"), `${csvRows.join("\n")}\n`);
writeFileSync(resolve(artifacts, "sampling-directions.csv"), `${directionRows.join("\n")}\n`);
writeFileSync(
  resolve(artifacts, "ltc-continuity.svg"),
  continuitySVG(sweep, {
    ...continuity.rect,
    boundaries: continuity.boundaryRoughness.map((value) => ({ roughness: value })),
  }),
);

const passed = checks.filter((check) => check.pass).length;
const text = [
  "LTC area-light validation",
  `status: ${report.success ? "PASS" : "FAIL"} (${passed}/${checks.length})`,
  `rect  IoU=${imageMetrics.rect.shapeIoU.toFixed(3)} energyError=${(imageMetrics.rect.energyError * 100).toFixed(2)}%`,
  `disk  IoU=${imageMetrics.disk.shapeIoU.toFixed(3)} energyError=${(imageMetrics.disk.energyError * 100).toFixed(2)}%`,
  `continuous boundary max jump=${(continuitySummary.maxContinuousJump * 100).toFixed(4)}%`,
  `quantized control jump=${(continuitySummary.maxQuantizedJump * 100).toFixed(2)}%`,
  `1024 spp error rect=${(convergence.rect.points.at(-1).relativeError * 100).toFixed(3)}% disk=${(convergence.disk.points.at(-1).relativeError * 100).toFixed(3)}%`,
  `valid fixture boundaryEdges=${validReport.mesh.stats.boundaryEdges} euler=${validReport.mesh.stats.euler}`,
  `invalid fixture boundaryEdges=${invalidReport.mesh.stats.boundaryEdges} euler=${invalidReport.mesh.stats.euler}`,
  "",
  ...checks.map((check) => `${check.pass ? "[ok]" : "[FAIL]"} ${check.name}`),
  "",
  "artifacts:",
  "  artifacts/validation-report.json",
  "  artifacts/ltc-matrix-sweep.csv",
  "  artifacts/sampling-directions.csv",
  "  artifacts/ltc-continuity.svg",
  "  artifacts/rect-ltc.png",
  "  artifacts/rect-mc-32spp.png",
  "  artifacts/disk-ltc.png",
  "  artifacts/disk-mc-32spp.png",
  "  artifacts/roughness-gradient-ltc.png",
  "  artifacts/roughness-gradient-mc-32spp.png",
].join("\n");
writeFileSync(resolve(artifacts, "acceptance.txt"), `${text}\n`);
console.log(text);
if (!report.success) process.exitCode = 1;
