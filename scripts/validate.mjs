import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { strict as assert } from "node:assert";
import { validateSoftBody } from "../src/sim.js";
import {
  paintSpectrum,
  colorResponse,
  energyAudit,
  PAINT_PRESETS,
} from "../src/paint.js";

const validation = validateSoftBody();
const paint = Object.entries(PAINT_PRESETS).map(([key, preset]) => {
  const spectrum = paintSpectrum(key, 35);
  return {
    key,
    name: preset.name,
    angleDeg: spectrum.angle,
    energy: {
      reflection: spectrum.totals.R,
      transmission: spectrum.totals.T,
      absorption: spectrum.totals.A,
      total: spectrum.energyTotal,
      maxAuditError: energyAudit(key).maxError,
    },
    spectrum: {
      wavelengths: spectrum.wavelengths,
      reflection: spectrum.reflectances,
      transmission: spectrum.transmissions,
      absorption: spectrum.absorptions,
    },
    colorResponse: colorResponse(key),
  };
});

const report = {
  generatedAt: new Date().toISOString(),
  model: {
    simulation: "Position-based dynamics, 4x4x4 validation lattice, 13-neighborhood distance constraints",
    validation: "Fixed strain 18%, stiffness 0.82, 3 seeded repeats, 60 steps per case",
    errorDefinition: "RMS vertex distance to the 64-iteration reference solution after the loading frame",
    stabilityDefinition: "Mean volume error plus mean peak residual velocity over the loading window",
    paint: "Incoherent four-layer spectral transport with Fresnel and multiple internal reflections",
  },
  validation,
  paint,
};

const outputPath = fileURLToPath(new URL("../artifacts/validation-report.json", import.meta.url));
await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`);

console.log("PBD SOFT-BODY VALIDATION");
console.log("iter  compression%  stretch%  vertex err mm  jitter  stability  result");
for (const row of validation.byIteration) {
  console.log([
    String(row.iterations).padStart(4),
    row.compressVolume.toFixed(3).padStart(12),
    row.stretchVolume.toFixed(3).padStart(9),
    row.vertexError.toFixed(3).padStart(13),
    row.jitter.toFixed(3).padStart(7),
    row.stability.toFixed(1).padStart(10),
    row.stable ? "PASS" : "ITERATE",
  ].join("  "));
}
console.log(`\nStable from ${validation.summary.stableAt}x; jitter reduction ${validation.summary.jitterReduction.toFixed(1)}%.`);

console.log("\nMULTILAYER PAINT ENERGY AUDIT");
for (const entry of paint) {
  const e = entry.energy;
  console.log(
    `${entry.name.padEnd(13)} R=${(e.reflection * 100).toFixed(2)}%  `
    + `T=${(e.transmission * 100).toFixed(2)}%  A=${(e.absorption * 100).toFixed(2)}%  `
    + `sum=${(e.total * 100).toFixed(6)}%  max|R+T+A-1|=${e.maxAuditError.toExponential(2)}`,
  );
}

assert(validation.summary.maxCompressVolumeError < 1, "compression volume drift exceeds 1%");
assert(validation.summary.maxStretchVolumeError < 1, "stretch volume drift exceeds 1%");
assert(validation.summary.jitterReduction > 90, "iteration count did not improve stability enough");
assert.equal(validation.summary.stableAt <= 4, true, "stable envelope was not reached by 4 iterations");
for (const entry of paint) {
  assert(entry.energy.maxAuditError < 1e-12, `${entry.name} violates energy conservation`);
  assert(Math.abs(entry.energy.total - 1) < 1e-12, `${entry.name} total energy is not 1`);
}
console.log("\nALL CHECKS PASSED");
console.log(`\nWrote ${outputPath}`);
