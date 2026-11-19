import {
  catmullRom,
  clamp,
  modulo,
  normalize2,
} from "./math.js";

export const WORLD = {
  baseX: 1_100_288,
  baseZ: 2_300_416,
  tileSize: 512,
  routeLaps: 3,
};

export const COLORS = {
  groundA: [0.043, 0.112, 0.12],
  groundB: [0.052, 0.132, 0.138],
  groundFar: [0.032, 0.082, 0.09],
  microGrid: [0.078, 0.205, 0.205],
  grid: [0.105, 0.26, 0.255],
  partition: [0.4, 1.0, 0.93],
  asphalt: [0.075, 0.122, 0.13],
  asphaltEdge: [0.35, 0.26, 0.13],
  taxiLine: [1.0, 0.71, 0.31],
  apron: [0.09, 0.145, 0.15],
  apronEdge: [0.25, 0.5, 0.48],
  hangarBody: [0.29, 0.44, 0.45],
  hangarRoof: [0.14, 0.235, 0.245],
  hangarAccent: [1.0, 0.58, 0.21],
  hangarDoor: [0.105, 0.225, 0.255],
  pole: [0.2, 0.36, 0.35],
  lamp: [1.0, 0.82, 0.52],
  service: [0.22, 0.32, 0.31],
  cart: [0.87, 0.54, 0.21],
  cyan: [0.3, 0.96, 0.9],
  marker: [1.0, 0.77, 0.37],
};

const ROUTE_LOCAL = [
  [-474, -262],
  [-188, -374],
  [190, -338],
  [485, -118],
  [454, 202],
  [145, 365],
  [-238, 344],
  [-507, 148],
];

function makeRoute(points, samplesPerSegment = 34) {
  const samples = [];
  const count = points.length;
  for (let segment = 0; segment < count; segment += 1) {
    const p0 = points[(segment - 1 + count) % count];
    const p1 = points[segment];
    const p2 = points[(segment + 1) % count];
    const p3 = points[(segment + 2) % count];
    for (let step = 0; step < samplesPerSegment; step += 1) {
      const t = step / samplesPerSegment;
      samples.push({
        x: catmullRom(p0[0], p1[0], p2[0], p3[0], t),
        z: catmullRom(p0[1], p1[1], p2[1], p3[1], t),
      });
    }
  }

  let total = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const current = samples[index];
    const next = samples[(index + 1) % samples.length];
    current.distance = total;
    current.tangent = normalize2(
      next.x - current.x,
      next.z - current.z,
    );
    total += Math.hypot(next.x - current.x, next.z - current.z);
  }

  function pointAt(distance) {
    const wrapped = modulo(distance, total);
    let low = 0;
    let high = samples.length - 1;
    while (low <= high) {
      const middle = (low + high) >> 1;
      if (samples[middle].distance <= wrapped) low = middle + 1;
      else high = middle - 1;
    }
    const index = Math.max(0, high);
    const current = samples[index];
    const next = samples[(index + 1) % samples.length];
    const segmentLength = next.distance > current.distance
      ? next.distance - current.distance
      : total - current.distance;
    const t = segmentLength > 0 ? (wrapped - current.distance) / segmentLength : 0;
    return {
      x: current.x + (next.x - current.x) * t,
      z: current.z + (next.z - current.z) * t,
      tangent: current.tangent,
    };
  }

  return { samples, length: total, pointAt };
}

export const ROUTE = makeRoute(ROUTE_LOCAL);

