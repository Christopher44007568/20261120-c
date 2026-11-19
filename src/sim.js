const GRID_N = 5;
const WIDTH = 2.2;
const DEPTH = 2.2;
const HEIGHT = 2.4;
const REST_VOLUME = WIDTH * DEPTH * HEIGHT;
const MM_PER_UNIT = 90;

const NEIGHBOR_OFFSETS = [
  [1, 0, 0], [0, 1, 0], [0, 0, 1],
  [1, 1, 0], [1, -1, 0], [1, 0, 1], [1, 0, -1], [0, 1, 1], [0, 1, -1],
  [1, 1, 1], [1, 1, -1], [1, -1, 1], [1, -1, -1],
];

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function index3(x, y, z, n = GRID_N) {
  return (x * n + y) * n + z;
}

function buildGrid(n = GRID_N) {
  const points = [];
  const rest = [];
  for (let ix = 0; ix < n; ix += 1) {
    for (let iy = 0; iy < n; iy += 1) {
      for (let iz = 0; iz < n; iz += 1) {
        const x = (ix / (n - 1) - 0.5) * WIDTH;
        const y = (iy / (n - 1) - 0.5) * DEPTH;
        const z = (iz / (n - 1) - 0.5) * HEIGHT;
        const anchor = iz === 0 || iz === n - 1 ? (iz === 0 ? -1 : 1) : 0;
        points.push({
          x, y, z, px: x, py: y, pz: z,
          vx: 0, vy: 0, vz: 0,
          invMass: 1, anchor,
          index: points.length,
        });
        rest.push({ x, y, z });
      }
    }
  }
  return { points, rest };
}

function buildConstraints(points, n = GRID_N) {
  const constraints = [];
  for (let ix = 0; ix < n; ix += 1) {
    for (let iy = 0; iy < n; iy += 1) {
      for (let iz = 0; iz < n; iz += 1) {
        const i = index3(ix, iy, iz, n);
        for (const [dx, dy, dz] of NEIGHBOR_OFFSETS) {
          const jx = ix + dx;
          const jy = iy + dy;
          const jz = iz + dz;
          if (jx < 0 || jx >= n || jy < 0 || jy >= n || jz < 0 || jz >= n) continue;
          const j = index3(jx, jy, jz, n);
          const a = points[i];
          const b = points[j];
          constraints.push({
            a: i,
            b: j,
            rest: Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z),
            axis: Math.abs(dx) + Math.abs(dy) + Math.abs(dz) === 1,
          });
        }
      }
    }
  }
  return constraints;
}

function buildSurface(points, n = GRID_N) {
  const faces = [];
  const addQuad = (a, b, c, d) => {
    const p0 = points[a];
    const p1 = points[b];
    const p2 = points[c];
    const p3 = points[d];
    const ux = p1.x - p0.x;
    const uy = p1.y - p0.y;
    const uz = p1.z - p0.z;
    const vx = p3.x - p0.x;
    const vy = p3.y - p0.y;
    const vz = p3.z - p0.z;
    const nx = uy * vz - uz * vy;
    const ny = uz * vx - ux * vz;
    const nz = ux * vy - uy * vx;
    const cx = (p0.x + p1.x + p2.x + p3.x) / 4;
    const cy = (p0.y + p1.y + p2.y + p3.y) / 4;
    const cz = (p0.z + p1.z + p2.z + p3.z) / 4;
    const outward = nx * cx + ny * cy + nz * cz > 0;
    if (outward) {
      faces.push([a, b, c], [a, c, d]);
    } else {
      faces.push([a, d, c], [a, c, b]);
    }
  };

  for (let ix = 0; ix < n - 1; ix += 1) {
    for (let iy = 0; iy < n - 1; iy += 1) {
      addQuad(
        index3(ix, iy, 0, n),
        index3(ix, iy + 1, 0, n),
        index3(ix + 1, iy + 1, 0, n),
        index3(ix + 1, iy, 0, n),
      );
      addQuad(
        index3(ix, iy, n - 1, n),
        index3(ix + 1, iy, n - 1, n),
        index3(ix + 1, iy + 1, n - 1, n),
        index3(ix, iy + 1, n - 1, n),
      );
    }
  }
  for (let ix = 0; ix < n - 1; ix += 1) {
    for (let iz = 0; iz < n - 1; iz += 1) {
      addQuad(
        index3(ix, 0, iz, n),
        index3(ix + 1, 0, iz, n),
        index3(ix + 1, 0, iz + 1, n),
        index3(ix, 0, iz + 1, n),
      );
      addQuad(
        index3(ix, n - 1, iz, n),
        index3(ix, n - 1, iz + 1, n),
        index3(ix + 1, n - 1, iz + 1, n),
        index3(ix + 1, n - 1, iz, n),
      );
    }
  }
  for (let iy = 0; iy < n - 1; iy += 1) {
    for (let iz = 0; iz < n - 1; iz += 1) {
      addQuad(
        index3(0, iy, iz, n),
        index3(0, iy, iz + 1, n),
        index3(0, iy + 1, iz + 1, n),
        index3(0, iy + 1, iz, n),
      );
      addQuad(
        index3(n - 1, iy, iz, n),
        index3(n - 1, iy + 1, iz, n),
        index3(n - 1, iy + 1, iz + 1, n),
        index3(n - 1, iy, iz + 1, n),
      );
    }
  }
  return faces;
}

