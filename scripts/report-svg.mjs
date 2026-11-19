const esc = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;');

const hex = (rgb) => `#${rgb.map((value) =>
  Math.round(Math.max(0, Math.min(255, value))).toString(16).padStart(2, '0')).join('')}`;

function gradient(id, rows, key) {
  const stops = rows.map((row, index) => {
    const offset = (index / Math.max(1, rows.length - 1) * 100).toFixed(3);
    return `<stop offset="${offset}%" stop-color="${hex(row[key])}"/>`;
  }).join('');
  return `<linearGradient id="${id}" x1="0" x2="1" y1="0" y2="0">${stops}</linearGradient>`;
}

export function elevationStripSvg(rows) {
  const x0 = 82;
  const width = 1110;
  const ticks = [];
  for (let elevation = 0; elevation <= 90; elevation += 30) {
    const ratio = (elevation + 6) / 96;
    const x = x0 + ratio * width;
    ticks.push(`
      <line x1="${x}" y1="76" x2="${x}" y2="260" stroke="#b9d5df" stroke-opacity=".12"/>
      <text x="${x}" y="276" fill="#86a8b6" font-size="10" text-anchor="middle">${elevation}°</text>`);
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="300" viewBox="0 0 1240 300">
  <rect width="1240" height="300" fill="#0a1721"/>
  <text x="52" y="36" fill="#e6f1f4" font-size="19" font-family="sans-serif" font-weight="300">
    Continuous sky color across solar elevation
  </text>
  <text x="52" y="56" fill="#6f95a5" font-size="9" font-family="monospace" letter-spacing="2">
    STEP 0.25° · −6° TO 90° · sRGB 8-BIT
  </text>
  <defs>${gradient('horizon', rows, 'horizon')}${gradient('zenith', rows, 'zenith')}${gradient('sun', rows, 'solar')}</defs>
  ${ticks.join('')}
  <text x="52" y="106" fill="#86a8b6" font-size="9" font-family="monospace">HORIZON</text>
  <rect x="${x0}" y="82" width="${width}" height="58" rx="2" fill="url(#horizon)"/>
  <text x="52" y="178" fill="#86a8b6" font-size="9" font-family="monospace">ZENITH</text>
  <rect x="${x0}" y="154" width="${width}" height="58" rx="2" fill="url(#zenith)"/>
  <text x="52" y="249" fill="#86a8b6" font-size="9" font-family="monospace">SUN</text>
  <rect x="${x0}" y="226" width="${width}" height="28" rx="2" fill="url(#sun)"/>
  <text x="52" y="290" fill="#4f7483" font-size="8" font-family="monospace">
    HORIZON 0.8° / ZENITH 89.5° / SOLAR TRANSMITTANCE
  </text>
</svg>`;
}

export function scatteringCurveSvg(series) {
  const x0 = 70;
  const x1 = 710;
  const y0 = 52;
  const y1 = 320;
  const sx = (scale) => x0 + (scale - 0.2) / 2.8 * (x1 - x0);
  const sy = (value) => y1 - Math.max(0, Math.min(1, value)) * (y1 - y0);
  const direct = series.map((point, index) =>
    `${index === 0 ? 'M' : 'L'}${sx(point.scale).toFixed(2)},${sy(point.direct).toFixed(2)}`
  ).join(' ');
  const diffuse = series.map((point, index) =>
    `${index === 0 ? 'M' : 'L'}${sx(point.scale).toFixed(2)},${sy(point.diffuse).toFixed(2)}`
  ).join(' ');
  const grid = [];
  for (let i = 0; i <= 4; i += 1) {
    const y = y0 + i * (y1 - y0) / 4;
    const value = 1 - i / 4;
    grid.push(`<line x1="${x0}" y1="${y}" x2="${x1}" y2="${y}" stroke="#9fc6d3" stroke-opacity=".1"/>
      <text x="${x0 - 12}" y="${y + 3}" text-anchor="end" fill="#6f95a5" font-size="9" font-family="monospace">${value.toFixed(2)}</text>`);
  }
  const xTicks = [0.2, 1, 2, 3].map((scale) =>
    `<text x="${sx(scale)}" y="342" text-anchor="middle" fill="#6f95a5" font-size="9" font-family="monospace">${scale}×</text>`
  ).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="760" height="390" viewBox="0 0 760 390">
  <rect width="760" height="390" fill="#0a1721"/>
  <text x="46" y="28" fill="#e6f1f4" font-size="17" font-family="sans-serif" font-weight="300">
    Scattering coefficient × sunlight
  </text>
  <text x="46" y="44" fill="#6f95a5" font-size="8" font-family="monospace" letter-spacing="2">
    BEER–LAMBERT DIRECT TRANSMISSION · DIFFUSE SKY RESPONSE
  </text>
  ${grid.join('')}
  <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="#9fc6d3" stroke-opacity=".2"/>
  <line x1="${sx(1)}" y1="${y0}" x2="${sx(1)}" y2="${y1}" stroke="#d8edf3" stroke-opacity=".22" stroke-dasharray="3 4"/>
  <path d="${direct}" fill="none" stroke="#e6a15d" stroke-width="1.6"/>
  <path d="${diffuse}" fill="none" stroke="#76c9e4" stroke-width="1.6" stroke-dasharray="5 4"/>
  <circle cx="${sx(1)}" cy="${sy(series.find((point) => Math.abs(point.scale - 1) < 0.01)?.direct || 0)}" r="3.4" fill="#e9f9fd"/>
  ${xTicks}
  <text x="${x1}" y="366" text-anchor="end" fill="#4f7483" font-size="8" font-family="monospace">
    RAYLEIGH COEFFICIENT MULTIPLIER
  </text>
  <text x="46" y="366" fill="#e6a15d" font-size="9" font-family="monospace">— DIRECT I/I₀</text>
  <text x="170" y="366" fill="#76c9e4" font-size="9" font-family="monospace">--- DIFFUSE SKY (NORMALIZED)</text>
</svg>`;
}

export function cloudShadowSvg(rows) {
  const x0 = 66;
  const x1 = 710;
  const y0 = 58;
  const y1 = 320;
  const coverages = [...new Set(rows.map((row) => row.coverage))];
  const sx = (coverage) => x0 + coverages.indexOf(coverage) / (coverages.length - 1) * (x1 - x0);
  const sy = (shadow) => y1 - shadow * (y1 - y0);
  const series = [0.5, 1.5, 3].map((thickness) => {
    const points = rows.filter((row) => row.thickness === thickness);
    return {
      thickness,
      path: points.map((point, index) =>
        `${index === 0 ? 'M' : 'L'}${sx(point.coverage).toFixed(2)},${sy(point.shadowFraction).toFixed(2)}`
      ).join(' ')
    };
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" width="760" height="390" viewBox="0 0 760 390">
  <rect width="760" height="390" fill="#0a1721"/>
  <text x="46" y="29" fill="#e6f1f4" font-size="17" font-family="sans-serif" font-weight="300">
    Cloud coverage, thickness and shadow
  </text>
  <text x="46" y="45" fill="#6f95a5" font-size="8" font-family="monospace" letter-spacing="2">
    VOLUMETRIC SUN MARCH · OPTICAL DEPTH TO SHADOW FRACTION
  </text>
  ${[0, 0.25, 0.5, 0.75, 1].map((value) => {
    const y = sy(value);
    return `<line x1="${x0}" y1="${y}" x2="${x1}" y2="${y}" stroke="#9fc6d3" stroke-opacity=".1"/>
      <text x="${x0 - 10}" y="${y + 3}" text-anchor="end" fill="#6f95a5" font-size="9" font-family="monospace">${Math.round(value * 100)}%</text>`;
  }).join('')}
  ${coverages.map((coverage) =>
    `<text x="${sx(coverage)}" y="342" text-anchor="middle" fill="#6f95a5" font-size="9" font-family="monospace">${Math.round(coverage * 100)}%</text>`
  ).join('')}
  ${series.map((line, index) => {
    const colors = ['#78c9e3', '#e6a15d', '#dcecf0'];
    return `<path d="${line.path}" fill="none" stroke="${colors[index]}" stroke-width="1.7" ${index === 2 ? 'stroke-dasharray="4 4"' : ''}/>`;
  }).join('')}
  ${series.map((line, index) => {
    const colors = ['#78c9e3', '#e6a15d', '#dcecf0'];
    return `<text x="${x0 + 5}" y="${73 + index * 17}" fill="${colors[index]}" font-size="9" font-family="monospace">— ${line.thickness.toFixed(1)} km</text>`;
  }).join('')}
  <text x="${x1}" y="367" text-anchor="end" fill="#4f7483" font-size="8" font-family="monospace">CLOUD COVERAGE</text>
  <text x="46" y="367" fill="#4f7483" font-size="8" font-family="monospace">SHADOW FRACTION</text>
</svg>`;
}
