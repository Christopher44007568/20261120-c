import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  ATMOSPHERE,
  DEFAULT_PARAMS,
  cloudOpticalDepth,
  cloudProfile,
  cloudShadowFraction,
  colorDistance,
  directIlluminance,
  luminance,
  rgbToHex,
  skyColor,
  skyRadiance,
  sunColor,
  sunDirection,
  sunTransmittance
} from '../src/atmosphere.js';
import { cloudShadowSvg, elevationStripSvg, scatteringCurveSvg } from './report-svg.mjs';

const artifacts = resolve('artifacts');
mkdirSync(artifacts, { recursive: true });
const generatedAt = new Date().toISOString();
const selectedElevations = [-6, -3, 0, 2, 6, 14, 30, 45, 62, 75, 90];
const params = { ...DEFAULT_PARAMS };
const hex = (rgb) => rgbToHex(rgb).toUpperCase();
const directionObject = (direction) => ({
  x: direction.x,
  y: direction.y,
  z: direction.z
});

function rowFor(elevation) {
  const direction = sunDirection(elevation, params.sunAzimuth);
  const zenith = skyColor(89.5, elevation, params);
  const horizon = skyColor(0.8, elevation, params);
  const solar = sunColor(elevation, params.rayleighScale, params.mieScale);
  const transmittance = luminance(sunTransmittance(
    elevation, params.rayleighScale, params.mieScale
  ));
  return {
    elevation,
    sunDirection: directionObject(direction),
    sun: hex(solar),
    solar,
    zenith,
    horizon,
    zenithHex: hex(zenith),
    horizonHex: hex(horizon),
    transmittance,
    illuminance: directIlluminance(elevation, params.rayleighScale, params.mieScale)
  };
}

const rows = [];
for (let elevation = -6; elevation <= 90.0001; elevation += 0.25) {
  const rounded = Math.round(elevation * 100) / 100;
  rows.push(rowFor(rounded));
}

let maxAdjacentDelta = 0;
let maxAdjacentAt = -6;
for (let index = 1; index < rows.length; index += 1) {
  const delta = Math.max(
    colorDistance(rows[index - 1].zenith, rows[index].zenith),
    colorDistance(rows[index - 1].horizon, rows[index].horizon)
  );
  if (delta > maxAdjacentDelta) {
    maxAdjacentDelta = delta;
    maxAdjacentAt = rows[index].elevation;
  }
}

const transitionSamples = selectedElevations.map((elevation) => {
  let maximum = 0;
  let maximumAt = 0.8;
  let previous = null;
  for (let viewElevation = 0.8; viewElevation <= 45.0001; viewElevation += 0.5) {
    const color = skyColor(viewElevation, elevation, params);
    if (previous) {
      const delta = colorDistance(previous, color);
      if (delta > maximum) {
        maximum = delta;
        maximumAt = viewElevation;
      }
    }
    previous = color;
  }
  return { elevation, maxDelta: maximum, maxDeltaAt: maximumAt };
});

const selectedRows = selectedElevations.map(rowFor);
const noon = rowFor(90);
const sunset = rowFor(2);
const zenithBlueDominant = noon.zenith[2] > noon.zenith[0];
const sunsetHorizonWarmer = (sunset.horizon[0] - sunset.horizon[2]) >
  (noon.horizon[0] - noon.horizon[2]);
const horizonBrighter = luminance(sunset.horizon) > luminance(sunset.zenith);
const maxTransition = Math.max(...transitionSamples.map((row) => row.maxDelta));

const scatteringSeries = [];
let maxDiffuseRadiance = 0;
for (let i = 0; i < 29; i += 1) {
  const scale = Math.round((0.2 + i * 0.1) * 100) / 100;
  const direct = luminance(sunTransmittance(14, scale, params.mieScale));
  const diffuseRadiance = luminance(skyRadiance(
    89.5, params.sunAzimuth, 14, { ...params, rayleighScale: scale }
  ));
  maxDiffuseRadiance = Math.max(maxDiffuseRadiance, diffuseRadiance);
  scatteringSeries.push({ scale, direct, diffuseRadiance });
}
for (const point of scatteringSeries) {
  point.diffuse = point.diffuseRadiance / maxDiffuseRadiance;
}
const directFalls = scatteringSeries.every((point, index) =>
  index === 0 || point.direct < scatteringSeries[index - 1].direct
);
const diffuseRises = scatteringSeries.every((point, index) =>
  index === 0 || point.diffuse > scatteringSeries[index - 1].diffuse
);

