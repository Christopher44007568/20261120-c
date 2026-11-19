import assert from "node:assert/strict";
import { DATASETS } from "../src/datasets.js";
import { gaussian, mulberry32, normalize } from "../src/math.js";
import { buildMesh } from "../src/mesh.js";
import { buildShadowVolume, cameraCrossing } from "../src/shadow.js";

const expectedCounts = {
  random: [46, 246, 54, 174],
  coplanar: [42, 186, 22, 134],
  cospherical: [38, 159, 72, 86],
  mixed: [51, 277, 56, 199],
  "mixed-extra": [74, 378, 102, 254],
};

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

function assertMesh(mesh) {
  assert.equal(mesh.error, null);
  assert.equal(mesh.allPassed, true, "mesh validation failed");
  assert.equal(mesh.hullAudit.closed, true, "hull is not closed");
  assert.equal(mesh.hullAudit.orientable, true, "hull orientation is inconsistent");
  assert.equal(mesh.hullAudit.euler, 2, "hull Euler characteristic is not 2");
  assert.equal(mesh.hullAudit.edgeIncidenceErrors, 0);
  assert.equal(mesh.hullAudit.orientationErrors, 0);
  assert.equal(mesh.hullAudit.volume > 0, true);
  assert.equal(mesh.hullAudit.edges * 2, mesh.hullAudit.faces * 3);
  assert.equal(mesh.tetAudit.manifold, true, "tetrahedra are non-manifold");
  assert.equal(mesh.tetAudit.components, 1, "tetrahedra are disconnected");
  assert.equal(mesh.tetAudit.boundaryEuler, 2, "tetra boundary Euler characteristic is not 2");
  assert.equal(mesh.tetAudit.internalFaceErrors, 0);
  assert.equal(mesh.tetAudit.boundaryOrientationErrors, 0);
  assert.equal(mesh.tetAudit.negativeTets, 0, "degenerate tetrahedron present");
  assert.equal(mesh.tetAudit.emptySphereViolations, 0, "Delaunay empty-sphere violation");
  assert.equal(mesh.tetAudit.unusedVertices, 0);
  assert.ok(mesh.tetAudit.minVolume > 0);
  assert.ok(mesh.tetAudit.volumeError < 2e-5, "tetra volume does not match hull");
  assert.equal(mesh.counts.boundaryFaces, mesh.counts.hullFaces);
  assert.equal(mesh.audits.hullClosed, true);
  assert.equal(mesh.audits.tetraTopology, true);
  assert.equal(mesh.audits.volumeConserved, true);
  assert.equal(mesh.audits.delaunayEmpty, true);
  assert.equal(mesh.audits.noDegenerateTets, true);
}

function assertShadow(mesh) {
  const shadow = buildShadowVolume(mesh);
  assert.equal(shadow.audit.capped, true, "shadow volume is not capped");
  assert.equal(shadow.audit.closed, true);
  assert.equal(shadow.audit.orientable, true);
  assert.equal(shadow.audit.euler, 2);
  assert.equal(shadow.audit.badEdges, 0);
  assert.equal(shadow.audit.badDirected, 0);
  assert.ok(shadow.audit.volume > 0);
  assert.ok(shadow.counts.nearCapFaces > 0);
  assert.ok(shadow.counts.farCapFaces > 0);
  assert.ok(shadow.counts.sideFaces > 0);
  assert.ok(shadow.counts.silhouetteEdges > 0);
  assert.equal(
    shadow.counts.templateTriangles,
    shadow.counts.nearCapFaces + shadow.counts.farCapFaces + shadow.counts.sideFaces,
  );
  const crossing = cameraCrossing(shadow, mesh.points);
  assert.equal(crossing.valid, true, "camera traversal did not resolve two cap crossings");
  assert.equal(crossing.records.length, 2);
  assert.equal(crossing.records[0].direction, "enter");
  assert.equal(crossing.records[0].surface, "near-cap");
  assert.equal(crossing.records[0].delta, 1);
  assert.equal(crossing.records[1].direction, "exit");
  assert.ok(["far-cap", "side"].includes(crossing.records[1].surface));
  assert.equal(crossing.records[1].delta, -1);
  assert.equal(crossing.finalInside, false);
  return { shadow, crossing };
}

console.log("case              V     E     F     T    chi  hull  tet   volume-err  caps  flips");
for (const dataset of DATASETS) {
  const mesh = buildMesh(dataset);
  assertMesh(mesh);
  const counts = [
    mesh.counts.meshVertices,
    mesh.counts.tetraEdges,
    mesh.counts.hullFaces,
    mesh.counts.tetrahedra,
  ];
  assert.deepEqual(counts, expectedCounts[dataset.id], `${dataset.id} count regression`);
  const { shadow, crossing } = assertShadow(mesh);
  console.log(
    `${dataset.id.padEnd(16)}`
    + `${String(counts[0]).padStart(4)}  ${String(counts[1]).padStart(4)}  `
    + `${String(counts[2]).padStart(4)}  ${String(counts[3]).padStart(4)}  `
    + `${String(mesh.hullAudit.euler).padStart(3)}  `
    + `${(mesh.hullAudit.closed ? "YES" : "NO").padStart(4)}  `
    + `${(mesh.tetAudit.manifold ? "YES" : "NO").padStart(3)}  `
    + `${mesh.tetAudit.volumeError.toExponential(1).padStart(10)}  `
    + `${(shadow.audit.capped ? "PASS" : "FAIL").padStart(4)}  `
    + `${crossing.records.length}`,
  );
}

const coplanar = buildMesh(DATASETS.find((dataset) => dataset.id === "coplanar"));
assert.equal(coplanar.degeneracy.intrinsicRank, 2);
assert.equal(coplanar.degeneracy.syntheticAnchors, 2);
assert.equal(coplanar.counts.uniqueVertices, 40);
assert.ok(coplanar.degeneracy.planarClusters >= 1);

const cospherical = buildMesh(DATASETS.find((dataset) => dataset.id === "cospherical"));
assert.equal(cospherical.degeneracy.intrinsicRank, 3);
assert.ok(cospherical.degeneracy.cosphericalEmptySphereHits > 0);
assert.equal(cospherical.degeneracy.degenerateTetsRemoved, 0);

const mixedExtra = buildMesh(DATASETS.find((dataset) => dataset.id === "mixed-extra"));
assert.equal(mixedExtra.degeneracy.duplicatesRemoved, 3);
assert.ok(mixedExtra.degeneracy.planarClusters >= 1);
assert.ok(mixedExtra.degeneracy.cosphericalEmptySphereHits > 0);
assert.equal(mixedExtra.degeneracy.degenerateTetsRemoved, 0);

for (let seed = 1; seed <= 100; seed += 1) {
  assertMesh(buildMesh(randomDataset(seed)));
}

console.log("\n100 deterministic random point sets: PASS");
console.log("Coplanar lift, cospherical symbolic regularization, duplicate merge: PASS");
console.log("Shadow caps are watertight; template flips are +1 near cap and -1 far cap: PASS");
