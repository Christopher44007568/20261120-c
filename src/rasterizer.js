// Tiny software rasterizer. Produces, per pixel, an ordered list of
// transparent fragments and the nearest opaque surface.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('./math.js'));
  } else root.TRRaster = factory(root.TRMath);
})(typeof self !== 'undefined' ? self : this, function (M) {
  'use strict';

  const LIGHT = M.v3.normalize([0.45, 0.75, 0.8]);

  // Clip a camera-space polygon against near (z <= -near) and far (z >= -far).
  function clipNearFar(poly, near, far) {
    const planes = [
      { inside: (p) => p[2] <= -near, coord: (p) => -near - p[2] },
      { inside: (p) => p[2] >= -far, coord: (p) => p[2] + far },
    ];
    let out = poly;
    for (const plane of planes) {
      const input = out;
      out = [];
      for (let i = 0; i < input.length; i++) {
        const cur = input[i];
        const prv = input[(i + input.length - 1) % input.length];
        const cin = plane.inside(cur), pin = plane.inside(prv);
        if (cin) {
          if (!pin) {
            const t = plane.coord(prv) / (plane.coord(prv) - plane.coord(cur));
            out.push([
              prv[0] + (cur[0] - prv[0]) * t,
              prv[1] + (cur[1] - prv[1]) * t,
              prv[2] + (cur[2] - prv[2]) * t,
            ]);
          }
          out.push(cur);
        } else if (pin) {
          const t = plane.coord(prv) / (plane.coord(prv) - plane.coord(cur));
          out.push([
            prv[0] + (cur[0] - prv[0]) * t,
            prv[1] + (cur[1] - prv[1]) * t,
            prv[2] + (cur[2] - prv[2]) * t,
          ]);
        }
      }
      if (out.length === 0) return out;
    }
    return out;
  }

  function checkerboard(w, h) {
    const buf = new Float32Array(w * h * 4);
    const tile = Math.max(4, Math.round(w / 24));
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const dark = ((Math.floor(x / tile) + Math.floor(y / tile)) & 1) === 0;
        const c = dark ? 0.78 : 0.92;
        const i = (y * w + x) * 4;
        buf[i] = c; buf[i + 1] = c; buf[i + 2] = c; buf[i + 3] = 1;
      }
    }
    return buf;
  }

  function shade(mesh, camVerts) {
    const e1 = M.v3.sub(camVerts[1], camVerts[0]);
    const e2 = M.v3.sub(camVerts[2], camVerts[0]);
    const n = M.v3.normalize(M.v3.cross(e1, e2));
    const diffuse = 0.55 + 0.45 * Math.abs(M.v3.dot(n, LIGHT));
    return [
      mesh.color[0] * diffuse,
      mesh.color[1] * diffuse,
      mesh.color[2] * diffuse,
      mesh.color[3],
    ];
  }

  function renderScene(scene, camera, w, h) {
    const bg = checkerboard(w, h);
    const opaque = new Float32Array(bg); // bg with opaque surfaces blended on top
    const opaqueDepth = new Float32Array(w * h).fill(Infinity);
    const fragments = Array.from({ length: w * h }, () => []);

    const view = camera.view();
    const proj = camera.projection(w / h);
    const vp = M.mat4Multiply(proj, view);

    for (let mi = 0; mi < scene.meshes.length; mi++) {
      const mesh = scene.meshes[mi];
      const mv = M.mat4Multiply(view, mesh.model);
      const mvp = M.mat4Multiply(proj, mv);
      const camVerts = mesh.vertices.map((p) => M.transformPoint(mv, p));
      const clipVerts = mesh.vertices.map((p) => M.transformPoint(mvp, p));

      for (let t = 0; t < mesh.indices.length; t += 3) {
        const ids = [mesh.indices[t], mesh.indices[t + 1], mesh.indices[t + 2]];
        const camTri = ids.map((id) => camVerts[id]);
        const clipped = clipNearFar(camTri, camera.near, camera.far);
        if (clipped.length < 3) continue;
        const color = shade(mesh, camTri);

        // Re-project clipped camera points through view-projection.
        const ndc = clipped.map((p) => {
          const q = M.transformPoint(vp, p);
          const iw = 1 / q[3];
          return [q[0] * iw, q[1] * iw, q[2] * iw, q[3]];
        });
        const screen = ndc.map((q) => [
          (q[0] * 0.5 + 0.5) * w,
          (1 - (q[1] * 0.5 + 0.5)) * h,
        ]);
        const camDepth = clipped.map((p) => -p[2]);
        const invW = ndc.map((q) => 1 / q[3]);

        for (let fi = 1; fi < clipped.length - 1; fi++) {
          rasterTriangle([0, fi, fi + 1], screen, ndc, camDepth, invW,
            color, mesh, mi, w, h, opaque, opaqueDepth, fragments);
        }
      }
    }
    return { w, h, bg, opaque, opaqueDepth, fragments, meshCount: scene.meshes.length };
  }

  function rasterTriangle(ids, screen, ndc, camDepth, invW, color, mesh, meshIndex,
      w, h, opaque, opaqueDepth, fragments) {
    const a = screen[ids[0]], b = screen[ids[1]], c = screen[ids[2]];
    const area = edge(a, b, c);
    if (area === 0) return;
    const minX = Math.max(0, Math.floor(Math.min(a[0], b[0], c[0])));
    const maxX = Math.min(w - 1, Math.ceil(Math.max(a[0], b[0], c[0])));
    const minY = Math.max(0, Math.floor(Math.min(a[1], b[1], c[1])));
    const maxY = Math.min(h - 1, Math.ceil(Math.max(a[1], b[1], c[1])));
    const biasA = topLeft(a, b);
    const biasB = topLeft(b, c);
    const biasC = topLeft(c, a);

    for (let y = minY; y <= maxY; y++) {
      for (let x = minX; x <= maxX; x++) {
        const p = [x + 0.5, y + 0.5];
        const w0 = edge(b, c, p) + (biasB ? 0 : -1);
        const w1 = edge(c, a, p) + (biasC ? 0 : -1);
        const w2 = edge(a, b, p) + (biasA ? 0 : -1);
        if (w0 < 0 || w1 < 0 || w2 < 0) continue;
        const ba = w0 / area, bb = w1 / area, bc = w2 / area;
        const persp = ba * invW[ids[0]] + bb * invW[ids[1]] + bc * invW[ids[2]];
        const depth = (
          ba * camDepth[ids[0]] * invW[ids[0]] +
          bb * camDepth[ids[1]] * invW[ids[1]] +
          bc * camDepth[ids[2]] * invW[ids[2]]
        ) / persp;
        const zNdc = ba * ndc[ids[0]][2] + bb * ndc[ids[1]][2] + bc * ndc[ids[2]][2];
        const pi = y * w + x;

        if (mesh.transparent) {
          if (depth >= opaqueDepth[pi]) continue; // occluded by opaque surface
          fragments[pi].push({
            depth, zNdc, color: color.slice(), meshIndex,
          });
        } else {
          if (depth < opaqueDepth[pi]) {
            opaqueDepth[pi] = depth;
            const j = pi * 4;
            opaque[j] = color[0]; opaque[j + 1] = color[1];
            opaque[j + 2] = color[2]; opaque[j + 3] = 1;
          }
        }
      }
    }
  }

  function edge(a, b, p) {
    return (p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0]);
  }
  function topLeft(a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1];
    return dy < 0 || (dy === 0 && dx > 0);
  }

  return { renderScene, clipNearFar };
});
