// Minimal vector/matrix/camera math. Column-major mat4, WebGL conventions.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.TRMath = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const v3 = {
    add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]],
    sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
    scale: (a, s) => [a[0] * s, a[1] * s, a[2] * s],
    dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
    cross: (a, b) => [
      a[1] * b[2] - a[2] * b[1],
      a[2] * b[0] - a[0] * b[2],
      a[0] * b[1] - a[1] * b[0],
    ],
    length: (a) => Math.hypot(a[0], a[1], a[2]),
    normalize(a) {
      const l = Math.hypot(a[0], a[1], a[2]) || 1;
      return [a[0] / l, a[1] / l, a[2] / l];
    },
  };

  function mat4Identity() {
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  }

  function mat4Multiply(a, b) {
    const out = new Array(16);
    for (let c = 0; c < 4; c++) {
      for (let r = 0; r < 4; r++) {
        out[c * 4 + r] =
          a[0 * 4 + r] * b[c * 4 + 0] +
          a[1 * 4 + r] * b[c * 4 + 1] +
          a[2 * 4 + r] * b[c * 4 + 2] +
          a[3 * 4 + r] * b[c * 4 + 3];
      }
    }
    return out;
  }

  function mat4Perspective(fovY, aspect, near, far) {
    const f = 1 / Math.tan(fovY / 2);
    const nf = 1 / (near - far);
    return [
      f / aspect, 0, 0, 0,
      0, f, 0, 0,
      0, 0, (far + near) * nf, -1,
      0, 0, 2 * far * near * nf, 0,
    ];
  }

  function mat4LookAt(eye, center, up) {
    const z = v3.normalize(v3.sub(eye, center));
    const x = v3.normalize(v3.cross(up, z));
    const y = v3.cross(z, x);
    return [
      x[0], y[0], z[0], 0,
      x[1], y[1], z[1], 0,
      x[2], y[2], z[2], 0,
      -v3.dot(x, eye), -v3.dot(y, eye), -v3.dot(z, eye), 1,
    ];
  }

  function mat4Translate(t) {
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, t[0], t[1], t[2], 1];
  }

  function mat4Scale(s) {
    return [s[0], 0, 0, 0, 0, s[1], 0, 0, 0, 0, s[2], 0, 0, 0, 0, 1];
  }

  function mat4RotateX(a) {
    const c = Math.cos(a), s = Math.sin(a);
    return [1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1];
  }

  function mat4RotateY(a) {
    const c = Math.cos(a), s = Math.sin(a);
    return [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1];
  }

  function mat4RotateZ(a) {
    const c = Math.cos(a), s = Math.sin(a);
    return [c, s, 0, 0, -s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  }

  function transformPoint(m, p) {
    const x = p[0], y = p[1], z = p[2], w = p[3] ?? 1;
    return [
      m[0] * x + m[4] * y + m[8] * z + m[12] * w,
      m[1] * x + m[5] * y + m[9] * z + m[13] * w,
      m[2] * x + m[6] * y + m[10] * z + m[14] * w,
      m[3] * x + m[7] * y + m[11] * z + m[15] * w,
    ];
  }

  // Spherical orbit camera.
  class OrbitCamera {
    constructor(center, radius, yaw, pitch, fovY = Math.PI / 4, near = 0.1, far = 100) {
      this.center = center.slice();
      this.radius = radius;
      this.yaw = yaw;
      this.pitch = pitch;
      this.fovY = fovY;
      this.near = near;
      this.far = far;
    }
    eye() {
      const cp = Math.cos(this.pitch);
      return [
        this.center[0] + this.radius * cp * Math.sin(this.yaw),
        this.center[1] + this.radius * Math.sin(this.pitch),
        this.center[2] + this.radius * cp * Math.cos(this.yaw),
      ];
    }
    view() {
      return mat4LookAt(this.eye(), this.center, [0, 1, 0]);
    }
    projection(aspect) {
      return mat4Perspective(this.fovY, aspect, this.near, this.far);
    }
  }

  return { v3, mat4Identity, mat4Multiply, mat4Perspective, mat4LookAt,
    mat4Translate, mat4Scale, mat4RotateX, mat4RotateY, mat4RotateZ,
    transformPoint, OrbitCamera };
});