export const HANGARS = [
  {
    id: "H-01",
    name: "H-01 / WEST BAY",
    x: -286,
    z: -106,
    width: 124,
    depth: 68,
    height: 21,
    yaw: 0.1,
  },
  {
    id: "H-02",
    name: "H-02 / NORTH BAY",
    x: 302,
    z: -466,
    width: 146,
    depth: 64,
    height: 23,
    yaw: 0.035,
  },
  {
    id: "H-03",
    name: "H-03 / SOUTH BAY",
    x: -16,
    z: 236,
    width: 142,
    depth: 76,
    height: 23,
    yaw: 0.035,
  },
  {
    id: "H-04",
    name: "H-04 / EAST BAY",
    x: 660,
    z: -330,
    width: 108,
    depth: 58,
    height: 17,
    yaw: -0.04,
  },
  {
    id: "H-05",
    name: "H-05 / WEST BAY",
    x: -612,
    z: 26,
    width: 118,
    depth: 60,
    height: 19,
    yaw: 0.03,
  },
  {
    id: "H-06",
    name: "H-06 / RANGE BAY",
    x: 235,
    z: -550,
    width: 94,
    depth: 54,
    height: 15,
    yaw: -0.02,
  },
];

export function localToWorld(x, z, y = 0) {
  return [WORLD.baseX + x, y, WORLD.baseZ + z];
}

export function worldTileOrigin(x, z) {
  return [
    Math.floor(x / WORLD.tileSize) * WORLD.tileSize,
    Math.floor(z / WORLD.tileSize) * WORLD.tileSize,
  ];
}

function addScaled(target, value) {
  target.push(value);
}

class StaticGeometry {
  constructor() {
    this.chunks = new Map();
    this.worldPositions = [];
    this.worldColors = [];
  }

  chunkAt(x, z) {
    const [originX, originZ] = worldTileOrigin(x, z);
    const key = `${originX}:${originZ}`;
    if (!this.chunks.has(key)) {
      this.chunks.set(key, {
        originX,
        originZ,
        positions: [],
        colors: [],
      });
    }
    return this.chunks.get(key);
  }

  triangle(a, b, c, color) {
    const centerX = (a[0] + b[0] + c[0]) / 3;
    const centerZ = (a[2] + b[2] + c[2]) / 3;
    const chunk = this.chunkAt(centerX, centerZ);
    for (const point of [a, b, c]) {
      addScaled(chunk.positions, point[0] - chunk.originX);
      addScaled(chunk.positions, point[1]);
      addScaled(chunk.positions, point[2] - chunk.originZ);
      addScaled(chunk.colors, color[0]);
      addScaled(chunk.colors, color[1]);
      addScaled(chunk.colors, color[2]);
      addScaled(this.worldPositions, point[0]);
      addScaled(this.worldPositions, point[1]);
      addScaled(this.worldPositions, point[2]);
      addScaled(this.worldColors, color[0]);
      addScaled(this.worldColors, color[1]);
      addScaled(this.worldColors, color[2]);
    }
  }

  quad(a, b, c, d, color) {
    this.triangle(a, b, c, color);
    this.triangle(a, c, d, color);
  }

  line(x1, z1, x2, z2, width, color, y = 0.04) {
    const dx = x2 - x1;
    const dz = z2 - z1;
    const length = Math.hypot(dx, dz);
    if (length < 1e-5) return;
    const nx = (-dz / length) * width * 0.5;
    const nz = (dx / length) * width * 0.5;
    this.quad(
      [x1 + nx, y, z1 + nz],
      [x2 + nx, y, z2 + nz],
      [x2 - nx, y, z2 - nz],
      [x1 - nx, y, z1 - nz],
      color,
    );
  }

  rectangle(cx, cz, width, depth, yaw, color, y = 0.02) {
    const c = Math.cos(yaw);
    const s = Math.sin(yaw);
    const rotate = (x, z) => [cx + c * x + s * z, cz - s * x + c * z];
    const hw = width * 0.5;
    const hd = depth * 0.5;
    const p1 = rotate(-hw, -hd);
    const p2 = rotate(hw, -hd);
    const p3 = rotate(hw, hd);
    const p4 = rotate(-hw, hd);
    this.quad(
      [p1[0], y, p1[1]],
      [p2[0], y, p2[1]],
      [p3[0], y, p3[1]],
      [p4[0], y, p4[1]],
      color,
    );
  }

