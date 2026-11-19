export const PI = Math.PI;
export const TAU = Math.PI * 2;

export const clamp = (value, lo, hi) => Math.min(hi, Math.max(lo, value));
export const lerp = (a, b, t) => a + (b - a) * t;
export const smoothstep = (a, b, value) => {
  const t = clamp((value - a) / (b - a), 0, 1);
  return t * t * (3 - 2 * t);
};

export const v3 = (x = 0, y = 0, z = 0) => [x, y, z];
export const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const mul = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
export const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a, b) => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
export const length = (a) => Math.hypot(a[0], a[1], a[2]);
export const normalize = (a) => {
  const len = length(a);
  return len > 1e-12 ? mul(a, 1 / len) : [0, 0, 1];
};
export const reflect = (direction, normal) =>
  sub(direction, mul(normal, 2 * dot(direction, normal)));

export function mulberry32(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function radicalInverse(index, base) {
  let result = 0;
  let fraction = 1 / base;
  let value = index;
  while (value > 0) {
    result += (value % base) * fraction;
    value = Math.floor(value / base);
    fraction /= base;
  }
  return result;
}

export function halton2D(index) {
  return [radicalInverse(index + 1, 2), radicalInverse(index + 1, 3)];
}

export function basisFromNormal(normal, view) {
  const n = normalize(normal);
  let t1 = sub(view, mul(n, dot(view, n)));
  if (length(t1) < 1e-7) t1 = [1, 0, 0];
  t1 = normalize(t1);
  const t2 = normalize(mul(cross(n, t1), -1));
  return [t1, t2, n];
}

export function toLocal(direction, basis) {
  return [
    dot(direction, basis[0]),
    dot(direction, basis[1]),
    dot(direction, basis[2]),
  ];
}

export function fromLocal(local, basis) {
  return normalize([
    basis[0][0] * local[0] + basis[1][0] * local[1] + basis[2][0] * local[2],
    basis[0][1] * local[0] + basis[1][1] * local[1] + basis[2][1] * local[2],
    basis[0][2] * local[0] + basis[1][2] * local[1] + basis[2][2] * local[2],
  ]);
}

export function mean(values) {
  if (!values.length) return 0;
  let sum = 0;
  for (const value of values) sum += value;
  return sum / values.length;
}

export function percentile(values, fraction) {
  if (!values.length) return 0;
  const sorted = values.slice().sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(fraction * sorted.length)))];
}
