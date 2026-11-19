// Render PPM snapshots for offline visual inspection (no browser needed).
const fs = require('fs');
const path = require('path');
const M = require('../src/math.js');
const G = require('../src/geometry.js');
const R = require('../src/rasterizer.js');
const C = require('../src/compositor.js');

function writePPM(file, rgba, w, h) {
  const lines = [`P3\n${w} ${h}\n255\n`];
  for (let i = 0; i < rgba.length; i += 4) {
    lines.push(`${Math.round(rgba[i]*255)} ${Math.round(rgba[i+1]*255)} ${Math.round(rgba[i+2]*255)} `);
  }
  fs.writeFileSync(file, lines.join(''));
}

const outDir = path.join(__dirname, 'snapshots');
fs.mkdirSync(outDir, { recursive: true });
const configs = [
  ['occluder', 4], ['intersect', 4], ['coplanar', 4],
  ['coplanar-tight', 1], ['occluder-tight', 1],
];
for (const [name, passes] of configs) {
  const id = name.startsWith('coplanar') ? 'coplanar'
    : name.startsWith('occluder') ? 'occluder' : name;
  const scene = G.buildScene(id);
  const cam = new M.OrbitCamera([0, 0, 0], 5.4, 0.25, 0.3);
  const render = R.renderScene(scene, cam, 160, 160);
  const res = C.evaluate(render, {
    maxPasses: passes,
    meshPermutation: scene.meshes.map((_, i) => i),
  });
  writePPM(path.join(outDir, name + '-ref.ppm'), res.ref, 160, 160);
  writePPM(path.join(outDir, name + '-ddp.ppm'), res.ddp, 160, 160);
  writePPM(path.join(outDir, name + '-naive.ppm'), res.naive, 160, 160);
  const mask = new Float32Array(res.w * res.h * 4);
  for (let p = 0; p < res.w * res.h; p++) {
    const j = p * 4;
    if (res.leftoverMask[p]) { mask[j] = 0.95; mask[j+1] = 0.15; mask[j+2] = 0.15; mask[j+3] = 1; }
  }
  writePPM(path.join(outDir, name + '-leftover.ppm'), mask, 160, 160);
  console.log(name, JSON.stringify(res.stats));
}
console.log('snapshots written to', outDir);