  rectangleOutline(cx, cz, width, depth, yaw, lineWidth, color, y = 0.03) {
    const c = Math.cos(yaw);
    const s = Math.sin(yaw);
    const rotate = (x, z) => [cx + c * x + s * z, cz - s * x + c * z];
    const hw = width * 0.5;
    const hd = depth * 0.5;
    const corners = [
      rotate(-hw, -hd),
      rotate(hw, -hd),
      rotate(hw, hd),
      rotate(-hw, hd),
    ];
    for (let index = 0; index < 4; index += 1) {
      const start = corners[index];
      const end = corners[(index + 1) % 4];
      this.line(start[0], start[1], end[0], end[1], lineWidth, color, y);
    }
  }
}

function buildGround(builder) {
  const tile = WORLD.tileSize;
  for (let tileX = -3; tileX <= 2; tileX += 1) {
    for (let tileZ = -3; tileZ <= 2; tileZ += 1) {
      const x0 = WORLD.baseX + tileX * tile;
      const z0 = WORLD.baseZ + tileZ * tile;
      const x1 = x0 + tile;
      const z1 = z0 + tile;
      const base = (tileX + tileZ) & 1 ? COLORS.groundA : COLORS.groundB;
      const color = tileX < -1 || tileZ < -1 ? COLORS.groundFar : base;
      builder.quad(
        [x0, -0.08, z0],
        [x1, -0.08, z0],
        [x1, -0.08, z1],
        [x0, -0.08, z1],
        color,
      );

      for (let offset = 64; offset < tile; offset += 64) {
        const alpha = offset % 128 === 0 ? COLORS.grid : COLORS.microGrid;
        builder.line(x0 + offset, z0 + 2, x0 + offset, z1 - 2, 0.11, alpha, -0.04);
        builder.line(x0 + 2, z0 + offset, x1 - 2, z0 + offset, 0.11, alpha, -0.04);
      }
    }
  }

  for (let tileX = -3; tileX <= 3; tileX += 1) {
    const x = WORLD.baseX + tileX * tile;
    builder.line(x, WORLD.baseZ - 3 * tile, x, WORLD.baseZ + 2 * tile, 0.55, COLORS.partition, 0.01);
  }
  for (let tileZ = -3; tileZ <= 3; tileZ += 1) {
    const z = WORLD.baseZ + tileZ * tile;
    builder.line(WORLD.baseX - 3 * tile, z, WORLD.baseX + 2 * tile, z, 0.55, COLORS.partition, 0.01);
  }

  for (let tileX = -2; tileX <= 1; tileX += 1) {
    for (let tileZ = -2; tileZ <= 1; tileZ += 1) {
      const x = WORLD.baseX + tileX * tile;
      const z = WORLD.baseZ + tileZ * tile;
      builder.line(x - 12, z, x + 12, z, 0.18, COLORS.partition, 0.07);
      builder.line(x, z - 12, x, z + 12, 0.18, COLORS.partition, 0.07);
    }
  }
}

