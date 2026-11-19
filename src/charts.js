const COLORS = {
  text: "#c8d3d9",
  muted: "#62727c",
  faint: "#33414a",
  grid: "rgba(142, 166, 179, 0.12)",
  blend: "rgba(255, 172, 93, 0.11)",
  blendLine: "rgba(255, 172, 93, 0.24)",
  lbs: "#f06a62",
  dqs: "#39c6b4",
  white: "#f1f8f7",
};

function setupCanvas(canvas) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(canvas.clientWidth * dpr));
  const height = Math.max(1, Math.round(canvas.clientHeight * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const context = canvas.getContext("2d");
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.clearRect(0, 0, width / dpr, height / dpr);
  return {
    context,
    width: width / dpr,
    height: height / dpr,
  };
}

function line(context, points, color, width = 1.5) {
  if (points.length < 2) return;
  context.beginPath();
  context.moveTo(points[0][0], points[0][1]);
  for (let index = 1; index < points.length; index += 1) {
    context.lineTo(points[index][0], points[index][1]);
  }
  context.strokeStyle = color;
  context.lineWidth = width;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.stroke();
}

function dot(context, point, color, radius = 2.3) {
  context.beginPath();
  context.arc(point[0], point[1], radius, 0, Math.PI * 2);
  context.fillStyle = color;
  context.fill();
}

export function drawAreaChart(canvas, model, analysis) {
  const { context, width, height } = setupCanvas(canvas);
  const margin = { left: 30, right: 9, top: 10, bottom: 22 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const x = (z) => margin.left + (z / model.height) * plotWidth;
  const y = (value) => margin.top + (1 - Math.min(value, 1.08) / 1.08) * plotHeight;

  context.fillStyle = "rgba(4, 8, 12, 0.25)";
  context.fillRect(margin.left, margin.top, plotWidth, plotHeight);
  context.fillStyle = COLORS.blend;
  context.fillRect(x(model.blendStart), margin.top, x(model.blendEnd) - x(model.blendStart), plotHeight);
  context.strokeStyle = COLORS.blendLine;
  context.lineWidth = 1;
  context.strokeRect(x(model.blendStart), margin.top, x(model.blendEnd) - x(model.blendStart), plotHeight);

  context.font = '8px "SFMono-Regular", Consolas, "DQS Sans SC", monospace';
  context.textAlign = "left";
  context.textBaseline = "middle";
  for (const tick of [0, 0.25, 0.5, 0.75, 1]) {
    const py = y(tick);
    context.strokeStyle = COLORS.grid;
    context.beginPath();
    context.moveTo(margin.left, py);
    context.lineTo(width - margin.right, py);
    context.stroke();
    context.fillStyle = COLORS.muted;
    context.fillText(`${Math.round(tick * 100)}%`, 0, py);
  }

  for (const tick of [0, 1, 2, 3, 4]) {
    context.fillStyle = COLORS.muted;
    context.textAlign = "center";
    context.fillText(tick.toFixed(0), x(tick), height - 8);
  }

  const lbsPoints = analysis.ringZ.map((z, index) => [x(z), y(analysis.lbsAreaRatio[index])]);
  const dqsPoints = analysis.ringZ.map((z, index) => [x(z), y(analysis.dqsAreaRatio[index])]);
  line(context, dqsPoints, COLORS.dqs, 2);
  line(context, lbsPoints, COLORS.lbs, 2);

  context.setLineDash([3, 3]);
  context.strokeStyle = "rgba(241, 248, 247, 0.26)";
  context.beginPath();
  context.moveTo(x(model.jointZ), margin.top);
  context.lineTo(x(model.jointZ), height - margin.bottom);
  context.stroke();
  context.setLineDash([]);
  context.fillStyle = COLORS.faint;
  context.textAlign = "right";
  context.fillText("z=2", x(model.jointZ) - 3, margin.top + 5);
}

function projection(point, mode) {
  if (mode === "YZ") return [point[1], point[2]];
  return [point[0], point[1]];
}

export function drawTrajectoryChart(canvas, model, trajectories, analysis) {
  const { context, width, height } = setupCanvas(canvas);
  const margin = 14;
  const plotWidth = width - margin * 2;
  const plotHeight = height - margin * 2;
  const lbs = trajectories.lbs.map((point) => projection(point, model.projection));
  const dqs = trajectories.dqs.map((point) => projection(point, model.projection));
  const points = [...lbs, ...dqs];
  let minX = Math.min(...points.map((point) => point[0]));
  let maxX = Math.max(...points.map((point) => point[0]));
  let minY = Math.min(...points.map((point) => point[1]));
  let maxY = Math.max(...points.map((point) => point[1]));
  const spanX = Math.max(maxX - minX, 0.8);
  const spanY = Math.max(maxY - minY, 0.8);
  minX -= spanX * 0.18;
  maxX += spanX * 0.18;
  minY -= spanY * 0.18;
  maxY += spanY * 0.18;
  const finalSpanX = maxX - minX;
  const finalSpanY = maxY - minY;
  const scale = Math.min(plotWidth / finalSpanX, plotHeight / finalSpanY);
  const centerX = (minX + maxX) * 0.5;
  const centerY = (minY + maxY) * 0.5;
  const map = (point) => [
    width * 0.5 + (point[0] - centerX) * scale,
    height * 0.5 - (point[1] - centerY) * scale,
  ];

  context.strokeStyle = COLORS.grid;
  context.lineWidth = 1;
  const origin = map([0, 0]);
  context.beginPath();
  context.moveTo(margin, origin[1]);
  context.lineTo(width - margin, origin[1]);
  context.moveTo(origin[0], margin);
  context.lineTo(origin[0], height - margin);
  context.stroke();

  const mappedLbs = lbs.map(map);
  const mappedDqs = dqs.map(map);
  line(context, mappedLbs, COLORS.lbs, 1.6);
  line(context, mappedDqs, COLORS.dqs, 1.8);
  mappedLbs.forEach((point, index) => {
    if (index % 4 !== 0) return;
    dot(context, point, "rgba(240, 106, 98, 0.58)", 1.5);
  });
  mappedDqs.forEach((point, index) => {
    if (index % 4 !== 0) return;
    dot(context, point, "rgba(57, 198, 180, 0.62)", 1.5);
  });

  const currentIndex = Math.round((analysis.angle ?? 0) / Math.PI * (trajectories.angles.length - 1));
  const clampedIndex = Math.max(0, Math.min(trajectories.angles.length - 1, currentIndex));
  dot(context, mappedLbs[clampedIndex], COLORS.lbs, 3.2);
  dot(context, mappedDqs[clampedIndex], COLORS.dqs, 3.2);

  context.font = '8px "SFMono-Regular", Consolas, "DQS Sans SC", monospace';
  context.fillStyle = COLORS.muted;
  context.textAlign = "left";
  context.fillText("0°", mappedDqs[0][0] + 5, mappedDqs[0][1] - 5);
  const last = mappedDqs[mappedDqs.length - 1];
  context.textAlign = "right";
  context.fillText("180°", last[0] - 5, last[1] + 10);
}

export function drawSignSparkline(canvas, proofs) {
  const { context, width, height } = setupCanvas(canvas);
  context.strokeStyle = COLORS.grid;
  context.beginPath();
  context.moveTo(5, height - 8);
  context.lineTo(width - 5, height - 8);
  context.stroke();
  const points = proofs.signJumps.map((value, index) => [
    5 + (index / Math.max(1, proofs.signJumps.length - 1)) * (width - 10),
    height - 8 - Math.min(value * 1e12, 1) * (height - 16),
  ]);
  line(context, points, COLORS.dqs, 1.5);
}
