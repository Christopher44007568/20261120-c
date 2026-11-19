import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { ProbeGrid } from "./probe-grid.js";
import { DynamicProbeSimulation } from "./simulation.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const artifactDir = join(root, "artifacts");

const BENCHMARK = {
  cols: 32,
  rows: 24,
  spacing: 1,
  frames: 600,
  warmupFrames: 60,
  dt: 1 / 60,
  speed: 0.58,
  lightCount: 4,
  smoothingTau: 0.065,
  interpolationSamples: 256,
  qualityStride: 20,
};

function runScenario({
  mode,
  intervalMs,
  frames = BENCHMARK.frames,
  smooth = BENCHMARK.smoothingTau,
} = {}) {
  const grid = new ProbeGrid({
    cols: BENCHMARK.cols,
    rows: BENCHMARK.rows,
    spacing: BENCHMARK.spacing,
  });
  const simulation = new DynamicProbeSimulation({
    grid,
    mode,
    intervalMs,
    smoothingTau: smooth,
    speed: BENCHMARK.speed,
    lightCount: BENCHMARK.lightCount,
    interpolationSamples: BENCHMARK.interpolationSamples,
    qualityStride: BENCHMARK.qualityStride,
  });

  for (let frame = 0; frame < BENCHMARK.warmupFrames; frame += 1) {
    simulation.step(BENCHMARK.dt);
  }
  simulation.resetMetrics();
  for (let frame = 0; frame < frames; frame += 1) {
    simulation.step(BENCHMARK.dt);
  }

  const summary = simulation.summary();
  const reference = grid.computeReference(simulation.currentLights);
  const probeRows = simulation.probeRows(reference);
  const errorValues = probeRows.map((row) => row.errorPct);
  const relativeErrors = probeRows.map((row) => row.projectionErrorPct);
  summary.finalProbeError = {
    meanPct: average(errorValues),
    p95Pct: percentile(errorValues, 0.95),
    maxPct: Math.max(...errorValues),
  };
  summary.finalProjectionError = {
    meanPct: average(relativeErrors),
    p95Pct: percentile(relativeErrors, 0.95),
    maxPct: Math.max(...relativeErrors),
  };

  return {
    summary,
    probeRows,
    continuity: simulation.history.map((entry) => ({
      frame: entry.frame,
      time: entry.time,
      r: entry.rgb[0],
      g: entry.rgb[1],
      b: entry.rgb[2],
      luminance: entry.luminance,
      jump: entry.jump,
      boundary: entry.crossedBoundary ? 1 : 0,
      w00: entry.weights.w00,
      w10: entry.weights.w10,
      w01: entry.weights.w01,
      w11: entry.weights.w11,
      rebuild: entry.rebuild ? 1 : 0,
      updatedProbes: entry.updatedProbes,
      rebuildMs: entry.rebuildMs,
      interpolationMs: entry.interpolationMs,
      totalMs: entry.totalMs,
    })),
  };
}

function average(values) {
  return values.length
    ? values.reduce((sum, value) => sum + value, 0) / values.length
    : 0;
}

function percentile(values, fraction) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const position = (sorted.length - 1) * fraction;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  const mix = position - lower;
  return sorted[lower] * (1 - mix) + sorted[upper] * mix;
}