function buildRouteSurface(builder) {
  const samples = ROUTE.samples;
  for (let index = 0; index < samples.length; index += 1) {
    const current = samples[index];
    const next = samples[(index + 1) % samples.length];
    const currentWorld = localToWorld(current.x, current.z);
    const nextWorld = localToWorld(next.x, next.z);
    const nx = current.tangent[1];
    const nz = -current.tangent[0];
    const halfWidth = 4.8;
    builder.quad(
      [currentWorld[0] + nx * halfWidth, 0.015, currentWorld[2] + nz * halfWidth],
      [nextWorld[0] + nx * halfWidth, 0.015, nextWorld[2] + nz * halfWidth],
      [nextWorld[0] - nx * halfWidth, 0.015, nextWorld[2] - nz * halfWidth],
      [currentWorld[0] - nx * halfWidth, 0.015, currentWorld[2] - nz * halfWidth],
      COLORS.asphalt,
    );
  }

  for (let index = 0; index < samples.length; index += 1) {
    const current = samples[index];
    const next = samples[(index + 1) % samples.length];
    const nx = current.tangent[1];
    const nz = -current.tangent[0];
    const cw = localToWorld(current.x, current.z);
    const nw = localToWorld(next.x, next.z);

    builder.line(
      cw[0] + nx * 4.1,
      cw[2] + nz * 4.1,
      nw[0] + nx * 4.1,
      nw[2] + nz * 4.1,
      0.1,
      COLORS.asphaltEdge,
      0.04,
    );
    builder.line(
      cw[0] - nx * 4.1,
      cw[2] - nz * 4.1,
      nw[0] - nx * 4.1,
      nw[2] - nz * 4.1,
      0.1,
      COLORS.asphaltEdge,
      0.04,
    );

    if (current.distance % 13 < next.distance - current.distance) {
      builder.line(
        cw[0] - nx * 3.6,
        cw[2] - nz * 3.6,
        cw[0] + nx * 3.6,
        cw[2] + nz * 3.6,
        0.075,
        [0.28, 0.23, 0.12],
        0.041,
      );
    }

    if (index % 6 === 0) {
      const lightColor = index % 12 === 0 ? COLORS.cyan : COLORS.taxiLine;
      for (const side of [-1, 1]) {
        const lightX = cw[0] + nx * 5.35 * side;
        const lightZ = cw[2] + nz * 5.35 * side;
        builder.line(
          lightX - current.tangent[0] * 0.62,
          lightZ - current.tangent[1] * 0.62,
          lightX + current.tangent[0] * 0.62,
          lightZ + current.tangent[1] * 0.62,
          0.22,
          lightColor,
          0.07,
        );
      }
    }

    if (Math.floor(current.distance / 8) % 2 === 0) {
      builder.line(
        cw[0],
        cw[2],
        nw[0],
        nw[2],
        0.18,
        COLORS.taxiLine,
        0.055,
      );
    }
  }
}

function buildAprons(builder) {
  for (const hangar of HANGARS) {
    const center = localToWorld(hangar.x, hangar.z);
    builder.rectangle(
      center[0],
      center[2],
      hangar.width + 54,
      hangar.depth + 48,
      hangar.yaw,
      COLORS.apron,
      0.005,
    );
    builder.rectangleOutline(
      center[0],
      center[2],
      hangar.width + 52,
      hangar.depth + 46,
      hangar.yaw,
      0.16,
      COLORS.apronEdge,
      0.025,
    );

    const c = Math.cos(hangar.yaw);
    const s = Math.sin(hangar.yaw);
    const front = hangar.depth * 0.5 + 24;
    const leadInStart = [
      center[0] + c * (hangar.width * 0.34),
      center[2] - s * (hangar.width * 0.34),
    ];
    const leadInEnd = [
      center[0] + c * (hangar.width * 0.34) + s * front,
      center[2] - s * (hangar.width * 0.34) + c * front,
    ];
    builder.line(
      leadInStart[0],
      leadInStart[1],
      leadInEnd[0],
      leadInEnd[1],
      0.14,
      COLORS.taxiLine,
      0.045,
    );

    for (let slot = -2; slot <= 2; slot += 1) {
      const localX = slot * (hangar.width * 0.12);
      const localZ = hangar.depth * 0.5 + 10;
      const x = center[0] + c * localX + s * localZ;
      const z = center[2] - s * localX + c * localZ;
      builder.line(x - c * 2.2, z + s * 2.2, x + c * 2.2, z - s * 2.2, 0.07, [0.23, 0.34, 0.33], 0.035);
    }
  }
}