function signedVolume(points, faces) {
  let volume = 0;
  for (const [a, b, c] of faces) {
    const p0 = points[a];
    const p1 = points[b];
    const p2 = points[c];
    volume += (
      p0.x * (p1.y * p2.z - p1.z * p2.y)
      + p0.y * (p1.z * p2.x - p1.x * p2.z)
      + p0.z * (p1.x * p2.y - p1.y * p2.x)
    ) / 6;
  }
  return volume;
}

export class SoftBody {
  constructor(options = {}) {
    this.grid = options.grid ?? GRID_N;
    this.iterations = options.iterations ?? 24;
    this.stiffness = options.stiffness ?? 0.82;
    this.mode = options.mode ?? "compress";
    this.strain = options.strain ?? 0.18;
    this.collision = options.collision ?? true;
    this.seed = options.seed ?? 0;
    this.volumeStiffness = options.volumeStiffness ?? 0.45;
    this.shapeStiffness = options.shapeStiffness ?? 0.012;
    this.timeScale = options.timeScale ?? 1;
    this.points = [];
    this.rest = [];
    this.constraints = [];
    this.faces = [];
    this.restVolume = REST_VOLUME;
    this.stepCount = 0;
    this.progress = options.instant ? 1 : 0;
    this.topPlate = HEIGHT / 2;
    this.bottomPlate = -HEIGHT / 2;
    this.targetGap = HEIGHT;
    this.sphereCenter = { x: 1.43, y: 0.08, z: 0.13 };
    this.sphereRadius = 0.72;
    this.volume = this.restVolume;
    this.reset();
    this.setDeformation(this.mode, this.strain, Boolean(options.instant));
  }

  reset() {
    const { points, rest } = buildGrid(this.grid);
    this.points = points;
    this.rest = rest;
    this.constraints = buildConstraints(points, this.grid);
    this.faces = buildSurface(points, this.grid);
    this.stepCount = 0;
    this.progress = 0;
    this.topPlate = HEIGHT / 2;
    this.bottomPlate = -HEIGHT / 2;
    this.targetGap = this.mode === "compress"
      ? HEIGHT * (1 - this.strain)
      : HEIGHT * (1 + this.strain);

    if (this.seed) {
      for (let i = 0; i < this.points.length; i += 1) {
        const p = this.points[i];
        const phase = i * 1.618 + this.seed * 0.73;
        p.vx = Math.sin(phase) * 0.008;
        p.vy = Math.cos(phase * 1.13) * 0.008;
        p.vz = Math.sin(phase * 0.61) * 0.004;
      }
    }
    this.volume = signedVolume(this.points, this.faces);
  }

  setDeformation(mode, strain, instant = false) {
    this.mode = mode;
    this.strain = clamp(strain, 0.01, 0.45);
    this.targetGap = mode === "compress"
      ? HEIGHT * (1 - this.strain)
      : HEIGHT * (1 + this.strain);
    if (instant) {
      this.progress = 1;
      this.topPlate = this.targetGap / 2;
      this.bottomPlate = -this.targetGap / 2;
      this.solveAnchors();
    }
  }

  setIterations(iterations) {
    this.iterations = clamp(Math.round(iterations), 1, 64);
  }

  setStiffness(stiffness) {
    this.stiffness = clamp(stiffness, 0.1, 1);
  }