const cloudRows = [];
for (const coverage of [0.1, 0.25, 0.5, 0.75, 1]) {
  for (const thickness of [0.5, 1.5, 3]) {
    cloudRows.push({
      coverage,
      coveragePercent: coverage * 100,
      thickness,
      top: ATMOSPHERE.cloudBaseKm + thickness,
      opticalDepth: cloudOpticalDepth(coverage, thickness),
      shadowFraction: cloudShadowFraction(coverage, thickness),
      shadowPercent: cloudShadowFraction(coverage, thickness) * 100
    });
  }
}
const coverageGroups = [0.5, 1.5, 3].every((thickness) => {
  const subset = cloudRows.filter((row) => row.thickness === thickness);
  return subset.every((row, index) =>
    index === 0 || row.shadowFraction >= subset[index - 1].shadowFraction
  );
});
const thicknessGroups = [0.1, 0.25, 0.5, 0.75, 1].every((coverage) => {
  const subset = cloudRows.filter((row) => row.coverage === coverage);
  return subset.every((row, index) =>
    index === 0 || row.shadowFraction > subset[index - 1].shadowFraction
  );
});
const cloudShadowGrows = coverageGroups && thicknessGroups;
const defaultCloud = cloudShadowSvg(cloudRows);
const currentCloud = cloudProfile(params);

const report = {
  generatedAt,
  model: {
    type: 'single-scattering atmosphere + volumetric clouds',
    betaRayleighKm: ATMOSPHERE.betaRayleighKm,
    betaMieKm: ATMOSPHERE.betaMieKm,
    rayleighScaleHeightKm: ATMOSPHERE.rayleighScaleHeightKm,
    mieScaleHeightKm: ATMOSPHERE.mieScaleHeightKm,
    observerAltitudeKm: ATMOSPHERE.observerAltitudeKm,
    cloudBaseKm: ATMOSPHERE.cloudBaseKm,
    sunIlluminanceLux: ATMOSPHERE.sunIlluminanceLux
  },
  params,
  validation: {
    summary: {
      zenithBlueDominant,
      sunsetHorizonWarmer,
      maxAdjacentDelta: maxAdjacentDelta,
      maxAdjacentAt,
      colorContinuity: maxAdjacentDelta < 0.2,
      horizonBrighterThanZenith: horizonBrighter,
      transitionNatural: maxTransition < 0.06,
      maxTransitionDelta: maxTransition,
      directFallsWithScattering: directFalls,
      diffuseRisesWithScattering: diffuseRises,
      cloudShadowGrows
    },
    noon: {
      zenithHex: noon.zenithHex,
      horizonHex: noon.horizonHex,
      directIlluminance: noon.illuminance
    },
    sunset: {
      sunHex: sunset.sun,
      horizonHex: sunset.horizonHex,
      transmittance: sunset.transmittance,
      directIlluminance: sunset.illuminance
    },
    selectedElevations: selectedRows,
    continuity: { step: 0.25, maxAdjacentDelta, maxAdjacentAt },
    transitionSamples,
    scatteringSeries,
    cloudRows
  }
};

writeFileSync(resolve(artifacts, 'atmosphere-validation.json'),
  `${JSON.stringify(report, null, 2)}\n`);

const csv = [
  'elevation_deg,sun_x,sun_y,sun_z,sun_hex,zenith_hex,horizon_hex,transmitted_fraction,direct_illuminance_lux',
  ...selectedRows.map((row) => [
    row.elevation,
    row.sunDirection.x.toFixed(5),
    row.sunDirection.y.toFixed(5),
    row.sunDirection.z.toFixed(5),
    row.sun,
    row.zenithHex,
    row.horizonHex,
    row.transmittance.toFixed(5),
    row.illuminance.toFixed(2)
  ].join(','))
].join('\n');
writeFileSync(resolve(artifacts, 'elevation-sweep.csv'), `${csv}\n`);
writeFileSync(resolve(artifacts, 'elevation-strip.svg'), elevationStripSvg(rows));
writeFileSync(resolve(artifacts, 'scattering-curve.svg'), scatteringCurveSvg(scatteringSeries));
writeFileSync(resolve(artifacts, 'cloud-shadow.svg'), defaultCloud);