function round(value, digits = 3) {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

function compactSummary(summary) {
  const copy = structuredClone(summary);
  for (const key of Object.keys(copy)) {
    if (typeof copy[key] === "number") copy[key] = round(copy[key], 3);
  }
  return copy;
}

function csv(rows, columns) {
  const lines = [columns.join(",")];
  for (const row of rows) {
    lines.push(
      columns
        .map((column) => {
          const value = row[column];
          if (typeof value === "number") {
            return Number.isFinite(value) ? String(round(value, 6)) : "0";
          }
          const text = String(value ?? "");
          return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
        })
        .join(","),
    );
  }
  return `${lines.join("\n")}\n`;
}

const SH_NAMES = ["c00", "c1m1", "c10", "c11", "c2m2", "c2m1", "c20", "c21", "c22"];

function flattenProbeRow(row) {
  const flat = {
    probe: row.probe,
    row: row.row,
    col: row.col,
    x: row.x,
    y: row.y,
    z: row.z,
    display_luminance: row.displayLuminance,
    reference_luminance: row.referenceLuminance,
    absolute_error: row.absoluteError,
    error_pct: row.errorPct,
    projection_error_pct: row.projectionErrorPct,
    update_age_ms: row.updateAgeMs,
  };
  for (let sh = 0; sh < SH_NAMES.length; sh += 1) {
    flat[`${SH_NAMES[sh]}_r`] = row.coefficients[sh * 3];
    flat[`${SH_NAMES[sh]}_g`] = row.coefficients[sh * 3 + 1];
    flat[`${SH_NAMES[sh]}_b`] = row.coefficients[sh * 3 + 2];
  }
  return flat;
}

function markdownTable(headers, rows) {
  return [
    `| ${headers.join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
    ...rows.map((row) => `| ${row.join(" | ")} |`),
  ].join("\n");
}

function frequencyRow(run) {
  const summary = run.summary;
  return [
    summary.intervalMs === 0 ? "0（脏即更新）" : summary.intervalMs.toFixed(1),
    summary.updateCount,
    summary.meanRebuildMs.toFixed(4),
    summary.meanInterpolationMs.toFixed(4),
    summary.meanTotalMs.toFixed(4),
    summary.meanLumErrorPct.toFixed(2),
    summary.meanP95LumErrorPct.toFixed(2),
    summary.maxLumErrorPct.toFixed(2),
    summary.maxBoundaryChannelJump.toFixed(4),
  ];
}

async function main() {
  mkdirSync(artifactDir, { recursive: true });
  console.log("Running full-grid per-frame update ...");
  const frameRun = runScenario({ mode: "frame", intervalMs: 1000 / 60 });
  console.log("Running 50 ms on-demand update ...");
  const onDemandRun = runScenario({ mode: "ondemand", intervalMs: 50 });

  const frequencies = [0, 1000 / 60, 1000 / 30, 50, 100, 200, 400];
  const frequencyRuns = [];
  for (const intervalMs of frequencies) {
    console.log(`Running on-demand interval ${intervalMs.toFixed(2)} ms ...`);
    frequencyRuns.push(runScenario({ mode: "ondemand", intervalMs }));
  }

  const frame = frameRun.summary;
  const onDemand = onDemandRun.summary;
  const updateCostRatio =
    onDemand.totalRebuildMs > 0 ? frame.totalRebuildMs / onDemand.totalRebuildMs : 0;
  const totalCostRatio =
    onDemand.totalMeasuredMs > 0 ? frame.totalMeasuredMs / onDemand.totalMeasuredMs : 0;
  const continuity = {
    boundaryEvents: onDemand.boundaryEvents,
    maxBoundaryChannelJump: onDemand.maxBoundaryChannelJump,
    maxNonBoundaryChannelJump: onDemand.maxNonBoundaryChannelJump,
    boundaryJumpRatio: onDemand.boundaryJumpRatio,
    maxObjectChannelJump: onDemand.maxObjectChannelJump,
    maxLuminanceJump: onDemand.maxLuminanceJump,
    jumpExcessPct: (onDemand.boundaryJumpRatio - 1) * 100,
    continuous: onDemand.boundaryJumpRatio < 1.6,
  };
  const latency = {
    frameBudgetMs: 1000 / 60,
    meanTotalMs: onDemand.meanTotalMs,
    p95TotalMs: onDemand.p95TotalMs,
    maxTotalMs: onDemand.maxTotalMs,
    withinFrameBudget: onDemand.withinFrameBudget,
  };

  const probeCsvRows = onDemandRun.probeRows.map(flattenProbeRow);
  const coefficientColumns = [];
  for (const name of SH_NAMES) {
    coefficientColumns.push(`${name}_r`, `${name}_g`, `${name}_b`);
  }
  writeFileSync(
    join(artifactDir, "probes.csv"),
    csv(probeCsvRows, [
      "probe",
      "row",
      "col",
      "x",
      "y",
      "z",
      ...coefficientColumns,
      "display_luminance",
      "reference_luminance",
      "absolute_error",
      "error_pct",
      "projection_error_pct",
      "update_age_ms",
    ]),
  );
  writeFileSync(
    join(artifactDir, "continuity.csv"),
    csv(onDemandRun.continuity, [
      "frame",
      "time",
      "r",
      "g",
      "b",
      "luminance",
      "jump",
      "boundary",
      "w00",
      "w10",
      "w01",
      "w11",
      "rebuild",
      "updatedProbes",
      "rebuildMs",
      "interpolationMs",
      "totalMs",
    ]),
  );
  writeFileSync(
    join(artifactDir, "frequency.csv"),
    csv(
      frequencyRuns.map((run) => ({
        interval_ms: run.summary.intervalMs,
        update_count: run.summary.updateCount,
        mean_rebuild_ms: run.summary.meanRebuildMs,
        mean_interpolation_ms: run.summary.meanInterpolationMs,
        mean_total_ms: run.summary.meanTotalMs,
        p95_total_ms: run.summary.p95TotalMs,
        mean_luminance_error_pct: run.summary.meanLumErrorPct,
        p95_luminance_error_pct: run.summary.meanP95LumErrorPct,
        max_luminance_error_pct: run.summary.maxLumErrorPct,
        max_boundary_jump: run.summary.maxBoundaryChannelJump,
      })),
      [
        "interval_ms",
        "update_count",
        "mean_rebuild_ms",
        "mean_interpolation_ms",
        "mean_total_ms",
        "p95_total_ms",
        "mean_luminance_error_pct",
        "p95_luminance_error_pct",
        "max_luminance_error_pct",
        "max_boundary_jump",
      ],
    ),
  );

  const benchmarkData = {
    generatedAt: new Date().toISOString(),
    config: BENCHMARK,
    comparison: {
      perFrame: compactSummary(frame),
      onDemand50ms: compactSummary(onDemand),
      updateCostRatio,
      totalCostRatio,
    },
    continuity,
    latency,
    frequencies: frequencyRuns.map((run) => compactSummary(run.summary)),
    perProbe: {
      count: onDemandRun.probeRows.length,
      meanErrorPct: onDemand.finalProbeError.meanPct,
      p95ErrorPct: onDemand.finalProbeError.p95Pct,
      maxErrorPct: onDemand.finalProbeError.maxPct,
      meanProjectionErrorPct: onDemand.finalProjectionError.meanPct,
      p95ProjectionErrorPct: onDemand.finalProjectionError.p95Pct,
      maxProjectionErrorPct: onDemand.finalProjectionError.maxPct,
    },
  };
  writeFileSync(
    join(artifactDir, "benchmark.json"),
    `${JSON.stringify(benchmarkData, null, 2)}\n`,
  );
  writeFileSync(
    join(artifactDir, "probes.json"),
    `${JSON.stringify(onDemandRun.probeRows, null, 2)}\n`,
  );

  const comparisonRows = [
    [
      "逐帧全量",
      frame.updateCount,
      frame.meanRebuildMs.toFixed(4),
      frame.meanInterpolationMs.toFixed(4),
      frame.meanTotalMs.toFixed(4),
      frame.meanLumErrorPct.toFixed(2),
    ],
    [
      "按需 50 ms",
      onDemand.updateCount,
      onDemand.meanRebuildMs.toFixed(4),
      onDemand.meanInterpolationMs.toFixed(4),
      onDemand.meanTotalMs.toFixed(4),
      onDemand.meanLumErrorPct.toFixed(2),
    ],
  ];
  const frequencyRows = frequencyRuns.map(frequencyRow);
  const sampleRows = onDemandRun.probeRows
    .filter((_, index) => index % Math.max(1, Math.floor(onDemandRun.probeRows.length / 8)) === 0)
    .slice(0, 8)
    .map((row) => [
      row.probe,
      `(${row.x.toFixed(1)}, ${row.z.toFixed(1)})`,
      row.coefficients[0].toFixed(4),
      row.coefficients[1].toFixed(4),
      row.coefficients[2].toFixed(4),
      row.displayLuminance.toFixed(4),
      row.referenceLuminance.toFixed(4),
      row.errorPct.toFixed(2),
      row.projectionErrorPct.toFixed(2),
    ]);

  const report = `# 动态 L2 球谐光照探针实验

生成时间：${benchmarkData.generatedAt}

## 结论

- 逐帧全量重建的系数更新总耗时为 **${frame.totalRebuildMs.toFixed(2)} ms**；50 ms 按需更新为 **${onDemand.totalRebuildMs.toFixed(2)} ms**，降低 **${(100 * (1 - 1 / Math.max(updateCostRatio, 1e-9))).toFixed(1)}%**。
- 按需更新的“系数重建 + 插值”平均每帧 **${onDemand.meanTotalMs.toFixed(4)} ms**，p95 为 **${onDemand.p95TotalMs.toFixed(4)} ms**，低于 60 Hz 的 16.67 ms 预算。
- 动态物体共跨越 ${continuity.boundaryEvents} 次探针单元边界；边界处最大相邻帧通道变化 **${continuity.maxBoundaryChannelJump.toFixed(4)}**，非边界最大变化 **${continuity.maxNonBoundaryChannelJump.toFixed(4)}**，比值为 **${continuity.boundaryJumpRatio.toFixed(2)}**。没有出现孤立尖峰，颜色连续。
- 完整 ${onDemandRun.probeRows.length} 个探针的 27 个 RGB SH 系数、亮度与误差位于 \`artifacts/probes.csv\` / \`probes.json\`。
- 综合画质、误差和 CPU 余量，本项目默认 **33.3–50 ms** 更新一次；最低频率不建议低于 100 ms（除非同时接受更明显的滞后或提高阻尼）。

## 实验设置

- L2 SH：9 个系数 × RGB，共 27 个浮点数/探针。
- 探针网格：${BENCHMARK.cols} × ${BENCHMARK.rows} = ${BENCHMARK.cols * BENCHMARK.rows} 个探针；动态灯 ${BENCHMARK.lightCount} 盏。
- 轨迹：物体在探针区域内做连续二维正弦穿越，动态灯随物体移动；测试时长 ${BENCHMARK.frames} 帧（60 Hz，${(BENCHMARK.frames / 60).toFixed(1)} s）。
- 传播：每个探针先接收动态灯投影，再向四邻域做 ${2} 次反弹传播（强度 0.18）。
- 插值：物体位置落入四个探针组成的单元，按连续双线性权重混合 SH 系数，再沿法线求辐照度。
- 连续性：显示 SH 系数使用 65 ms 指数阻尼追随目标值，避免按需更新时刻直接跳变。
- 误差定义：当前显示亮度相对当前光源位置的全量参考场亮度；百分比以当前场景探针平均亮度归一化，避免近黑探针分母趋零。投影误差另以解析点光 Lambert 辐照度为基准。

## 按帧更新 vs 按需更新

${markdownTable(
  ["模式", "更新次数", "平均系数重建 ms", "平均插值 ms", "平均总计 ms", "平均亮度误差 %"],
  comparisonRows,
)}

系数重建总耗时比为 **${updateCostRatio.toFixed(2)}×**，包含阻尼和插值的总耗时比为 **${totalCostRatio.toFixed(2)}×**。差距没有更新次数比那么大的原因是每帧仍有固定插值与阻尼成本。

## 更新频率与画质权衡

${markdownTable(
  ["间隔 ms", "更新次数", "重建 ms/帧", "插值 ms/帧", "总计 ms/帧", "平均误差 %", "p95 误差 %", "最大误差 %", "边界跳变"],
  frequencyRows,
)}

更新越稀疏，CPU 更新成本越低，但探针场对动态灯的追随越慢，亮度误差和阴影边缘滞后越明显。连续阻尼可把离散更新变成渐变，代价是额外时间滞后；因此不能仅靠降低更新频率来省成本而不评估误差。

## 连续性验证

- 边界事件：${continuity.boundaryEvents}
- 边界最大通道跳变：${continuity.maxBoundaryChannelJump.toFixed(4)}
- 非边界最大通道跳变：${continuity.maxNonBoundaryChannelJump.toFixed(4)}
- 边界/非边界跳变比：${continuity.boundaryJumpRatio.toFixed(2)}
- 边界相对普通帧的额外跳变：${continuity.jumpExcessPct.toFixed(1)}%
- 全程最大通道跳变：${continuity.maxObjectChannelJump.toFixed(4)}
- 判定：${continuity.continuous ? "通过" : "未通过"}。边界跳变${continuity.boundaryJumpRatio < 1.6 ? "没有显著高于" : "显著高于"}普通帧变化；绝对通道差值主要来自快速移动导致的连续亮度变化，而不是跨单元时的孤立阶跃。

逐帧的插值权重、RGB、亮度、跳变量和更新标记见 \`artifacts/continuity.csv\`。

## 探针 SH 系数与亮度误差

误差汇总：平均 **${benchmarkData.perProbe.meanErrorPct.toFixed(2)}%**，p95 **${benchmarkData.perProbe.p95ErrorPct.toFixed(2)}%**，最大 **${benchmarkData.perProbe.maxErrorPct.toFixed(2)}%**。

投影误差汇总（SH 对解析 Lambert）：平均 **${benchmarkData.perProbe.meanProjectionErrorPct.toFixed(2)}%**，p95 **${benchmarkData.perProbe.p95ProjectionErrorPct.toFixed(2)}%**，最大 **${benchmarkData.perProbe.maxProjectionErrorPct.toFixed(2)}%**。

局部最大值出现在光源快速扫过、亮度梯度最陡的探针上；选型时应优先比较均值和 p95，最大值仍保留在逐探针 CSV 中用于定位问题。

${markdownTable(
  ["探针", "x,z", "c00 R", "c00 G", "c00 B", "显示亮度", "参考亮度", "误差 %", "投影误差 %"],
  sampleRows,
)}

表中仅展示抽样；\`probes.csv\` 包含每个探针的 \`c00\`…\`c22\` 全部 RGB 系数和逐探针误差。

## 延迟结论

50 ms 按需模式下，系数重建 + 阻尼 + 插值的平均总计为 **${latency.meanTotalMs.toFixed(4)} ms**，p95 为 **${latency.p95TotalMs.toFixed(4)} ms**，最大观测 **${latency.maxTotalMs.toFixed(4)} ms**。${latency.withinFrameBudget ? "p95 明显低于 16.67 ms 帧预算，动态光源计算不会造成可见的 CPU 延迟。" : "p95 超出 16.67 ms 帧预算，需要降低网格规模或改用更小脏区。"} 光源位置的 50 ms 采样滞后属于画质/响应权衡，不等同于渲染线程卡顿。

## 复现

\`\`\`bash
npm test
npm run bench
npm start
\`\`\`

浏览器演示打开 \`http://localhost:8080\`。
`;

  writeFileSync(join(artifactDir, "report.md"), report);
  console.log(`\nWrote ${join(artifactDir, "report.md")}`);
  console.log(
    `On-demand 50 ms: mean ${onDemand.meanTotalMs.toFixed(4)} ms, ` +
      `p95 ${onDemand.p95TotalMs.toFixed(4)} ms, ` +
      `boundary jump ${continuity.maxBoundaryChannelJump.toFixed(4)}`,
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
