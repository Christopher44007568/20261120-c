import assert from "node:assert/strict";
import test from "node:test";
import { precomputeProofs } from "../src/analysis.js";
import { MODELS } from "../src/models.js";

for (const [name, model] of Object.entries(MODELS)) {
  test(`${name}: sampled runtime proofs are exact`, () => {
    const proofs = precomputeProofs(model, 37);
    assert.ok(proofs.bindLbs < 1e-6);
    assert.ok(proofs.bindDqs < 1e-6);
    assert.ok(proofs.bindSeparation < 1e-6);
    assert.ok(proofs.signJumpMax < 1e-6);
    assert.equal(proofs.orphan.count, 3);
    assert.ok(proofs.orphan.maxDeviation < 1e-12);
  });
}