  resetMotion() {
    for (const p of this.points) {
      p.x = p.px = this.rest[p.index].x;
      p.y = p.py = this.rest[p.index].y;
      p.z = p.pz = this.rest[p.index].z;
      p.vx = p.vy = p.vz = 0;
    }
    this.progress = 0;
    this.topPlate = HEIGHT / 2;
    this.bottomPlate = -HEIGHT / 2;
    this.stepCount = 0;
    this.volume = signedVolume(this.points, this.faces);
  }

  solveAnchors() {
    for (const p of this.points) {
      if (p.anchor === -1) p.z = this.bottomPlate;
      if (p.anchor === 1) p.z = this.topPlate;
      if (p.anchor !== 0) {
        p.pz = p.z;
        p.vz = 0;
      }
    }
  }

  solveDistance() {
    const k = this.stiffness * 0.18;
    for (const c of this.constraints) {
      const a = this.points[c.a];
      const b = this.points[c.b];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dz = b.z - a.z;
      const distance = Math.hypot(dx, dy, dz);
      if (distance < 1e-8) continue;
      const w = a.invMass + b.invMass;
      if (w === 0) continue;
      const correction = ((distance - c.rest) / distance) * k / w;
      a.x += dx * correction * a.invMass;
      a.y += dy * correction * a.invMass;
      a.z += dz * correction * a.invMass;
      b.x -= dx * correction * b.invMass;
      b.y -= dy * correction * b.invMass;
      b.z -= dz * correction * b.invMass;
    }
  }

  solvePlates() {
    for (const p of this.points) {
      p.z = clamp(p.z, this.bottomPlate, this.topPlate);
    }
    this.solveAnchors();
  }

  solveSphere() {
    if (!this.collision) return;
    const c = this.sphereCenter;
    const r = this.sphereRadius;
    for (const p of this.points) {
      const dx = p.x - c.x;
      const dy = p.y - c.y;
      const dz = p.z - c.z;
      const distance = Math.hypot(dx, dy, dz);
      if (distance >= r || distance < 1e-8) continue;
      const scale = (r + 0.004) / distance;
      p.x = c.x + dx * scale;
      p.y = c.y + dy * scale;
      p.z = c.z + dz * scale;
    }
  }

  solveShape() {
    let xx = 0;
    let yy = 0;
    let zz = 0;
    let rx = 0;
    let ry = 0;
    let rz = 0;
    for (const p of this.points) {
      const r = this.rest[p.index];
      xx += r.x * p.x;
      yy += r.y * p.y;
      zz += r.z * p.z;
      rx += r.x * r.x;
      ry += r.y * r.y;
      rz += r.z * r.z;
    }
    const sx = clamp(xx / Math.max(rx, 1e-8), 0.55, 1.8);
    const sy = clamp(yy / Math.max(ry, 1e-8), 0.55, 1.8);
    const sz = clamp(zz / Math.max(rz, 1e-8), 0.55, 1.8);
    const blend = this.shapeStiffness;
    for (const p of this.points) {
      const r = this.rest[p.index];
      p.x += (r.x * sx - p.x) * blend;
      p.y += (r.y * sy - p.y) * blend;
      if (p.anchor === 0) p.z += (r.z * sz - p.z) * blend;
    }
  }

  solveVolume() {
    const volume = signedVolume(this.points, this.faces);
    if (volume < 1e-5) return;
    const ratio = this.restVolume / Math.abs(volume);
    const scaleTarget = Math.sqrt(ratio);
    const scale = clamp(1 + (scaleTarget - 1) * this.volumeStiffness, 0.72, 1.38);
    if (!Number.isFinite(scale) || Math.abs(scale - 1) < 1e-8) return;
    const cx = 0;
    const cy = 0;
    for (const p of this.points) {
      p.x = cx + (p.x - cx) * scale;
      p.y = cy + (p.y - cy) * scale;
    }
  }

  integrate(dt) {
    const gravity = this.mode === "stretch" ? -0.16 : -0.34;
    const damping = 0.997;
    for (const p of this.points) {
      p.px = p.x;
      p.py = p.y;
      p.pz = p.z;
      p.vz += gravity * dt;
      p.vx *= damping;
      p.vy *= damping;
      p.vz *= damping;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.z += p.vz * dt;
    }
  }

