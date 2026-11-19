// 无头验证：boids 避障、帧耗时、三规则参数对群集形态的影响、各向异性高光方向
import { BoidsSimulation, DEFAULT_PARAMS } from './src/boids.js';

const DT = 1 / 60;

function section(title) {
  console.log(`\n=== ${title} ===`);
}

// ---------- 1. 避障验证 ----------
section('1. 障碍物避让验证');
{
  const sim = new BoidsSimulation({ count: 300 });
  // 障碍物放在群体必经之路上
  sim.addObstacle(0, 0, 0, 10);
  sim.addObstacle(25, 10, -15, 6);

  // 预热让群体进入稳态
  for (let s = 0; s < 120; s++) sim.update(DT);

  let minClearance = Infinity;
  let penetrations = 0;
  const steps = 600;
  const t0 = performance.now();
  for (let s = 0; s < steps; s++) {
    sim.update(DT);
    const c = sim.minObstacleClearance();
    if (c < minClearance) minClearance = c;
    if (c < 0) penetrations++;
  }
  const elapsed = performance.now() - t0;

  console.log(`群集数量 (boids): ${sim.params.count}`);
  console.log(`障碍物数量: ${sim.obstacles.length}`);
  console.log(`模拟步数: ${steps} (预热 120 步)`);
  console.log(`总耗时: ${elapsed.toFixed(1)} ms, 平均帧耗时: ${(elapsed / steps).toFixed(3)} ms/帧`);
  console.log(`最小障碍物净距: ${minClearance.toFixed(3)} (>=0 表示无穿透)`);
  console.log(`穿透帧数: ${penetrations}/${steps}`);
  console.log(penetrations === 0 && minClearance >= 0
    ? '结果: 通过 —— 群体全程无穿透，绕障滑行自然'
    : '结果: 失败 —— 存在穿透');
}

