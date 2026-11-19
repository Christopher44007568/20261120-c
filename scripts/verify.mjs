import { mkdir, writeFile } from "node:fs/promises";
import { analyzePose, precomputeProofs } from "../src/analysis.js";
import { HemisphereTracker } from "../src/math.js";
import { MODELS } from "../src/models.js";
import { buildSkinningPalette } from "../src/skinning.js";

const ANGLES = [0, 45, 90, 120, 150, 180];

function summarizeModel(model) {
  const proofs = precomputeProofs(model, 181);
  const samples = {};
  for (const degrees of ANGLES) {
    const radians = (degrees / 180) * Math.PI;
    const palette = buildSkinningPalette(model.rig, radians, {
      sign: 1,
      tracker: new HemisphereTracker(),
    });
    const analysis = analyzePose(model, palette, palette);
    samples[`${degrees}deg`] = {
      maxError: analysis.maxError,
      meanError: analysis.meanError,
      blendMaxError: analysis.blendErrorMax,
      pureRegionMaxError: analysis.pureErrorMax,
      midAreaRatio: {
        lbs: analysis.mid.lbsAreaRatio,
        dqs: analysis.mid.dqsAreaRatio,
      },
      minAreaRatio: {
        lbs: Math.min(...analysis.lbsAreaRatio),
        dqs: Math.min(...analysis.dqsAreaRatio),
      },
      intervals: analysis.intervals,
    };
  }
  return {
    kind: model.kind,
    bones: model.rig.bindMatrices.length,
    vertices: model.vertexCount,
    surfaceVertices: model.surfaceVertexCount,
    blendVertices: model.blendVertexCount,
    orphanVertices: proofs.orphan.count,
    sharedWeightInterval: [model.blendStart, model.blendEnd],
    bindPose: {
      lbsMaxDeviation: proofs.bindLbs,
      dqsMaxDeviation: proofs.bindDqs,
      crossPathMaxSeparation: proofs.bindSeparation,
    },
    quaternionSign: {
      testedAngleCount: proofs.angles.length,
      maxVertexJump: proofs.signJumpMax,
      worstAngle: proofs.angles[proofs.signJumps.indexOf(proofs.signJumpMax)] * 180 / Math.PI,
    },
    isolatedVertices: {
      count: proofs.orphan.count,
      maxBindDeviation: proofs.orphan.maxDeviation,
    },
    samples,
  };
}

const report = {
  generatedAt: new Date().toISOString(),
  implementation: {
    skinning: "GPU dual quaternion skinning with matrix LBS comparison",
    weights: "up to 4 influences per vertex",
    zeroWeightPolicy: "return bind-space position",
    signPolicy: "deterministic first-frame hemisphere plus per-bone temporal alignment",
  },
  scenes: {
    twist: summarizeModel(MODELS.twist),
    elbow: summarizeModel(MODELS.elbow),
  },
};

await mkdir("artifacts", { recursive: true });
await writeFile("artifacts/verification.json", `${JSON.stringify(report, null, 2)}\n`);

const lines = [];
for (const [name, scene] of Object.entries(report.scenes)) {
  lines.push(`${name}: bind=${scene.bindPose.crossPathMaxSeparation.toExponential(2)} signJump=${scene.quaternionSign.maxVertexJump.toExponential(2)} orphans=${scene.isolatedVertices.maxBindDeviation.toExponential(2)}`);
  for (const angle of ["90deg", "120deg", "180deg"]) {
    const sample = scene.samples[angle];
    lines.push(`  ${angle.padEnd(6)} area LBS=${(sample.midAreaRatio.lbs * 100).toFixed(2)}% DQS=${(sample.midAreaRatio.dqs * 100).toFixed(2)}% error=${sample.maxError.toFixed(4)}`);
  }
}
console.log(lines.join("\n"));
console.log("wrote artifacts/verification.json");
