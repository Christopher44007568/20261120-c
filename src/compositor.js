// Premultiplied-alpha compositing: per-fragment sorted reference, dual depth
// peeling simulation, and naive shuffled single-pass blending.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.TRCompositor = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // straight RGBA -> premultiplied RGB + coverage
  function premul(c) {
    return [c[0] * c[3], c[1] * c[3], c[2] * c[3], c[3]];
  }

  // Front-to-back "over": src over dst (both premultiplied).
  function over(dst, src) {
    const oneMinusA = 1 - src[3];
    return [
      src[0] + dst[0] * oneMinusA,
      src[1] + dst[1] * oneMinusA,
      src[2] + dst[2] * oneMinusA,
      src[3] + dst[3] * oneMinusA,
    ];
  }

  // Back-to-front "under": dst under src, i.e. src accumulated onto dst.
  // Used by the back peeling target: farther layers land first.
  function under(dst, src) {
    const oneMinusA = 1 - dst[3];
    return [
      dst[0] + src[0] * oneMinusA,
      dst[1] + src[1] * oneMinusA,
      dst[2] + src[2] * oneMinusA,
      dst[3] + src[3] * oneMinusA,
    ];
  }

  function clone4(c) { return [c[0], c[1], c[2], c[3]]; }

  // Ground truth: sort every fragment at the pixel front-to-back and over-blend.
  function referencePixel(frags, base) {
    const ordered = frags.slice().sort((a, b) => a.depth - b.depth);
    let acc = clone4(base);
    for (const f of ordered) acc = over(acc, premul(f.color));
    return acc;
  }

  // Naive pipeline: fragments processed in a shuffled mesh-submission order.
  // Mesh order is the same for all pixels; fragments of one mesh keep their
  // rasterization (arbitrary) order, exposing the classic order-dependence bug.
  function naiveOrder(frags, meshPermutation) {
    const rank = new Map();
    meshPermutation.forEach((meshIndex, rankValue) => rank.set(meshIndex, rankValue));
    return frags.slice().sort((a, b) => {
      const ra = rank.has(a.meshIndex) ? rank.get(a.meshIndex) : a.meshIndex;
      const rb = rank.has(b.meshIndex) ? rank.get(b.meshIndex) : b.meshIndex;
      return ra - rb;
    });
  }

  function naivePixel(frags, base, meshPermutation) {
    let acc = clone4(base);
    for (const f of naiveOrder(frags, meshPermutation)) {
      acc = over(acc, premul(f.color));
    }
    return acc;
  }

  // Dual depth peeling. Each pass peels the nearest and farthest remaining
  // layers; the front target uses over-blending, the back target under-blending.
  // When maxPasses is exhausted, any leftover fragments are simply dropped.
  function dualDepthPeelPixel(frags, base, maxPasses) {
    const remaining = frags.slice().sort((a, b) => a.depth - b.depth);
    let front = [0, 0, 0, 0];
    let back = [0, 0, 0, 0];
    let passes = 0;
    while (remaining.length > 0 && passes < maxPasses) {
      const nearest = remaining.shift();
      front = over(front, premul(nearest.color));
      if (remaining.length > 0) {
        const farthest = remaining.pop();
        back = under(back, premul(farthest.color));
      }
      passes++;
    }
    const leftover = remaining.length;
    // Full DDP framebuffer: front over opaque base under back.
    let acc = over(clone4(base), front);
    acc = over(acc, back);
    return { color: acc, leftover, passesUsed: passes };
  }

  // Minimum peeling passes this pixel needs for an exact result.
  function requiredPasses(fragCount) {
    return Math.ceil(fragCount / 2);
  }

  function rgbError(a, b) {
    return Math.sqrt(
      (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2);
  }

  // Compose whole images and the comparison overlays.
  function evaluate(render, options) {
    const { w, h, opaque, fragments } = render;
    const maxPasses = options.maxPasses;
    const permutation = options.meshPermutation;
    const n = w * h;

    const ref = new Float32Array(n * 4);
    const ddp = new Float32Array(n * 4);
    const naive = new Float32Array(n * 4);
    const errorMap = new Float32Array(n);
    const leftoverMask = new Uint8Array(n);
    const requiredMap = new Float32Array(n);
    const firstFailMap = new Float32Array(n);
    const naiveErrorMap = new Float32Array(n);

    let sumError = 0, maxError = 0;
    let failingPixels = 0, leftoverPixels = 0;
    let sumNaiveError = 0, maxNaiveError = 0, naiveFailing = 0;
    let maxFragCount = 0, maxRequired = 0;

    for (let p = 0; p < n; p++) {
      const j = p * 4;
      const base = [opaque[j], opaque[j + 1], opaque[j + 2], opaque[j + 3]];
      const frags = fragments[p];
      maxFragCount = Math.max(maxFragCount, frags.length);
      const need = requiredPasses(frags.length);
      requiredMap[p] = need;
      maxRequired = Math.max(maxRequired, need);

      const r = referencePixel(frags, base);
      ref.set(r, j);

      const peeled = dualDepthPeelPixel(frags, base, maxPasses);
      ddp.set(peeled.color, j);
      if (peeled.leftover > 0) {
        leftoverMask[p] = peeled.leftover;
        leftoverPixels++;
      }

      const err = rgbError(r, peeled.color);
      errorMap[p] = err;
      sumError += err;
      if (err > maxError) maxError = err;
      if (err > 1 / 255) failingPixels++;

      // First budget that fails this pixel: sweep every peeling budget up to
      // the pixel's exact requirement. 0 means the current budget is exact.
      if (need > maxPasses) {
        let firstFail = 0;
        for (let b = 1; b < need; b++) {
          const probe = dualDepthPeelPixel(frags, base, b);
          if (rgbError(r, probe.color) > 1 / 255) { firstFail = b; break; }
        }
        firstFailMap[p] = firstFail || need;
      }

      const nv = naivePixel(frags, base, permutation);
      naive.set(nv, j);
      const ne = rgbError(r, nv);
      naiveErrorMap[p] = ne;
      sumNaiveError += ne;
      if (ne > maxNaiveError) maxNaiveError = ne;
      if (ne > 1 / 255) naiveFailing++;
    }

    return {
      w, h, ref, ddp, naive,
      errorMap, leftoverMask, requiredMap, firstFailMap, naiveErrorMap,
      stats: {
        meanError: sumError / n,
        maxError,
        failingPixels,
        leftoverPixels,
        maxFragCount,
        maxRequired,
        budgetSufficient: leftoverPixels === 0,
        naive: {
          meanError: sumNaiveError / n,
          maxError: maxNaiveError,
          failingPixels: naiveFailing,
        },
      },
    };
  }

  return {
    premul, over, under, referencePixel, naivePixel,
    dualDepthPeelPixel, requiredPasses, rgbError, evaluate,
  };
});
