export const DEG = Math.PI / 180;

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function lerp(a, b, t) {
  return a + (b - a) * t;
}

export function smoothstep(edge0, edge1, value) {
  const t = clamp((value - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}

export function modulo(value, modulus) {
  return ((value % modulus) + modulus) % modulus;
}

export function f32(value) {
  return Math.fround(value);
}

const floatBuffer = new ArrayBuffer(4);
const floatView = new Float32Array(floatBuffer);
const uintView = new Uint32Array(floatBuffer);

export function ulp32(value) {
  const abs = Math.abs(value);
  if (abs === 0) return 1.401298464324817e-45;
  floatView[0] = abs;
  uintView[0] += 1;
  return floatView[0] - abs;
}

export function perspective(out, fovyRadians, aspect, near, far) {
  const f = 1 / Math.tan(fovyRadians / 2);
  const nf = 1 / (near - far);
  out.fill(0);
  out[0] = f / aspect;
  out[5] = f;
  out[10] = (far + near) * nf;
  out[11] = -1;
  out[14] = 2 * far * near * nf;
  return out;
}

export function lookAt(out, eye, target, up = [0, 1, 0]) {
  let z0 = eye[0] - target[0];
  let z1 = eye[1] - target[1];
  let z2 = eye[2] - target[2];
  let length = Math.hypot(z0, z1, z2) || 1;
  z0 /= length;
  z1 /= length;
  z2 /= length;

  let x0 = up[1] * z2 - up[2] * z1;
  let x1 = up[2] * z0 - up[0] * z2;
  let x2 = up[0] * z1 - up[1] * z0;
  length = Math.hypot(x0, x1, x2) || 1;
  x0 /= length;
  x1 /= length;
  x2 /= length;

  const y0 = z1 * x2 - z2 * x1;
  const y1 = z2 * x0 - z0 * x2;
  const y2 = z0 * x1 - z1 * x0;

  out[0] = x0;
  out[1] = y0;
  out[2] = z0;
  out[3] = 0;
  out[4] = x1;
  out[5] = y1;
  out[6] = z1;
  out[7] = 0;
  out[8] = x2;
  out[9] = y2;
  out[10] = z2;
  out[11] = 0;
  out[12] = -(x0 * eye[0] + x1 * eye[1] + x2 * eye[2]);
  out[13] = -(y0 * eye[0] + y1 * eye[1] + y2 * eye[2]);
  out[14] = -(z0 * eye[0] + z1 * eye[1] + z2 * eye[2]);
  out[15] = 1;
  return out;
}

export function multiply(out, a, b) {
  for (let column = 0; column < 4; column += 1) {
    const b0 = b[column * 4];
    const b1 = b[column * 4 + 1];
    const b2 = b[column * 4 + 2];
    const b3 = b[column * 4 + 3];
    out[column * 4] = b0 * a[0] + b1 * a[4] + b2 * a[8] + b3 * a[12];
    out[column * 4 + 1] = b0 * a[1] + b1 * a[5] + b2 * a[9] + b3 * a[13];
    out[column * 4 + 2] = b0 * a[2] + b1 * a[6] + b2 * a[10] + b3 * a[14];
    out[column * 4 + 3] = b0 * a[3] + b1 * a[7] + b2 * a[11] + b3 * a[15];
  }
  return out;
}

export function transformPoint(matrix, point, out = [0, 0, 0, 0]) {
  const x = point[0];
  const y = point[1];
  const z = point[2];
  const w = point[3] ?? 1;
  out[0] = matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12] * w;
  out[1] = matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13] * w;
  out[2] = matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14] * w;
  out[3] = matrix[3] * x + matrix[7] * y + matrix[11] * z + matrix[15] * w;
  return out;
}

export function projectToClip(projectionView, point, out = [0, 0, 0, 0]) {
  return transformPoint(projectionView, point, out);
}

export function clipToPixels(clip, width, height) {
  const inverseW = 1 / Math.max(clip[3], 1e-9);
  return [
    (clip[0] * inverseW * 0.5 + 0.5) * width,
    (0.5 - clip[1] * inverseW * 0.5) * height,
  ];
}

export function catmullRom(p0, p1, p2, p3, t) {
  const t2 = t * t;
  const t3 = t2 * t;
  return 0.5 * (
    2 * p1 +
    (-p0 + p2) * t +
    (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
    (-p0 + 3 * p1 - 3 * p2 + p3) * t3
  );
}

export function normalize2(x, z) {
  const length = Math.hypot(x, z) || 1;
  return [x / length, z / length];
}

export function rayGroundIntersection(camera, direction, groundY = 0) {
  const denominator = direction[1];
  if (Math.abs(denominator) < 1e-8) return null;
  const distance = (groundY - camera[1]) / denominator;
  if (distance < 0) return null;
  return [
    camera[0] + direction[0] * distance,
    groundY,
    camera[2] + direction[2] * distance,
  ];
}