  updateVelocities(dt) {
    const invDt = 1 / dt;
    for (const p of this.points) {
      p.vx = (p.x - p.px) * invDt * 0.992;
      p.vy = (p.y - p.py) * invDt * 0.992;
      p.vz = (p.z - p.pz) * invDt * 0.992;
    }
  }

  step(dt = 1 / 60, substeps = 2) {
    if (this.progress < 1) {
      this.progress = Math.min(1, this.progress + dt * 2.45 * this.timeScale);
      const eased = 1 - (1 - this.progress) ** 3;
      const gap = HEIGHT + (this.targetGap - HEIGHT) * eased;
      this.topPlate = gap / 2;
      this.bottomPlate = -gap / 2;
    }
    const subDt = dt / substeps;
    for (let s = 0; s < substeps; s += 1) {
      this.integrate(subDt);
      for (let i = 0; i < this.iterations; i += 1) {
        this.solveDistance();
        this.solveAnchors();
        this.solveSphere();
        this.solveShape();
        this.solveVolume();
      }
      this.solvePlates();
      this.updateVelocities(subDt);
    }
    this.stepCount += 1;
    this.volume = Math.abs(signedVolume(this.points, this.faces));
  }

  get gap() {
    return this.topPlate - this.bottomPlate;
  }

  get strainActual() {
    return this.mode === "compress"
      ? 1 - this.gap / HEIGHT
      : this.gap / HEIGHT - 1;
  }

  measure() {
    const gapFactor = this.gap / HEIGHT;
    const lateral = 1 / Math.sqrt(Math.max(gapFactor, 0.15));
    let squaredError = 0;
    let squaredVelocity = 0;
    let maxSpeed = 0;
    for (const p of this.points) {
      const r = this.rest[p.index];
      const targetX = r.x * lateral;
      const targetY = r.y * lateral;
      const targetZ = r.z * gapFactor;
      squaredError += (
        (p.x - targetX) ** 2
        + (p.y - targetY) ** 2
        + (p.z - targetZ) ** 2
      );
      const speed = Math.hypot(p.vx, p.vy, p.vz);
      squaredVelocity += speed * speed;
      maxSpeed = Math.max(maxSpeed, speed);
    }
    const count = this.points.length;
    const vertexError = Math.sqrt(squaredError / count) * MM_PER_UNIT;
    const velocityRms = Math.sqrt(squaredVelocity / count);
    let residual = 0;
    for (const c of this.constraints) {
      const a = this.points[c.a];
      const b = this.points[c.b];
      residual += Math.abs(Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z) - c.rest);
    }
    residual /= this.constraints.length;
    return {
      volume: this.volume,
      volumeRetention: (this.volume / this.restVolume) * 100,
      volumeError: Math.abs(1 - this.volume / this.restVolume) * 100,
      vertexError,
      velocityRms,
      maxSpeed,
      residual,
      iterations: this.iterations,
      strain: this.strainActual,
    };
  }
}

export const VALIDATION_ITERATIONS = [1, 2, 4, 8, 16, 32, 64];

