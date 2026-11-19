import { runE2E } from "../scripts/e2e.mjs";

const report = await runE2E({ screenshots: false });
const failures = [];
const check = (condition, message) => {
  if (!condition) failures.push(message);
};

const closed = report.structural.closed;
const open = report.structural.open;
const plank = report.structural.plank;
check(closed.meshClosed && closed.meshBoundaryEdges === 0, "closed sphere must be manifold and closed");
check(!open.meshClosed && open.meshBoundaryEdges > 0, "open surface must expose boundary edges");
check(closed.capped.topology.boundaryEdges === 0, "closed capped volume must be watertight");
check(open.capped.topology.boundaryEdges === 0, "open capped prism volume must be watertight");
check(closed.uncapped.topology.boundaryEdges > 0, "closed volume without caps must leak");
check(open.uncapped.topology.boundaryEdges > 0, "open prism without caps must leak");
check(open.capped.capTriangles === open.meshTriangles * 2, "open mesh needs two cap triangles per source triangle");
check(plank.capped.topology.boundaryEdges === 0, "thin plank volume must be watertight");

const s = report.scenarios;
check(s.closedOutsideZfail.mismatchVsShadowMap < 0.01, "closed outside shadow mask mismatch too high");
check(s.closedOutsideZfail.stencilNonzero > 0, "closed outside must produce stencil pixels");
check(s.closedInsideZfail.cameraInside, "closed inside camera must be classified inside");
check(s.closedInsideZfail.mismatchVsShadowMap < 0.02, "closed inside z-fail mask mismatch too high");
check(s.closedInsideZfail.stencilNonzero > 0, "closed inside z-fail must keep stencil coverage");
check(s.closedInsideZpass.mismatchVsShadowMap > 0.5, "z-pass inside camera should be visibly incorrect");
check(s.openOutsideCaps.mismatchVsShadowMap < 0.01, "open capped outside mask mismatch too high");
check(s.openInsideCaps.mismatchVsShadowMap < 0.02, "open capped inside mask mismatch too high");
check(
  s.openInsideNoCaps.mismatchVsShadowMap > s.openInsideCaps.mismatchVsShadowMap + 0.01,
  "removing open-mesh caps must expose a larger mask error",
);
check(s.openOutsideCaps.volumeTriangles === 960, "open capped volume triangle count changed");
check(s.openOutsideNoCaps.volumeTriangles === 720, "open uncapped volume triangle count changed");

const enter = report.cameraEnter;
check(!enter.before.cameraInside, "entering camera must start outside the volume");
check(enter.after.cameraInside, "entering camera must end inside the volume");
check(enter.before.stencilNonzero > 0, "entering camera needs stencil coverage before crossing");
check(enter.after.stencilNonzero > 0, "entering camera needs stencil coverage after crossing");
check(enter.after.mismatchVsShadowMap < 0.02, "entered camera shadow mask mismatch too high");

for (const size of [512, 1024, 2048]) {
  const run = report.thinEdge.runs[size];
  check(Boolean(run), `missing thin-edge run for ${size}`);
  if (run) {
    check(run.sharper === "stencil", `stencil should be sharper than ${size} shadow map`);
    check(run.stencilScore < run.shadowMapScore, `stencil RMS must beat ${size} shadow map`);
  }
}
check(report.browserErrors.length === 0, `browser errors: ${report.browserErrors.join(" | ")}`);

console.log(JSON.stringify({
  volumeTriangles: {
    closed: s.closedOutsideZfail.volumeTriangles,
    openCapped: s.openOutsideCaps.volumeTriangles,
    openUncapped: s.openOutsideNoCaps.volumeTriangles,
    plank: plank.capped.volumeTriangles,
  },
  fillRate: {
    closedOutside: s.closedOutsideZfail.fillRate,
    closedInside: s.closedInsideZfail.fillRate,
    openOutside: s.openOutsideCaps.fillRate,
    openInside: s.openInsideCaps.fillRate,
  },
  stencil: {
    closedOutside: s.closedOutsideZfail.stencilHistogram,
    closedInside: s.closedInsideZfail.stencilHistogram,
    closedInsideZpass: s.closedInsideZpass.stencilHistogram,
    openInsideCaps: s.openInsideCaps.stencilHistogram,
    openInsideNoCaps: s.openInsideNoCaps.stencilHistogram,
  },
  mismatchVsShadowMap: Object.fromEntries(
    Object.entries(s).map(([key, value]) => [key, value.mismatchVsShadowMap]),
  ),
  enter: report.cameraEnter,
  thinEdge: report.thinEdge.runs,
}, null, 2));

if (failures.length > 0) {
  console.error(`\n${failures.length} verification failure(s):`);
  for (const failure of failures) console.error(`- ${failure}`);
  process.exitCode = 1;
} else {
  console.log("\nAll stencil shadow volume checks passed.");
}
