import assert from "node:assert/strict";
import test from "node:test";
import {
  HemisphereTracker,
  mat4FromQuaternionTranslation,
  mat4Identity,
  quatFromAxisAngle,
  quatNegate,
  transformPoint,
} from "../src/math.js";
import { MODELS } from "../src/models.js";
import {
  buildSkinningPalette,
  dualQuaternionFromRigid,
  polygonArea3D,
  skinAllVertices,
  skinVertexDQS,
  skinVertexLBS,
  transformedRing,
  transformPointDualQuaternion,
  vertexDifferenceAt,
} from "../src/skinning.js";
import { maxSeparation } from "../src/analysis.js";

const ANGLES = [0, Math.PI / 6, Math.PI / 2, (Math.PI * 3) / 4, Math.PI];

test("dual quaternion transform matches the rigid matrix", () => {
  const quaternion = quatFromAxisAngle([1, 2, 3], 1.234);
  const translation = [0.4, -1.2, 2.1];
  const point = [0.2, 0.8, -0.6];
  const dq = dualQuaternionFromRigid(quaternion, translation);
  const transformed = transformPointDualQuaternion(dq, point);
  const expected = transformPoint(mat4FromQuaternionTranslation(quaternion, translation), point);
  assert.ok(transformed.every((value, index) => Math.abs(value - expected[index]) < 1e-6));
});

for (const [name, model] of Object.entries(MODELS)) {
  test(`${name}: both paths reproduce the bind pose`, () => {
    for (const sign of [-1, 1]) {
      const palette = buildSkinningPalette(model.rig, 0, { sign, tracker: new HemisphereTracker() });
      const lbs = skinAllVertices(model, palette, "lbs");
      const dqs = skinAllVertices(model, palette, "dqs");
      for (let vertex = 0; vertex < model.vertexCount; vertex += 1) {
        assert.ok(vertexDifferenceAt(lbs, model.positions, vertex) < 1e-6);
        assert.ok(vertexDifferenceAt(dqs, model.positions, vertex) < 1e-6);
      }
    }
  });

  test(`${name}: +q and -q produce identical DQS output`, () => {
    for (const angle of ANGLES) {
      const plus = buildSkinningPalette(model.rig, angle, { sign: 1, tracker: new HemisphereTracker() });
      const minus = buildSkinningPalette(model.rig, angle, { sign: -1, tracker: new HemisphereTracker() });
      assert.ok(maxSeparation(skinAllVertices(model, plus, "dqs"), skinAllVertices(model, minus, "dqs")) < 1e-6);
    }
  });

  test(`${name}: isolated zero-weight vertices stay at bind position`, () => {
    for (const angle of ANGLES) {
      for (const sign of [-1, 1]) {
        const palette = buildSkinningPalette(model.rig, angle, { sign, tracker: new HemisphereTracker() });
        for (let vertex = model.orphanStart; vertex < model.vertexCount; vertex += 1) {
          const offset = vertex * 4;
          const point = [model.positions[vertex * 3], model.positions[vertex * 3 + 1], model.positions[vertex * 3 + 2]];
          assert.deepEqual(skinVertexLBS(point, model.skinIndex, model.skinWeight, offset, palette), point);
          assert.deepEqual(skinVertexDQS(point, model.skinIndex, model.skinWeight, offset, palette), point);
        }
      }
    }
  });

  test(`${name}: DQS preserves the probe cross section at 180 degrees`, () => {
    const palette = buildSkinningPalette(model.rig, Math.PI, { sign: 1, tracker: new HemisphereTracker() });
    const dqs = skinAllVertices(model, palette, "dqs");
    const center = [0, 0, model.jointZ];
    let minRadius = Infinity;
    for (let radial = 0; radial < model.radialSegments; radial += 1) {
      const vertex = model.midRing * model.radialSegments + radial;
      const offset = vertex * 3;
      minRadius = Math.min(minRadius, Math.hypot(
        dqs[offset] - center[0],
        dqs[offset + 1] - center[1],
        dqs[offset + 2] - center[2],
      ));
    }
    assert.ok(minRadius > model.radius * 0.98, `min radius ${minRadius}`);
  });

  test(`${name}: LBS collapses the probe cross section at 180 degrees`, () => {
    const palette = buildSkinningPalette(model.rig, Math.PI, { sign: 1, tracker: new HemisphereTracker() });
    const lbs = skinAllVertices(model, palette, "lbs");
    const areaRatio = polygonArea3D(transformedRing(model, lbs, model.midRing)) / model.bindArea;
    assert.ok(areaRatio < 1e-5, `area ratio ${areaRatio}`);
  });
}

test("quaternion sign tracker keeps an arbitrary input sign stable across frames", () => {
  const tracker = new HemisphereTracker();
  const base = quatFromAxisAngle([0, 0, 1], 2.2);
  const first = tracker.track("joint", base);
  const second = tracker.track("joint", quatNegate(base));
  assert.ok(Math.abs(first[3] - second[3]) < 1e-12);
  assert.ok(first.every((value, index) => Math.abs(value - second[index]) < 1e-12));
});

test("mat4 identity is exported for tests", () => {
  assert.deepEqual([...mat4Identity()], [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
});