const selectedTable = selectedRows.map((row) =>
  `| ${row.elevation.toFixed(1)}° | ${row.sunDirection.x.toFixed(3)}, ${row.sunDirection.y.toFixed(3)}, ${row.sunDirection.z.toFixed(3)} | ${row.sun} | ${row.zenithHex} | ${row.horizonHex} | ${(row.transmittance * 100).toFixed(1)}% | ${Math.round(row.illuminance).toLocaleString('en-US')} lx |`
).join('\n');

const transitionTable = transitionSamples.map((row) =>
  `| ${row.elevation}° | ${row.maxDelta.toFixed(4)} | ${row.maxDeltaAt.toFixed(1)}° |`
).join('\n');

const scatteringTable = [0.2, 0.6, 1, 1.4, 1.8, 2.2, 2.6, 3]
  .map((scale) => scatteringSeries.find((point) => Math.abs(point.scale - scale) < 0.001))
  .filter(Boolean)
  .map((row) =>
    `| ${row.scale.toFixed(1)}× | ${row.direct.toFixed(4)} | ${row.diffuse.toFixed(4)} | ${(row.direct * ATMOSPHERE.sunIlluminanceLux * Math.sin(14 * Math.PI / 180) / 1000).toFixed(1)} klx |`
  ).join('\n');

const cloudTable = cloudRows.map((row) =>
  `| ${row.coveragePercent.toFixed(0)}% | ${row.thickness.toFixed(1)} km | ${row.top.toFixed(2)} km | ${row.opticalDepth.toFixed(2)} | ${row.shadowPercent.toFixed(1)}% |`
).join('\n');