function average(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function snapshotPoints(mode, iterations, seed, options) {
  const simulation = new SoftBody({
    mode,
    strain: options.strain,
    iterations,
    collision: false,
    instant: true,
    seed,
    grid: options.grid,
    stiffness: options.stiffness,
    volumeStiffness: options.volumeStiffness,
    shapeStiffness: options.shapeStiffness,
  });
  simulation.step(1 / 60, 2);
  return simulation.points;
}

function convergenceError(points, reference) {
  let sum = 0;
  for (let index = 0; index < points.length; index += 1) {
    const a = points[index];
    const b = reference[index];
    sum += (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2;
  }
  return Math.sqrt(sum / points.length) * MM_PER_UNIT;
}

function runCase(mode, iterations, seed, options, reference) {
  const simulation = new SoftBody({
    mode,
    strain: options.strain,
    iterations,
    collision: false,
    instant: true,
    seed,
    grid: options.grid,
    stiffness: options.stiffness,
    volumeStiffness: options.volumeStiffness,
    shapeStiffness: options.shapeStiffness,
  });
  let jitter = 0;
  for (let step = 0; step < options.steps; step += 1) {
    simulation.step(1 / 60, 2);
    if (step < options.observeSteps) {
      jitter = Math.max(jitter, simulation.measure().velocityRms);
    }
  }
  const metrics = simulation.measure();
  const snapshot = snapshotPoints(mode, iterations, seed, options);
  return {
    iterations,
    mode,
    seed,
    volumeRetention: metrics.volumeRetention,
    volumeError: metrics.volumeError,
    vertexError: metrics.vertexError,
    convergence: convergenceError(snapshot, reference),
    jitter,
    residual: metrics.residual,
  };
}

export function validateSoftBody(options = {}) {
  const config = {
    iterations: options.iterations ?? VALIDATION_ITERATIONS,
    repeats: options.repeats ?? 3,
    steps: options.steps ?? 60,
    observeSteps: options.observeSteps ?? 42,
    strain: options.strain ?? 0.18,
    stiffness: options.stiffness ?? 0.82,
    volumeStiffness: options.volumeStiffness ?? 0.75,
    shapeStiffness: options.shapeStiffness ?? 0.012,
    grid: options.grid ?? 4,
  };
  const references = new Map();
  for (const mode of ["compress", "stretch"]) {
    for (let repeat = 0; repeat < config.repeats; repeat += 1) {
      references.set(`${mode}-${repeat}`, snapshotPoints(mode, 64, repeat + 1, config));
    }
  }
  const cases = [];
  for (const iterations of config.iterations) {
    for (const mode of ["compress", "stretch"]) {
      for (let repeat = 0; repeat < config.repeats; repeat += 1) {
        const reference = references.get(`${mode}-${repeat}`);
        const result = runCase(mode, iterations, repeat + 1, config, reference);
        cases.push({ ...result, repeat });
      }
    }
  }

  const byIteration = config.iterations.map((iterations) => {
    const compression = cases.filter((c) => c.iterations === iterations && c.mode === "compress");
    const stretching = cases.filter((c) => c.iterations === iterations && c.mode === "stretch");
    const compressVolume = average(compression.map((c) => c.volumeRetention));
    const stretchVolume = average(stretching.map((c) => c.volumeRetention));
    const vertexError = average(cases.filter((c) => c.iterations === iterations).map((c) => c.convergence));
    const shapeError = average(cases.filter((c) => c.iterations === iterations).map((c) => c.vertexError));
    const jitter = average([
      ...compression.map((c) => c.jitter),
      ...stretching.map((c) => c.jitter),
    ]);
    const volumeError = average([
      ...compression.map((c) => c.volumeError),
      ...stretching.map((c) => c.volumeError),
    ]);
    const residual = average(cases.filter((c) => c.iterations === iterations).map((c) => c.residual));
    const stability = clamp(100 - jitter * 6 - volumeError * 4 - vertexError * 3, 0, 100);
    return {
      iterations,
      compressVolume,
      stretchVolume,
      vertexError,
      shapeError,
      jitter,
      residual,
      volumeError,
      stability,
      stable: stability >= 85 && volumeError < 1.5,
    };
  });
  const first = byIteration[0];
  const last = byIteration[byIteration.length - 1];
  return {
    cases,
    byIteration,
    summary: {
      repeats: config.repeats,
      caseCount: cases.length,
      firstIteration: first.iterations,
      lastIteration: last.iterations,
      jitterReduction: (1 - last.jitter / first.jitter) * 100,
      maxCompressVolumeError: Math.max(...byIteration.map((r) => Math.abs(r.compressVolume - 100))),
      maxStretchVolumeError: Math.max(...byIteration.map((r) => Math.abs(r.stretchVolume - 100))),
      maxEnergy: last.stability,
      stableAt: byIteration.find((r) => r.stable)?.iterations ?? null,
    },
  };
}

export function measureSimulation(iterations, mode, strain, collision, stiffness = 0.82, steps = 36) {
  const simulation = new SoftBody({
    iterations,
    mode,
    strain,
    collision,
    stiffness,
    instant: true,
    seed: 1,
    grid: GRID_N,
    volumeStiffness: 0.75,
  });
  let peakJitter = 0;
  for (let step = 0; step < steps; step += 1) {
    simulation.step(1 / 60, 2);
    if (step < 24) peakJitter = Math.max(peakJitter, simulation.measure().velocityRms);
  }
  return { simulation, metrics: simulation.measure(), peakJitter };
}

export { HEIGHT, WIDTH, DEPTH, REST_VOLUME, MM_PER_UNIT };
