// Image blitting and diagnostic colormap rendering onto 2D canvases.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.TRViz = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  function blit(canvas, rgba) {
    const w = canvas.width;
    const h = canvas.height;
    const ctx = canvas.getContext('2d');
    const img = ctx.createImageData(w, h);
    for (let i = 0, k = 0; i < rgba.length; i += 4, k++) {
      img.data[i] = clamp255(rgba[i] * 255);
      img.data[i + 1] = clamp255(rgba[i + 1] * 255);
      img.data[i + 2] = clamp255(rgba[i + 2] * 255);
      img.data[i + 3] = clamp255(rgba[i + 3] * 255);
    }
    const small = document.createElement('canvas');
    small.width = w; small.height = h;
    small.getContext('2d').putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(small, 0, 0, canvas.width, canvas.height);
  }

  function clamp255(v) {
    return v < 0 ? 0 : v > 255 ? 255 : v;
  }

  // Blue -> cyan -> green -> yellow -> red heat ramp for scalar error fields.
  function heat(t) {
    t = Math.max(0, Math.min(1, t));
    const stops = [
      [0.0, [0.05, 0.05, 0.35]],
      [0.25, [0.1, 0.6, 0.9]],
      [0.5, [0.2, 0.85, 0.35]],
      [0.75, [1.0, 0.85, 0.15]],
      [1.0, [0.95, 0.1, 0.1]],
    ];
    for (let i = 1; i < stops.length; i++) {
      if (t <= stops[i][0]) {
        const a = stops[i - 1], b = stops[i];
        const u = (t - a[0]) / (b[0] - a[0]);
        return [
          a[1][0] + (b[1][0] - a[1][0]) * u,
          a[1][1] + (b[1][1] - a[1][1]) * u,
          a[1][2] + (b[1][2] - a[1][2]) * u,
        ];
      }
    }
    return stops[stops.length - 1][1].slice();
  }

  function blitHeat(canvas, values, maxValue, mask, maskColor) {
    const w = canvas.width, h = canvas.height;
    const ctx = canvas.getContext('2d');
    const img = ctx.createImageData(w, h);
    for (let p = 0, k = 0; p < values.length; p++, k += 4) {
      if (mask && !mask[p]) {
        img.data[k + 3] = 0;
        continue;
      }
      const rgb = heat(values[p] / (maxValue || 1));
      if (maskColor) {
        img.data[k] = maskColor[0] * 255;
        img.data[k + 1] = maskColor[1] * 255;
        img.data[k + 2] = maskColor[2] * 255;
        img.data[k + 3] = 235;
      } else {
        img.data[k] = rgb[0] * 255;
        img.data[k + 1] = rgb[1] * 255;
        img.data[k + 2] = rgb[2] * 255;
        img.data[k + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  // Required-budget map. Pixels that fail under the current budget are painted
  // red, brighter when the first distortion happens at an earlier round.
  function blitBudget(canvas, requiredMap, firstFailMap, maxPasses) {
    const w = canvas.width, h = canvas.height;
    const ctx = canvas.getContext('2d');
    const img = ctx.createImageData(w, h);
    let maxNeed = maxPasses;
    for (let i = 0; i < requiredMap.length; i++) {
      if (requiredMap[i] > maxNeed) maxNeed = requiredMap[i];
    }
    maxNeed = Math.max(1, maxNeed);
    for (let p = 0, k = 0; p < requiredMap.length; p++, k += 4) {
      const need = requiredMap[p];
      if (need === 0) { img.data[k + 3] = 0; continue; }
      let rgb;
      if (firstFailMap[p] > 0) {
        const severity = 0.45 + 0.55 * (1 - firstFailMap[p] / maxNeed);
        rgb = [0.95, 0.18 * severity, 0.18 * severity];
      } else {
        rgb = heat(need / maxNeed);
      }
      img.data[k] = rgb[0] * 255;
      img.data[k + 1] = rgb[1] * 255;
      img.data[k + 2] = rgb[2] * 255;
      img.data[k + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
  }

  return { blit, blitHeat, blitBudget, heat };
});
