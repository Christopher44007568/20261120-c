// Procedural mesh builders and the three scene templates.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('./math.js'));
  } else root.TRGeometry = factory(root.TRMath);
})(typeof self !== 'undefined' ? self : this, function (M) {
  'use strict';

  // Mesh: { name, transparent, color:[r,g,b,a] (straight alpha), vertices, indices,
  //         model: mat4, flat: true }
  function makeBox(name, color, transparent, model) {
    const h = 0.5;
    const v = [
      [-h, -h, -h], [h, -h, -h], [h, h, -h], [-h, h, -h],
      [-h, -h, h], [h, -h, h], [h, h, h], [-h, h, h],
    ];
    const idx = [
      0, 2, 1, 0, 3, 2, // back (-z)
      4, 5, 6, 4, 6, 7, // front (+z)
      0, 1, 5, 0, 5, 4, // bottom
      3, 7, 6, 3, 6, 2, // top
      0, 4, 7, 0, 7, 3, // left
      1, 2, 6, 1, 6, 5, // right
    ];
    return { name, color, transparent, vertices: v, indices: idx, model, flat: true };
  }

  // A zero-thickness double-sided quad in the XY plane, unit size.
  function makeQuad(name, color, model) {
    const h = 0.5;
    const vertices = [[-h, -h, 0], [h, -h, 0], [h, h, 0], [-h, h, 0]];
    const indices = [0, 1, 2, 0, 2, 3];
    return { name, color, transparent: true, vertices, indices, model, flat: true };
  }

  function model(pos, rot, scl) {
    let m = M.mat4Translate(pos);
    if (rot) {
      m = M.mat4Multiply(m, M.mat4RotateZ(rot[2]));
      m = M.mat4Multiply(m, M.mat4RotateY(rot[1]));
      m = M.mat4Multiply(m, M.mat4RotateX(rot[0]));
    }
    if (scl) m = M.mat4Multiply(m, M.mat4Scale(scl));
    return m;
  }

  // Glass shell: a box (six faces) that reads as a hollow cube envelope.
  function glassShell(name, color, pos, scl, rot) {
    return makeBox(name, color, true, model(pos, rot, scl));
  }

  function thinSheet(name, color, pos, scl, rot) {
    return makeQuad(name, color, model(pos, rot, scl));
  }

  function occluder(name, color, pos, scl, rot) {
    return makeBox(name, color, false, model(pos, rot, scl));
  }

  function buildScene(id) {
    const meshes = [];
    if (id === 'occluder') {
      // Opaque cube in the middle of an interleaved stack of shells and sheets.
      meshes.push(occluder('opaque-core', [0.78, 0.55, 0.28, 1],
        [0, 0, 0], [0.9, 0.9, 0.9]));
      meshes.push(glassShell('glass-A', [0.25, 0.55, 0.95, 0.32],
        [0, 0, 0], [3.2, 2.2, 2.2], [0, 0.35, 0]));
      meshes.push(thinSheet('sheet-B', [0.95, 0.35, 0.45, 0.38],
        [0, 0, 0], [3.6, 2.4, 1], [0.15, -0.5, 0.1]));
      meshes.push(glassShell('glass-C', [0.35, 0.85, 0.55, 0.26],
        [0.3, -0.2, 0.4], [1.7, 1.7, 1.7], [0.5, 0.2, 0.4]));
      meshes.push(thinSheet('sheet-D', [0.75, 0.45, 0.95, 0.3],
        [-0.4, 0.3, -0.3], [2.6, 1.8, 1], [-0.2, 0.7, -0.25]));
    } else if (id === 'intersect') {
      // Three large transparent primitives cutting through each other, plus a shell.
      meshes.push(thinSheet('sheet-X', [0.95, 0.3, 0.35, 0.34],
        [0, 0, 0], [3.8, 3.8, 1], [0.6, 0.2, 0.15]));
      meshes.push(thinSheet('sheet-Y', [0.3, 0.55, 0.95, 0.34],
        [0, 0, 0], [3.8, 3.8, 1], [-0.5, 0.9, -0.4]));
      meshes.push(thinSheet('sheet-Z', [0.35, 0.85, 0.45, 0.3],
        [0, 0, 0], [3.4, 3.4, 1], [0.1, -0.35, 0.8]));
      meshes.push(glassShell('glass-shell', [0.85, 0.7, 0.25, 0.24],
        [0.2, 0.1, -0.2], [2.0, 2.0, 2.0], [0.4, 0.6, 0.2]));
      meshes.push(occluder('opaque-wedge', [0.6, 0.6, 0.65, 1],
        [1.4, -1.2, 0.8], [0.8, 0.8, 1.6], [0.3, 0.4, 0.2]));
    } else {
      // Near-coplanar: sheets stacked with tiny depth gaps plus a grazing shell.
      const n = 7;
      const palette = [
        [0.95, 0.35, 0.4, 0.3], [0.35, 0.55, 0.95, 0.3],
        [0.4, 0.85, 0.5, 0.3], [0.9, 0.75, 0.3, 0.3],
      ];
      for (let i = 0; i < n; i++) {
        const t = i - (n - 1) / 2;
        meshes.push(thinSheet('coplanar-' + i, palette[i % palette.length],
          [t * 0.015, t * 0.01, t * 0.09],
          [3.0, 2.2, 1],
          [0.05, 0.12 + t * 0.004, t * 0.012]));
      }
      meshes.push(glassShell('grazing-shell', [0.5, 0.7, 0.95, 0.22],
        [0, 0, 0.6], [2.6, 1.8, 1.4], [0.9, 0.15, 0.1]));
    }
    return { id, meshes };
  }

  return { makeBox, makeQuad, model, glassShell, thinSheet, occluder, buildScene };
});
