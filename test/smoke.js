const assert = require('assert');
const M = require('../src/math.js');
const G = require('../src/geometry.js');
const R = require('../src/rasterizer.js');
const C = require('../src/compositor.js');

// 1. Premultiplied over/under are consistent inverses on a two-layer case.
{
  const base = [0.8, 0.8, 0.8, 1];
  const s1 = C.premul([0.9, 0.1, 0.1, 0.4]);
  const s2 = C.premul([0.1, 0.2, 0.9, 0.3]);
  const frontToBack = C.over(C.over(base.slice(), s1), s2);
  // back target: farthest (s2) lands first, then s1 goes under it.
  const backToFront = C.under(C.under([0, 0, 0, 0], s2), s1);
  const merged = C.over(base.slice(), backToFront);
  for (let i = 0; i < 3; i++) {
    assert(Math.abs(frontToBack[i] - merged[i]) < 1e-9, 'over/under mismatch at ' + i);
  }
}

// 2. Full-budget dual depth peeling equals the sorted reference on random
//    fragment stacks, regardless of input order.
{
  let seed = 1234567;
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  for (let trial = 0; trial < 200; trial++) {
    const count = 1 + Math.floor(rnd() * 12);
    const frags = [];
    for (let i = 0; i < count; i++) {
      frags.push({
        depth: rnd() * 10,
        color: [rnd(), rnd(), rnd(), 0.1 + rnd() * 0.5],
        meshIndex: Math.floor(rnd() * 4),
      });
    }
    const base = [rnd(), rnd(), rnd(), 1];
    const ref = C.referencePixel(frags, base);
    const ddp = C.dualDepthPeelPixel(frags, base, C.requiredPasses(count));
    assert.strictEqual(ddp.leftover, 0, 'no leftovers with full budget');
    for (let i = 0; i < 3; i++) {
      assert(Math.abs(ref[i] - ddp.color[i]) < 1e-9,
        'DDP != reference trial ' + trial + ' channel ' + i);
    }
  }
}

// 3. Under-budget peeling drops fragments and diverges from reference.
{
  const frags = [];
  for (let i = 0; i < 8; i++) {
    frags.push({ depth: i, color: [0.5, 0.5, 0.5, 0.3], meshIndex: 0 });
  }
  const base = [0.9, 0.9, 0.9, 1];
  const ref = C.referencePixel(frags, base);
  const ddp = C.dualDepthPeelPixel(frags, base, 2);
  assert.strictEqual(ddp.leftover, 4, '4 middle fragments remain after 2 passes');
  assert(C.rgbError(ref, ddp.color) > 1e-6, 'under-budget must differ');
}

// 4. End-to-end: every scene renders and a full budget gives zero pixel error.
for (const id of ['occluder', 'intersect', 'coplanar']) {
  const scene = G.buildScene(id);
  const cam = new M.OrbitCamera([0, 0, 0], 5.2, 0.6, 0.35);
  const w = 96, h = 96;
  const render = R.renderScene(scene, cam, w, h);
  let totalFrags = 0, covered = 0;
  for (const list of render.fragments) {
    if (list.length) covered++;
    totalFrags += list.length;
  }
  assert(covered > 0, id + ' covers pixels');
  const perm = scene.meshes.map((_, i) => i);
  const full = C.evaluate(render, { maxPasses: 32, meshPermutation: perm });
  assert.strictEqual(full.stats.leftoverPixels, 0, id + ' full budget leaves nothing');
  assert.strictEqual(full.stats.failingPixels, 0, id + ' full budget matches reference');
  assert(full.stats.maxFragCount >= 2, id + ' has overlapping transparency');
  const tight = C.evaluate(render, { maxPasses: 1, meshPermutation: perm });
  assert(tight.stats.leftoverPixels >= 0, id + ' tight budget runs');
  console.log(`[ok] ${id}: covered=${covered} frags=${totalFrags} ` +
    `maxDepth=${full.stats.maxFragCount} need<=${full.stats.maxRequired} ` +
    `tightFail=${tight.stats.failingPixels}`);
}

console.log('all smoke tests passed');
