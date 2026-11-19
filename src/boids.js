// Boids 核心模拟：分离 / 对齐 / 聚合 三规则 + 球形障碍物避让
// 同时被浏览器演示 (index.html) 与 Node 验证脚本 (verify.mjs) 复用

export const DEFAULT_PARAMS = {
  count: 300,
  perceptionRadius: 6.0,   // 邻居感知半径
  separationRadius: 2.2,   // 分离作用半径
  separationWeight: 1.6,
  alignmentWeight: 1.0,
  cohesionWeight: 0.9,
  obstacleWeight: 3.0,     // 避障转向强度
  obstacleMargin: 4.0,     // 障碍物表面外的预警距离
  maxSpeed: 12.0,
  minSpeed: 4.0,
  maxForce: 30.0,
  bounds: 60,              // 立方活动空间半边长
  boundsWeight: 1.2,
  seed: 12345,             // 随机种子，保证验证可复现
};

export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class BoidsSimulation {
  constructor(params = {}) {
    this.params = { ...DEFAULT_PARAMS, ...params };
    this._rand = mulberry32(this.params.seed ?? 12345);
    const n = this.params.count;
    this.positions = new Float32Array(n * 3);
    this.velocities = new Float32Array(n * 3);
    this.obstacles = []; // {x, y, z, radius}
    this._grid = new Map();
    this._cellSize = this.params.perceptionRadius;
    this._randomize();
  }

  _randomize() {
    const { count, bounds, maxSpeed } = this.params;
    const rand = this._rand;
    for (let i = 0; i < count; i++) {
      const i3 = i * 3;
      this.positions[i3] = (rand() * 2 - 1) * bounds * 0.6;
      this.positions[i3 + 1] = (rand() * 2 - 1) * bounds * 0.6;
      this.positions[i3 + 2] = (rand() * 2 - 1) * bounds * 0.6;
      const theta = rand() * Math.PI * 2;
      const phi = Math.acos(rand() * 2 - 1);
      const speed = maxSpeed * (0.5 + rand() * 0.5);
      this.velocities[i3] = Math.sin(phi) * Math.cos(theta) * speed;
      this.velocities[i3 + 1] = Math.cos(phi) * speed;
      this.velocities[i3 + 2] = Math.sin(phi) * Math.sin(theta) * speed;
    }
  }

  addObstacle(x, y, z, radius) {
    this.obstacles.push({ x, y, z, radius });
  }

  _rebuildGrid() {
    this._grid.clear();
    const cs = this._cellSize;
    const n = this.params.count;
    for (let i = 0; i < n; i++) {
      const i3 = i * 3;
      const key = this._cellKey(
        Math.floor(this.positions[i3] / cs),
        Math.floor(this.positions[i3 + 1] / cs),
        Math.floor(this.positions[i3 + 2] / cs)
      );
      let cell = this._grid.get(key);
      if (!cell) { cell = []; this._grid.set(key, cell); }
      cell.push(i);
    }
  }

  _cellKey(x, y, z) { return `${x},${y},${z}`; }

  *neighborsOf(i) {
    const cs = this._cellSize;
    const i3 = i * 3;
    const cx = Math.floor(this.positions[i3] / cs);
    const cy = Math.floor(this.positions[i3 + 1] / cs);
    const cz = Math.floor(this.positions[i3 + 2] / cs);
    for (let dx = -1; dx <= 1; dx++)
      for (let dy = -1; dy <= 1; dy++)
        for (let dz = -1; dz <= 1; dz++) {
          const cell = this._grid.get(this._cellKey(cx + dx, cy + dy, cz + dz));
          if (cell) for (const j of cell) if (j !== i) yield j;
        }
  }

  // 单步模拟：三规则求和为转向力，叠加避障与边界力后积分
  update(dt) {
    const p = this.params;
    const n = p.count;
    const pos = this.positions;
    const vel = this.velocities;
    this._rebuildGrid();

    const pr2 = p.perceptionRadius * p.perceptionRadius;
    const sr2 = p.separationRadius * p.separationRadius;

    for (let i = 0; i < n; i++) {
      const i3 = i * 3;
      const px = pos[i3], py = pos[i3 + 1], pz = pos[i3 + 2];
      let sepX = 0, sepY = 0, sepZ = 0;
      let aliX = 0, aliY = 0, aliZ = 0;
      let cohX = 0, cohY = 0, cohZ = 0;
      let count = 0;

      for (const j of this.neighborsOf(i)) {
        const j3 = j * 3;
        const dx = pos[j3] - px, dy = pos[j3 + 1] - py, dz = pos[j3 + 2] - pz;
        const d2 = dx * dx + dy * dy + dz * dz;
        if (d2 > pr2 || d2 === 0) continue;
        count++;
        aliX += vel[j3]; aliY += vel[j3 + 1]; aliZ += vel[j3 + 2];
        cohX += pos[j3]; cohY += pos[j3 + 1]; cohZ += pos[j3 + 2];
        if (d2 < sr2) {
          const inv = 1 / d2; // 距离越近排斥越强
          sepX -= dx * inv; sepY -= dy * inv; sepZ -= dz * inv;
        }
      }

      let fx = 0, fy = 0, fz = 0;
      if (count > 0) {
        const invC = 1 / count;
        // 对齐：趋向邻居平均速度
        fx += (aliX * invC - vel[i3]) * p.alignmentWeight;
        fy += (aliY * invC - vel[i3 + 1]) * p.alignmentWeight;
        fz += (aliZ * invC - vel[i3 + 2]) * p.alignmentWeight;
        // 聚合：趋向邻居质心
        fx += (cohX * invC - px) * p.cohesionWeight * 0.1;
        fy += (cohY * invC - py) * p.cohesionWeight * 0.1;
        fz += (cohZ * invC - pz) * p.cohesionWeight * 0.1;
        // 分离：远离过近邻居
        fx += sepX * p.separationWeight;
        fy += sepY * p.separationWeight;
        fz += sepZ * p.separationWeight;
      }

      // 障碍物避让：进入预警圈后沿径向推离，并附加切向绕行分量
      for (const ob of this.obstacles) {
        const dx = px - ob.x, dy = py - ob.y, dz = pz - ob.z;
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
        const safe = ob.radius + p.obstacleMargin;
        if (dist < safe && dist > 1e-6) {
          const inv = 1 / dist;
          const nx = dx * inv, ny = dy * inv, nz = dz * inv;
          const urgency = (safe - dist) / (safe - ob.radius); // 0..1，越贴近越急
          const push = p.obstacleWeight * urgency * urgency * p.maxForce;
          fx += nx * push; fy += ny * push; fz += nz * push;
          // 切向分量让群体绕障滑行而非正面急停，避让更自然
          const tx = -nz, tz = nx;
          const tl = Math.sqrt(tx * tx + tz * tz);
          if (tl > 1e-6) {
            const side = (vel[i3] * tx + vel[i3 + 2] * tz) >= 0 ? 1 : -1;
            const tang = push * 0.5 * side / tl;
            fx += tx * tang; fz += tz * tang;
          }
        }
      }

      // 软边界：把个体引回活动空间
      const b = p.bounds;
      if (px > b) fx -= (px - b) * p.boundsWeight; else if (px < -b) fx -= (px + b) * p.boundsWeight;
      if (py > b) fy -= (py - b) * p.boundsWeight; else if (py < -b) fy -= (py + b) * p.boundsWeight;
      if (pz > b) fz -= (pz - b) * p.boundsWeight; else if (pz < -b) fz -= (pz + b) * p.boundsWeight;

      // 限制转向力
      const fl = Math.sqrt(fx * fx + fy * fy + fz * fz);
      if (fl > p.maxForce) {
        const s = p.maxForce / fl;
        fx *= s; fy *= s; fz *= s;
      }

      vel[i3] += fx * dt;
      vel[i3 + 1] += fy * dt;
      vel[i3 + 2] += fz * dt;

      // 限制速度在 [minSpeed, maxSpeed]
      const vx = vel[i3], vy = vel[i3 + 1], vz = vel[i3 + 2];
      const sp = Math.sqrt(vx * vx + vy * vy + vz * vz);
      if (sp > p.maxSpeed) {
        const s = p.maxSpeed / sp;
        vel[i3] *= s; vel[i3 + 1] *= s; vel[i3 + 2] *= s;
      } else if (sp < p.minSpeed && sp > 1e-6) {
        const s = p.minSpeed / sp;
        vel[i3] *= s; vel[i3 + 1] *= s; vel[i3 + 2] *= s;
      }
    }

    for (let i = 0; i < n * 3; i++) pos[i] += vel[i] * dt;
  }

  // 每个体到最近障碍物表面的最小距离（负值表示穿透）
  minObstacleClearance() {
    let min = Infinity;
    const pos = this.positions;
    for (let i = 0; i < this.params.count; i++) {
      const i3 = i * 3;
      for (const ob of this.obstacles) {
        const dx = pos[i3] - ob.x, dy = pos[i3 + 1] - ob.y, dz = pos[i3 + 2] - ob.z;
        const c = Math.sqrt(dx * dx + dy * dy + dz * dz) - ob.radius;
        if (c < min) min = c;
      }
    }
    return min;
  }

  // 群体形态指标：回转半径（聚集程度）与平均最近邻距离（分散程度）
  shapeMetrics() {
    const n = this.params.count;
    const pos = this.positions;
    let cx = 0, cy = 0, cz = 0;
    for (let i = 0; i < n; i++) {
      cx += pos[i * 3]; cy += pos[i * 3 + 1]; cz += pos[i * 3 + 2];
    }
    cx /= n; cy /= n; cz /= n;
    let rg = 0;
    for (let i = 0; i < n; i++) {
      const dx = pos[i * 3] - cx, dy = pos[i * 3 + 1] - cy, dz = pos[i * 3 + 2] - cz;
      rg += dx * dx + dy * dy + dz * dz;
    }
    rg = Math.sqrt(rg / n);
    let nnSum = 0;
    for (let i = 0; i < n; i++) {
      let best = Infinity;
      for (let j = 0; j < n; j++) {
        if (j === i) continue;
        const dx = pos[j * 3] - pos[i * 3];
        const dy = pos[j * 3 + 1] - pos[i * 3 + 1];
        const dz = pos[j * 3 + 2] - pos[i * 3 + 2];
        const d2 = dx * dx + dy * dy + dz * dz;
        if (d2 < best) best = d2;
      }
      nnSum += Math.sqrt(best);
    }
    return { radiusOfGyration: rg, meanNearestNeighbor: nnSum / n };
  }
}
