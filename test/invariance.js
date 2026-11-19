// Cross-view / cross-order invariants for the comparator itself.
const assert = require('assert');
const M = require('../src/math.js');
const G = require('../src/geometry.js');
const R = require('../src/rasterizer.js');
const C = require('../src/compositor.js');

function fullBudgetPerm(scene) {
  return scene.meshes.map((_, i) => i);
}

function permute(scene, mode, seedValue) {
  const transparent = scene.meshes
    .map((m, i) => ({ m, i }))
    .filter((e) => e.m.transparent).map((e) => e.i);
  if (mode === 'reverse') transparent.reverse();
  if (mode === 'shuffle') {
    let seed = seedValue;
    const rnd = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 4294967296;
    };
    for (let i = transparent.length - 1; i > 0; i--) {
      const j = Math.floor(rnd() * (i + 1));
      [transparent[i], transparent[j]] = [transparent[j], transparent[i]];
    }
  }
  return scene.meshes.map((m, i) => (m.transparent ? transparent.indexOf(i) : i));
}

// 1. DDP with a sufficient budget is identical for all submission orders,
//    while naive blending changes when the order changes.
for (const id of ['occluder', 'intersect', 'coplanar']) {
  const scene = G.buildScene(id);
  const cam = new M.OrbitCamera([0, 0, 0], 5.4, 0.7, 0.32);
  const render = R.renderScene(scene, cam, 140, 140);
  const budget = 16;
  const orders = {
    natural: permute(scene, 'natural'),
    reverse: permute(scene, 'reverse'),
    shuffle: permute(scene, 'shuffle', 7),
  };
  const ddpImages = {};
  const naiveImages = {};
  for (const [name, perm] of Object.entries(orders)) {
    const res = C.evaluate(render, { maxPasses: budget, meshPermutation: perm });
    assert.strictEqual(res.stats.budgetSufficient, true, id + ' ' + name + ' sufficient');
    assert.strictEqual(res.stats.failingPixels, 0, id + ' ' + name + ' exact');
    ddpImages[name] = res.ddp;
    naiveImages[name] = res.naive;
  }
  for (const name of ['reverse', 'shuffle']) {
    let ddpDiff = 0, naiveDiff = 0;
    for (let i = 0; i < ddpImages.natural.length; i++) {
      ddpDiff += Math.abs(ddpImages.natural[i] - ddpImages[name][i]);
      naiveDiff += Math.abs(naiveImages.natural[i] - naiveImages[name][i]);
    }
    assert.strictEqual(ddpDiff, 0, id + ' DDP must be order-independent');
    assert(naiveDiff > 0, id + ' naive blend must react to order changes');
  }
  console.log(`[ok] ${id}: DDP order-independent, naive differs across orders`);
}

// 2. Moving the camera keeps exact reference agreement whenever budget covers
//    the deepest pixel; agreement breaks at the same pixels budget predicts.
{
  const scene = G.buildScene('coplanar');
  const views = [
    new M.OrbitCamera([0, 0, 0], 5.4, 0.2, 0.1),
    new M.OrbitCamera([0, 0, 0], 4.0, 1.4, -0.6),
    new M.OrbitCamera([0.2, -0.3, 0.1], 6.5, -1.0, 0.9),
  ];
  for (const cam of views) {
    const render = R.renderScene(scene, cam, 120, 120);
    const perm = fullBudgetPerm(scene);
    const full = C.evaluate(render, { maxPasses: 16, meshPermutation: perm });
    assert.strictEqual(full.stats.failingPixels, 0, 'full budget exact from any view');

    const tightBudget = Math.max(1, full.stats.maxRequired - 1);
    const tight = C.evaluate(render, { maxPasses: tightBudget, meshPermutation: perm });
    if (full.stats.maxRequired > 1) {
      assert(tight.stats.leftoverPixels > 0, 'tight budget must leave fragments');
      assert(tight.stats.failingPixels > 0, 'tight budget must show color loss');
    }
    // Every leftover pixel is flagged in firstFailMap; none others are.
    const n = render.w * render.h;
    for (let p = 0; p < n; p++) {
      const hasLeftover = tight.leftoverMask[p] > 0;
      const flagged = tight.firstFailMap[p] > 0;
      assert.strictEqual(hasLeftover, flagged, 'loss mask consistency at pixel ' + p);
      if (hasLeftover) {
        const j = p * 4;
        assert(C.rgbError(
          [full.ref[j], full.ref[j+1], full.ref[j+2]],
          [tight.ddp[j], tight.ddp[j+1], tight.ddp[j+2]]) > 1/255,
          'flagged pixel must actually distort');
      }
    }
  }
  console.log('[ok] camera orbit: exact under full budget, loss flagged under tight budget');
}

// 3. Required-passes map correctly predicts the minimum exact budget.
{
  const scene = G.buildScene('coplanar');
  const cam = new M.OrbitCamera([0, 0, 0], 5.4, 0.7, 0.32);
  const render = R.renderScene(scene, cam, 110, 110);
  const perm = fullBudgetPerm(scene);
  const probe = C.evaluate(render, { maxPasses: 32, meshPermutation: perm });
  const needed = probe.stats.maxRequired;
  const exact = C.evaluate(render, { maxPasses: needed, meshPermutation: perm });
  const oneLess = C.evaluate(render, { maxPasses: needed - 1, meshPermutation: perm });
  assert.strictEqual(exact.stats.failingPixels, 0, 'predicted budget is exact');
  assert(oneLess.stats.failingPixels > 0, 'one pass less must fail');
  console.log(`[ok] minimum exact budget predicted correctly: ${needed} passes`);
}

console.log('all invariance tests passed');