function staticBoxParts() {
  const boxes = [];
  for (const hangar of HANGARS) {
    const center = localToWorld(hangar.x, hangar.z);
    const c = Math.cos(hangar.yaw);
    const s = Math.sin(hangar.yaw);
    const at = (localX, localZ) => [
      center[0] + c * localX + s * localZ,
      center[2] - s * localX + c * localZ,
    ];

    boxes.push({
      x: center[0],
      y: hangar.height * 0.5,
      z: center[2],
      sx: hangar.width,
      sy: hangar.height,
      sz: hangar.depth,
      yaw: hangar.yaw,
      color: COLORS.hangarBody,
    });
    boxes.push({
      x: center[0],
      y: hangar.height + 0.55,
      z: center[2],
      sx: hangar.width + 2.2,
      sy: 1.1,
      sz: hangar.depth + 2.2,
      yaw: hangar.yaw,
      color: COLORS.hangarRoof,
    });

    const door = at(0, hangar.depth * 0.5 + 0.35);
    boxes.push({
      x: door[0],
      y: hangar.height * 0.37,
      z: door[1],
      sx: hangar.width * 0.7,
      sy: hangar.height * 0.69,
      sz: 0.45,
      yaw: hangar.yaw,
      color: COLORS.hangarDoor,
    });

    const accent = at(hangar.width * 0.5 + 0.5, hangar.depth * 0.18);
    boxes.push({
      x: accent[0],
      y: hangar.height * 0.56,
      z: accent[1],
      sx: 0.5,
      sy: 0.72,
      sz: hangar.depth * 0.72,
      yaw: hangar.yaw,
      color: COLORS.hangarAccent,
    });

    const frontZ = hangar.depth * 0.5 + 0.62;
    const frontFascia = at(0, frontZ);
    boxes.push({
      x: frontFascia[0],
      y: hangar.height + 0.18,
      z: frontFascia[1],
      sx: hangar.width * 0.82,
      sy: 0.32,
      sz: 0.44,
      yaw: hangar.yaw,
      color: COLORS.hangarAccent,
    });
    for (const slot of [-0.28, 0, 0.28]) {
      const slat = at(hangar.width * slot, frontZ + 0.1);
      boxes.push({
        x: slat[0],
        y: hangar.height * 0.32,
        z: slat[1],
        sx: 0.28,
        sy: hangar.height * 0.52,
        sz: 0.22,
        yaw: hangar.yaw,
        color: [0.32, 0.61, 0.6],
      });
    }

    for (const side of [-1, 1]) {
      const mast = at(side * (hangar.width * 0.5 + 18), hangar.depth * 0.5 + 33);
      boxes.push({
        x: mast[0],
        y: 11.6,
        z: mast[1],
        sx: 0.34,
        sy: 23.2,
        sz: 0.34,
        yaw: 0,
        color: [0.23, 0.4, 0.39],
      });
      boxes.push({
        x: mast[0],
        y: 23.1,
        z: mast[1],
        sx: 2.8,
        sy: 0.28,
        sz: 0.56,
        yaw: hangar.yaw,
        color: COLORS.lamp,
      });
    }

    for (const side of [-1, 1]) {
      const cargo = at(side * (hangar.width * 0.5 + 9), -hangar.depth * 0.36);
      boxes.push({
        x: cargo[0],
        y: 1.45,
        z: cargo[1],
        sx: 5.7,
        sy: 2.9,
        sz: 2.4,
        yaw: hangar.yaw + 0.03,
        color: side > 0 ? [0.22, 0.37, 0.36] : [0.34, 0.29, 0.19],
      });
    }

    const serviceA = at(hangar.width * 0.31, hangar.depth * 0.5 + 17);
    const serviceB = at(hangar.width * 0.2, hangar.depth * 0.5 + 23);
    boxes.push({
      x: serviceA[0],
      y: 1.55,
      z: serviceA[1],
      sx: 5.8,
      sy: 3.1,
      sz: 3.1,
      yaw: hangar.yaw + 0.2,
      color: COLORS.service,
    });
    boxes.push({
      x: serviceB[0],
      y: 0.9,
      z: serviceB[1],
      sx: 2.1,
      sy: 1.8,
      sz: 3.7,
      yaw: hangar.yaw - 0.3,
      color: COLORS.cart,
    });
  }

  const poleSpacing = 76;
  for (let distance = 24; distance < ROUTE.length; distance += poleSpacing) {
    const point = ROUTE.pointAt(distance);
    const nx = point.tangent[1];
    const nz = -point.tangent[0];
    for (const side of [-1, 1]) {
      const world = localToWorld(
        point.x + nx * 6.4 * side,
        point.z + nz * 6.4 * side,
      );
      boxes.push({
        x: world[0],
        y: 5.35,
        z: world[2],
        sx: 0.24,
        sy: 10.7,
        sz: 0.24,
        yaw: 0,
        color: COLORS.pole,
      });
      boxes.push({
        x: world[0],
        y: 10.65,
        z: world[2],
        sx: 1.2,
        sy: 0.18,
        sz: 0.34,
        yaw: Math.atan2(point.tangent[0], point.tangent[1]),
        color: COLORS.lamp,
      });
    }
  }

  for (const gridX of [-512, 0, 512]) {
    for (const gridZ of [-512, 0, 512]) {
      if (gridX === 0 && gridZ === 0) continue;
      const center = localToWorld(gridX, gridZ);
      boxes.push({
        x: center[0],
        y: 1.45,
        z: center[2],
        sx: 0.24,
        sy: 2.9,
        sz: 0.24,
        yaw: 0,
        color: [0.22, 0.59, 0.57],
      });
      boxes.push({
        x: center[0],
        y: 2.95,
        z: center[2],
        sx: 0.8,
        sy: 0.16,
        sz: 0.8,
        yaw: Math.PI * 0.25,
        color: COLORS.cyan,
      });
    }
  }

  return boxes;
}

