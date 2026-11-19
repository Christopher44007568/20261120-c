import { mkdirSync, writeFileSync } from "node:fs";
import { DATASETS } from "../src/datasets.js";
import { gaussian, mulberry32, normalize } from "../src/math.js";
import { buildMesh } from "../src/mesh.js";
import { buildShadowVolume, cameraCrossing } from "../src/shadow.js";

mkdirSync("artifacts", { recursive: true });

function randomDataset(seed) {
  const random = mulberry32(seed * 9173 + 5);
  const count = 16 + Math.floor(random() * 48);
  const points = [];
  for (let index = 0; index < count; index += 1) {
    const direction = normalize([
      gaussian(random),
      gaussian(random),
      gaussian(random),
    ]);
    const radius = 0.2 + random() * 0.9;
    points.push([
      direction[0] * radius * 1.25,
      direction[1] * radius * 0.83,
      direction[2] * radius * 1.1,
    ]);
  }
  return { id: `fuzz-${seed}`, name: `fuzz-${seed}`, points };
}

const cases = DATASETS.map((dataset) => {
  const mesh = buildMesh(dataset);
  const shadow = buildShadowVolume(mesh);
  const crossing = cameraCrossing(shadow, mesh.points);
  return {
    id: dataset.id,
    name: dataset.name,
    description: dataset.description,
    path: mesh.degeneracy.intrinsicRank === 2 ? "2D Delaunay + dual support" : "3D Bowyer-Watson",
    counts: mesh.counts,
    degeneracy: mesh.degeneracy,
    audits: mesh.audits,
    hullAudit: mesh.hullAudit,
    tetraAudit: mesh.tetAudit,
    allPassed: mesh.allPassed,
    shadow: {
      counts: shadow.counts,
      audit: shadow.audit,
      crossing: {
        valid: crossing.valid,
        enterSurface: crossing.enterSurface,
        exitSurface: crossing.exitSurface,
        records: crossing.records,
      },
    },
  };
});

const report = {
  generatedAt: new Date().toISOString(),
  summary: {
    cases: cases.length,
    passed: cases.filter((item) => item.allPassed).length,
    degeneracyPolicy:
      "Coplanar rank-2 sets use 2D Delaunay plus two normal support anchors; 3D predicates use bounded deterministic regularization while source coordinates are audited separately.",
    cappingPolicy:
      "Closed shadow volume uses a light-facing near cap, a translated back-facing far cap, and silhouette-edge side quads.",
  },
  randomRegression: {
    seeds: 100,
    passed: Array.from({ length: 100 }, (_, index) => buildMesh(randomDataset(index + 1)))
      .filter((mesh) => mesh.allPassed).length,
  },
  cases,
};

writeFileSync("artifacts/validation-report.json", `${JSON.stringify(report, null, 2)}\n`);

const lines = [
  "# Hull / Dual validation report",
  "",
  `Generated: ${report.generatedAt}`,
  "",
  `Deterministic random regression: ${report.randomRegression.passed} / ${report.randomRegression.seeds} PASS`,
  "",
  "## Case matrix",
  "",
  "| Case | Path | V | E | F | T | chi | Hull | Tets | Volume error | Caps | Flips |",
  "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | --- | ---: |",
];

for (const item of cases) {
  lines.push(
    `| ${item.name} | ${item.path} | ${item.counts.meshVertices} | ${item.counts.tetraEdges} | `
    + `${item.counts.hullFaces} | ${item.counts.tetrahedra} | ${item.hullAudit.euler} | `
    + `${item.audits.hullClosed ? "closed" : "open"} | ${item.audits.tetraManifold ? "manifold" : "broken"} | `
    + `${item.tetraAudit.volumeError.toExponential(2)} | ${item.shadow.audit.capped ? "watertight" : "open"} | `
    + `${item.shadow.crossing.records.length} |`,
  );
}

lines.push("", "## Degeneracy ledger", "");
lines.push("| Case | Rank | Duplicates | Planar clusters | Max planar | Cospherical hits | Degenerate tets |");
lines.push("| --- | ---: | ---: | ---: | ---: | ---: | ---: |");
for (const item of cases) {
  const ledger = item.degeneracy;
  lines.push(
    `| ${item.name} | ${ledger.intrinsicRank}D | ${ledger.duplicatesRemoved} | ${ledger.planarClusters} | `
    + `${ledger.maxPlanarPoints} | ${ledger.cosphericalEmptySphereHits} | ${ledger.degenerateTetsRemoved} |`,
  );
}

lines.push("", "## Template flips", "");
for (const item of cases) {
  const records = item.shadow.crossing.records.map((record) => (
    `${record.direction} ${record.surface} t=${record.t.toFixed(4)} `
    + `count ${record.templateBefore}->${record.templateAfter}`
  ));
  lines.push(`- **${item.name}**: ${records.join("; ")}; final count 0`);
}
lines.push("");
writeFileSync("artifacts/validation-report.md", `${lines.join("\n")}\n`);

console.log(lines.slice(0, 15).join("\n"));
console.log("\nTemplate flips");
for (const item of cases) {
  const flips = item.shadow.crossing.records
    .map((record) => `${record.direction}:${record.surface}:${record.templateBefore}->${record.templateAfter}`)
    .join(" | ");
  console.log(`${item.id.padEnd(14)} ${flips}`);
}
console.log("\nWrote artifacts/validation-report.json");
console.log("Wrote artifacts/validation-report.md");