const reportMarkdown = `# 大气散射验证报告

生成时间：${generatedAt}

## 模型

- 瑞利散射系数：βR = (${ATMOSPHERE.betaRayleighKm.map((value) => value.toFixed(4)).join(', ')}) km⁻¹
- 米氏散射系数：βM = ${ATMOSPHERE.betaMieKm.toFixed(3)} km⁻¹（当前倍率 ${params.mieScale.toFixed(2)}×）
- 标高：瑞利 ${ATMOSPHERE.rayleighScaleHeightKm} km，米氏 ${ATMOSPHERE.mieScaleHeightKm} km
- 观测高度：${ATMOSPHERE.observerAltitudeKm} km；云底：${ATMOSPHERE.cloudBaseKm} km
- 太阳高度角范围：−6° 至 90°；连续性验证步进：0.25°
- 渲染：GPU 单次散射天空 + 太阳方向自阴影体积云 + 海面云影

## 验证结论

| 验证项 | 结果 |
| --- | --- |
| 正午天顶蓝色占优 | ${zenithBlueDominant ? 'PASS' : 'FAIL'} |
| 低太阳高度角地平线更暖 | ${sunsetHorizonWarmer ? 'PASS' : 'FAIL'} |
| 天空颜色连续，无阶跃色带 | ${maxAdjacentDelta < 0.2 ? 'PASS' : 'FAIL'} |
| 天空到地平线过渡自然 | ${maxTransition < 0.06 ? 'PASS' : 'FAIL'} |
| 地平线亮度高于天顶 | ${horizonBrighter ? 'PASS' : 'FAIL'} |
| 散射系数增大时直射日照单调下降 | ${directFalls ? 'PASS' : 'FAIL'} |
| 散射系数增大时漫射天空单调上升 | ${diffuseRises ? 'PASS' : 'FAIL'} |
| 云量与厚度增大时云影遮蔽增强 | ${cloudShadowGrows ? 'PASS' : 'FAIL'} |

相邻 0.25° 采样的最大 sRGB ΔRGB 为 **${maxAdjacentDelta.toFixed(3)}**
（出现在 ${maxAdjacentAt.toFixed(2)}°），低于连续性阈值 0.200。
天空至地平线 0.5° 观测步进的最大 ΔRGB 为 **${maxTransition.toFixed(4)}**。

## 不同太阳高度角

| 高度角 | 太阳方向 (x, y, z) | 太阳颜色 | 天顶颜色 | 地平线颜色 | 直射透射 | 地面照度 |
| ---: | --- | --- | --- | --- | ---: | ---: |
${selectedTable}

太阳方向采用 y 轴向上的单位向量，方位角为 ${params.sunAzimuth}°。低角度时蓝光先被瑞利散射移除，
太阳与地平线转暖；高度角升高后，直射透射与地面照度单调增加，天空蓝光占比恢复。

## 天空与地平线过渡

沿同一太阳高度角，从地平线 0.8° 仰角向上以 0.5° 步进采样至 45°。最大相邻色差远低于
0.06 的可见阶跃阈值，说明天空—地平线渐变由连续散射积分产生，没有硬分界或色带。

| 太阳高度角 | 最大相邻 ΔRGB | 出现仰角 |
| ---: | ---: | ---: |
${transitionTable}

## 散射系数与日照

直射光使用 Beer–Lambert 透射：

\`\`\`text
T = exp[−(βR · HR · mR + βM · HM · mM)]
E = E0 · sin(h) · T
\`\`\`

β 增大时，直射透射和地面照度单调下降；漫射天空辐射因散射路径增加而上升。
在 2° 日落与 14° 黄金时刻，基准地面照度分别为
${(sunset.illuminance).toFixed(0)} lx 与
${(selectedRows.find((row) => row.elevation === 14).illuminance).toFixed(0)} lx。

| 瑞利系数倍率 | 直射 I/I₀ | 归一化漫射天空 | 14° 地面照度 |
| ---: | ---: | ---: | ---: |
${scatteringTable}

![散射系数与日照关系](./scattering-curve.svg)

## 云层覆盖、厚度与云影

| 云量 | 厚度 | 云顶 | 光学厚度 τ | 云影遮蔽 |
| ---: | ---: | ---: | ---: | ---: |
${cloudTable}

体积着色在每个云样本沿太阳方向继续采样，使用连续透射率计算云底明暗；海面使用同一云层场
计算投影阴影。覆盖率和厚度增加时，光程与光学厚度增加，云影遮蔽随之增强。
当前场景为 ${(currentCloud.coverage * 100).toFixed(0)}% 云量、${currentCloud.thickness.toFixed(2)} km
厚度，云底/云顶 ${currentCloud.baseKm.toFixed(2)}/${currentCloud.topKm.toFixed(2)} km，
光学厚度 ${currentCloud.opticalDepth.toFixed(2)}，云影遮蔽 ${(currentCloud.shadowFraction * 100).toFixed(1)}%。

![云量、厚度与云影](./cloud-shadow.svg)

## 高度角连续色带

![不同太阳高度角的天空连续色带](./elevation-strip.svg)

## 渲染场景

| 场景 | 太阳高度角 | 截图 |
| --- | ---: | --- |
| 黄金时刻 + 体积云 | 14° | [preview-default.png](./preview-default.png) |
| 正午 | 62° | [preview-noon.png](./preview-noon.png) |
| 日落 | 2° | [preview-sunset.png](./preview-sunset.png) |
| 晴空对照 | 14° | [preview-clear.png](./preview-clear.png) |
| 厚云 + 云影 | 24° | [preview-clouds-shadow.png](./preview-clouds-shadow.png) |
| 同云层关闭云影 | 24° | [preview-clouds-no-shadow.png](./preview-clouds-no-shadow.png) |

## 复现

\`\`\`bash
npm run validate
npm test
npm run serve
\`\`\`
`;

writeFileSync(resolve(artifacts, 'validation.md'), reportMarkdown);
writeFileSync(resolve(artifacts, 'validation-report.md'), reportMarkdown);

console.log(`Continuity ΔRGB: ${maxAdjacentDelta.toFixed(4)} at ${maxAdjacentAt.toFixed(2)}°`);
console.log(`Sky/horizon transition ΔRGB: ${maxTransition.toFixed(4)}`);
console.log(`Direct falls: ${directFalls}; diffuse rises: ${diffuseRises}`);
console.log(`Cloud shadow grows: ${cloudShadowGrows}`);
console.log(`Wrote ${artifacts}/validation.md and atmosphere-validation.json`);