export const STATIC_GEOMETRY = (() => {
  const builder = new StaticGeometry();
  buildGround(builder);
  buildRouteSurface(builder);
  buildAprons(builder);
  return {
    chunks: [...builder.chunks.values()],
    worldPositions: new Float64Array(builder.worldPositions),
    worldColors: new Float32Array(builder.worldColors),
  };
})();

export const STATIC_BOXES = staticBoxParts();

export const UNIT_CUBE = (() => {
  const vertices = [];
  const colors = [];
  const faces = [
    { normal: [0, 1, 0], points: [[-0.5, 1, -0.5], [-0.5, 1, 0.5], [0.5, 1, 0.5], [0.5, 1, -0.5]] },
    { normal: [0, -1, 0], points: [[-0.5, 0, 0.5], [-0.5, 0, -0.5], [0.5, 0, -0.5], [0.5, 0, 0.5]] },
    { normal: [0, 0, 1], points: [[-0.5, 0, 0.5], [0.5, 0, 0.5], [0.5, 1, 0.5], [-0.5, 1, 0.5]] },
    { normal: [0, 0, -1], points: [[0.5, 0, -0.5], [-0.5, 0, -0.5], [-0.5, 1, -0.5], [0.5, 1, -0.5]] },
    { normal: [1, 0, 0], points: [[0.5, 0, 0.5], [0.5, 0, -0.5], [0.5, 1, -0.5], [0.5, 1, 0.5]] },
    { normal: [-1, 0, 0], points: [[-0.5, 0, -0.5], [-0.5, 0, 0.5], [-0.5, 1, 0.5], [-0.5, 1, -0.5]] },
  ];
  const indices = [0, 1, 2, 0, 2, 3];
  for (const face of faces) {
    for (const index of indices) {
      vertices.push(...face.points[index], ...face.normal);
      const shade = 0.74 + Math.max(0, face.normal[1]) * 0.16;
      colors.push(shade, shade, shade);
    }
  }
  return {
    vertices: new Float32Array(vertices),
    colors: new Float32Array(colors),
    count: vertices.length / 6,
  };
})();

export function createCamera(distance, yawOffset = 0, pitchOffset = 0) {
  const point = ROUTE.pointAt(distance);
  const ahead = ROUTE.pointAt(distance + 155);
  const eye = localToWorld(
    point.x,
    point.z,
    44 + Math.sin(distance * 0.011) * 1.8,
  );
  const target = localToWorld(ahead.x, ahead.z, 1.5);
  let dx = target[0] - eye[0];
  let dy = target[1] - eye[1];
  let dz = target[2] - eye[2];
  const horizontal = Math.hypot(dx, dz) || 1;
  const baseYaw = Math.atan2(dx, -dz);
  const basePitch = Math.atan2(dy, horizontal);
  const yaw = baseYaw + yawOffset;
  const pitch = clamp(basePitch + pitchOffset, -0.42, 0.32);
  const cosPitch = Math.cos(pitch);
  const forward = [
    Math.sin(yaw) * cosPitch,
    Math.sin(pitch),
    -Math.cos(yaw) * cosPitch,
  ];
  const right = normalize2(-forward[2], forward[0]);
  const up = [
    -right[1] * forward[1],
    right[1] * forward[0] - right[0] * forward[2],
    right[0] * forward[1],
  ];
  return {
    eye,
    forward,
    right: [right[0], 0, right[1]],
    up,
    yaw,
    pitch,
    routePoint: point,
  };
}