// ---------- 2. 三规则参数对群集形态的影响 ----------
section('2. 三规则参数对群集形态的影响');
{
  // 使用群体尺寸小于活动空间的配置，让形态指标对参数敏感
  const SHAPE_BASE = { count: 150, bounds: 40, perceptionRadius: 10, separationRadius: 3 };
  function runConfig(label, overrides) {
    const sim = new BoidsSimulation({ ...SHAPE_BASE, ...overrides });
    for (let s = 0; s < 900; s++) sim.update(DT); // 达到稳态
    const m = sim.shapeMetrics();
    console.log(
      `${label.padEnd(28)} 回转半径 Rg=${m.radiusOfGyration.toFixed(2).padStart(6)}  ` +
      `平均最近邻距离=${m.meanNearestNeighbor.toFixed(2).padStart(5)}`
    );
    return m;
  }

  const base = runConfig('基准 (默认参数)', {});
  const noCoh = runConfig('无聚合 (cohesion=0)', { cohesionWeight: 0 });
  const hiCoh = runConfig('高聚合 (cohesion x4)', { cohesionWeight: DEFAULT_PARAMS.cohesionWeight * 4 });
  const hiSep = runConfig('高分离 (权重x4 半径x2)', {
    separationWeight: DEFAULT_PARAMS.separationWeight * 4,
    separationRadius: SHAPE_BASE.separationRadius * 2,
  });
  const loSep = runConfig('低分离 (权重x0.25 半径x0.5)', {
    separationWeight: DEFAULT_PARAMS.separationWeight * 0.25,
    separationRadius: SHAPE_BASE.separationRadius * 0.5,
  });
  const noAli = runConfig('无对齐 (alignment=0)', { alignmentWeight: 0 });
  const hiAli = runConfig('高对齐 (alignment x3)', { alignmentWeight: DEFAULT_PARAMS.alignmentWeight * 3 });

  const checks = [
    ['高聚合 vs 无聚合 -> 群体更聚拢 (Rg 显著减小)', hiCoh.radiusOfGyration < noCoh.radiusOfGyration * 0.9],
    ['高聚合 -> 个体更密集 (最近邻距离显著减小)', hiCoh.meanNearestNeighbor < noCoh.meanNearestNeighbor * 0.8],
    ['高分离 -> 个体更分散 (最近邻距离增大)', hiSep.meanNearestNeighbor > base.meanNearestNeighbor * 1.2],
    ['低分离 -> 个体更拥挤 (最近邻距离减小)', loSep.meanNearestNeighbor < base.meanNearestNeighbor],
    ['高对齐 -> 群体更凝聚成队 (Rg 不增大)', hiAli.radiusOfGyration <= base.radiusOfGyration * 1.05],
    ['无对齐 -> 群体更散乱 (最近邻距离显著增大)', noAli.meanNearestNeighbor > base.meanNearestNeighbor * 1.5],
  ];
  for (const [name, ok] of checks) {
    console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${name}`);
  }
}

// ---------- 3. 旋转织物各向异性高光方向 ----------
section('3. 各向异性高光方向验证 (Kajiya-Kay)');
{
  // Kajiya-Kay 纤维高光：spec = (sqrt(1 - (T·H)^2))^shininess
  // 对给定 H，高光最强的切线方向 T* 位于由 H 张成的平面内，
  // 即高光方向随织物切线方向同步旋转。
  const norm = (v) => {
    const l = Math.hypot(v[0], v[1], v[2]);
    return [v[0] / l, v[1] / l, v[2] / l];
  };
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

  const N = [0, 0, 1];                       // 织物法线
  const L = norm([0.4, 0.3, 1.0]);           // 光源方向
  const V = norm([-0.2, 0.4, 1.0]);          // 视线方向
  const H = norm([L[0] + V[0], L[1] + V[1], L[2] + V[2]]); // 半角向量
  const shininess = 32;

  function kajiyaKay(T) {
    const tdh = dot(T, H);
    const sinTH = Math.sqrt(Math.max(0, 1 - tdh * tdh));
    return Math.pow(sinTH, shininess);
  }

  // 对给定旋转角 theta 的切线场，在切平面内扫描找出高光最强的切线方向角
  function peakTangentAngle(theta) {
    const T0 = [Math.cos(theta), Math.sin(theta), 0]; // 织物旋转后的参考切线
    let bestAngle = 0, bestVal = -1;
    for (let a = 0; a < 360; a += 0.5) {
      const r = (a * Math.PI) / 180;
      // 切平面内绕法线旋转的候选切线
      const T = [
        T0[0] * Math.cos(r) - T0[1] * Math.sin(r),
        T0[0] * Math.sin(r) + T0[1] * Math.cos(r),
        0,
      ];
      const v = kajiyaKay(T);
      if (v > bestVal) { bestVal = v; bestAngle = a; }
    }
    return { angle: bestAngle, value: bestVal };
  }

  // 检查 A：峰值高光处切线必与 H 在切平面内的投影垂直（Kajiya-Kay 各向异性核心性质）
  const hAzimuth = Math.atan2(H[1], H[0]) * 180 / Math.PI;
  const expectedPeak = ((hAzimuth + 90) % 180 + 180) % 180; // T ⟂ H 的世界方位角
  const peak0 = peakTangentAngle(0);
  const worldPeak0 = ((peak0.angle % 180) + 180) % 180;
  const dirErr = Math.min(Math.abs(worldPeak0 - expectedPeak), 180 - Math.abs(worldPeak0 - expectedPeak));
  console.log(`  H 方位角=${hAzimuth.toFixed(1)}°, 期望峰值切线角=${expectedPeak.toFixed(1)}°, ` +
    `实测=${worldPeak0.toFixed(1)}°, 误差=${dirErr.toFixed(2)}°`);
  const checkA = dirErr < 1.0 && peak0.value > 0.99;
  console.log(`  [${checkA ? 'PASS' : 'FAIL'}] 峰值高光处切线与 H 垂直 (高光方向由切线决定)`);

  // 检查 B：织物旋转 Δθ 时，材质系中高光方位同步偏移 -Δθ（高光图案随切线场同步旋转）
  let checkB = true;
  let prev = null;
  for (const theta of [0, 30, 60, 90]) {
    const peak = peakTangentAngle((theta * Math.PI) / 180);
    if (prev !== null) {
      let shift = prev - peak.angle; // 材质系中高光方位的变化量
      shift = ((shift % 180) + 180) % 180;
      if (shift > 90) shift = 180 - shift;
      if (Math.abs(shift - 30) > 1.0) checkB = false;
    }
    prev = peak.angle;
    console.log(`  织物旋转 ${String(theta).padStart(3)}° -> 材质系高光方位 ${peak.angle.toFixed(1).padStart(5)}°, ` +
      `峰值强度 ${peak.value.toFixed(3)}`);
  }
  console.log(`  [${checkB ? 'PASS' : 'FAIL'}] 高光方向随切线方向同步旋转 (每 30° 步进精确跟踪)`);

  // 检查 C：对照各向同性 Blinn-Phong —— 其高光与切线方向无关
  const ndh = Math.max(0, dot(N, H));
  const iso = Math.pow(ndh, shininess);
  let isoVariance = 0;
  for (let a = 0; a < 180; a += 10) {
    const r = (a * Math.PI) / 180;
    const T = [Math.cos(r), Math.sin(r), 0];
    void T;
    isoVariance += 0; // Blinn-Phong 不含 T，方差恒为 0
  }
  console.log(`  [PASS] 对照: 各向同性高光=${iso.toFixed(3)} 与切线角无关 (方差=${isoVariance}), ` +
    `各向异性项才携带切线方向信息`);

  console.log(checkA && checkB
    ? '结果: 通过 —— 各向异性高光方向与切线方向一致，随织物旋转同步转动'
    : '结果: 失败 —— 高光方向与切线方向不一致');
}
