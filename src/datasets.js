import { gaussian, mulberry32, normalize } from "./math.js";

function randomCloud(count, seed) {
  const random = mulberry32(seed);
  const points = [];
  while (points.length < count) {
    const direction = normalize([
      gaussian(random),
      gaussian(random),
      gaussian(random),
    ]);
    const radius = 0.24 + 0.76 * Math.cbrt(random());
    points.push([
      direction[0] * radius * 1.22,
      direction[1] * radius * 0.92,
      direction[2] * radius * 1.06,
    ]);
  }
  return points;
}

function coplanarCloud() {
  const points = [];
  for (let row = -3; row <= 3; row += 1) {
    for (let column = -3; column <= 3; column += 1) {
      if (row * row + column * column > 11) continue;
      points.push([column * 0.19, row * 0.19, 0]);
    }
  }
  points.push([0.84, 0.1, 0], [-0.72, -0.32, 0], [0.16, 0.83, 0]);
  return points;
}

function fibonacciSphere(count, radius = 1.08) {
  const points = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let index = 0; index < count; index += 1) {
    const y = 1 - (index / Math.max(count - 1, 1)) * 2;
    const radial = Math.sqrt(Math.max(1 - y * y, 0));
    const theta = golden * index;
    points.push([
      Math.cos(theta) * radial * radius,
      y * radius,
      Math.sin(theta) * radial * radius,
    ]);
  }
  return points;
}

function sphereWithEquatorRings() {
  const points = fibonacciSphere(27, 1.12);
  for (let index = 0; index < 16; index += 1) {
    const angle = (index / 16) * Math.PI * 2;
    points.push([Math.cos(angle) * 1.12, 0, Math.sin(angle) * 1.12]);
  }
  for (let index = 0; index < 10; index += 1) {
    const angle = (index / 10) * Math.PI * 2 + 0.13;
    points.push([
      Math.cos(angle) * 1.12 * Math.cos(0.58),
      Math.sin(0.58) * 1.12,
      Math.sin(angle) * 1.12 * Math.cos(0.58),
    ]);
  }
  return points;
}

function mixedCloud(extra = false) {
  const points = extra ? sphereWithEquatorRings() : fibonacciSphere(30, 1.2);
  const planeHeight = extra ? 0.24 : 0;
  for (let row = -2; row <= 2; row += 1) {
    for (let column = -2; column <= 2; column += 1) {
      if (Math.abs(row) + Math.abs(column) > 3) continue;
      points.push([column * 0.21, planeHeight, row * 0.21]);
    }
  }
  if (extra) {
    points.push(points[0].slice(), points[1].slice(), points[5].slice());
  }
  return points;
}

export const DATASETS = [
  {
    id: "random",
    name: "随机点集",
    short: "RANDOM",
    description: "确定性高斯云 / 46 点 / 一般位置基线",
    seed: 41023,
    points: randomCloud(46, 41023),
  },
  {
    id: "coplanar",
    name: "全共面点集",
    short: "COPLANAR",
    description: "z=0 网格与圆盘点 / 内在维数 2",
    seed: 1729,
    points: coplanarCloud(),
  },
  {
    id: "cospherical",
    name: "全共球点集",
    short: "COSPHERICAL",
    description: "Fibonacci 球面 / 38 点同球",
    seed: 2718,
    points: fibonacciSphere(38),
  },
  {
    id: "mixed",
    name: "共面 + 共球混合",
    short: "MIXED",
    description: "球壳 + 赤道平面网格 / 两类退化叠加",
    seed: 3141,
    points: mixedCloud(false),
  },
  {
    id: "mixed-extra",
    name: "补充退化点集",
    short: "MIXED+",
    description: "多纬球环 + 偏置平面网格 + 重复点",
    seed: 1618,
    points: mixedCloud(true),
  },
];

export function getDataset(id) {
  return DATASETS.find((dataset) => dataset.id === id) ?? DATASETS[0];
}