export function dynamicVehicleBoxes(time) {
  const boxes = [];
  const vehicleSpecs = [
    { offset: 84, speed: 17, lateral: -1.7, color: COLORS.cart },
    { offset: 460, speed: 13, lateral: 1.85, color: [0.25, 0.74, 0.7] },
    { offset: 890, speed: 21, lateral: -2.1, color: [0.72, 0.42, 0.19] },
    { offset: 1320, speed: 11, lateral: 1.6, color: [0.36, 0.58, 0.56] },
    { offset: 1710, speed: 19, lateral: -1.55, color: COLORS.cyan },
  ];

  for (const spec of vehicleSpecs) {
    const distance = modulo(time * spec.speed + spec.offset, ROUTE.length);
    const point = ROUTE.pointAt(distance);
    const nx = point.tangent[1];
    const nz = -point.tangent[0];
    const world = localToWorld(
      point.x + nx * spec.lateral,
      point.z + nz * spec.lateral,
    );
    const yaw = Math.atan2(point.tangent[0], point.tangent[1]);
    boxes.push({
      x: world[0],
      y: 0.72,
      z: world[2],
      sx: 2.05,
      sy: 1.15,
      sz: 4.5,
      yaw,
      color: spec.color,
    });
    const cabinForward = 0.4;
    boxes.push({
      x: world[0] + point.tangent[0] * cabinForward,
      y: 1.62,
      z: world[2] + point.tangent[1] * cabinForward,
      sx: 1.6,
      sy: 0.72,
      sz: 1.8,
      yaw,
      color: [0.18, 0.3, 0.3],
    });
  }
  return boxes;
}

export function pickBoxes(pickWorld, targetHangar) {
  if (!pickWorld || !targetHangar) return [];
  const target = localToWorld(targetHangar.x, targetHangar.z);
  const dx = target[0] - pickWorld[0];
  const dz = target[2] - pickWorld[2];
  const length = Math.hypot(dx, dz);
  const yaw = Math.atan2(dx, dz);
  return [
    {
      x: pickWorld[0],
      y: 2.2,
      z: pickWorld[2],
      sx: 0.22,
      sy: 4.4,
      sz: 0.22,
      yaw: 0,
      color: COLORS.marker,
    },
    {
      x: pickWorld[0],
      y: 0.08,
      z: pickWorld[2],
      sx: 4.6,
      sy: 0.06,
      sz: 0.23,
      yaw: 0,
      color: COLORS.marker,
    },
    {
      x: pickWorld[0],
      y: 0.08,
      z: pickWorld[2],
      sx: 0.23,
      sy: 0.06,
      sz: 4.6,
      yaw: 0,
      color: COLORS.marker,
    },
    {
      x: pickWorld[0] + dx * 0.5,
      y: 0.16,
      z: pickWorld[2] + dz * 0.5,
      sx: 0.11,
      sy: 0.1,
      sz: Math.max(0.1, length),
      yaw,
      color: [0.34, 0.92, 0.86],
    },
  ];
}

export function nearestHangar(worldX, worldZ) {
  let nearest = null;
  let nearestDistance = Infinity;
  for (const hangar of HANGARS) {
    const center = localToWorld(hangar.x, hangar.z);
    const distance = Math.hypot(worldX - center[0], worldZ - center[2]);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearest = hangar;
    }
  }
  return { hangar: nearest, distance: nearestDistance };
}

export function routeStartDistance() {
  return ROUTE.length * 0.115;
}

