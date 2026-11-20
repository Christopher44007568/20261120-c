import {
  parsePathData,
  normalizeContours,
  transformRawPoint,
} from "./contours.js";
import { analyzeGlyph } from "./geometry.js";

export const BUILTIN_SPECIMENS = [
  {
    id: "a-sharp",
    char: "A",
    title: "A",
    className: "锐角 / 负空间",
    path: "M8 94 L37 7 L53 7 L93 94 L77 94 L67 67 L30 67 L20 94 Z M36 53 L61 53 L49 20 Z",
    description: "尖顶、横杠与三角负空间。用于观察尖角分组和内部三角形的覆盖稳定性。",
    notes: ["尖顶", "三角 counter", "横杠接合"],
    annotations: [
      { x: 49, y: 7, label: "尖顶", kind: "sharp" },
      { x: 49, y: 44, label: "窄负空间", kind: "counter" },
      { x: 48, y: 69, label: "横杠", kind: "thin" },
    ],
  },
  {
    id: "o-round",
    char: "O",
    title: "O",
    className: "内孔 / 相邻曲线",
    path: "M50 5 C74 5 95 25 95 50 C95 75 74 95 50 95 C26 95 5 75 5 50 C5 25 26 5 50 5 Z M50 26 C37 26 26 38 26 50 C26 62 37 74 50 74 C63 74 74 62 74 50 C74 38 63 26 50 26 Z",
    description: "内外两条相邻曲线构成窄环，检查通道接缝与屏幕导数重建。",
    notes: ["内孔", "相邻曲线", "等宽环"],
    annotations: [
      { x: 50, y: 50, label: "内孔", kind: "counter" },
      { x: 78, y: 67, label: "相邻曲线", kind: "curve" },
    ],
  },
  {
    id: "i-thin",
    char: "i",
    title: "i",
    className: "细笔画 / 小间隙",
    path: "M45.5 32 L54.5 32 L54.5 95 L45.5 95 Z M50 10 C56 10 61 15 61 21 C61 27 56 32 50 32 C44 32 39 27 39 21 C39 15 44 10 50 10 Z",
    description: "窄竖笔与独立圆点。小字号下最容易出现断笔与点形丢失。",
    notes: ["细笔画", "点 / 竖笔间隙", "小字号"],
    annotations: [
      { x: 50, y: 67, label: "细笔画", kind: "thin" },
      { x: 50, y: 34, label: "窄间隙", kind: "gap" },
    ],
  },
  {
    id: "eight-loops",
    char: "8",
    title: "8",
    className: "双内孔 / 窄腰",
    path: "M50 6 C28 6 18 19 18 33 C18 43 24 50 32 55 C21 61 14 70 14 82 C14 94 29 100 50 100 C71 100 86 94 86 82 C86 70 79 61 68 55 C76 50 82 43 82 33 C82 19 72 6 50 6 Z M50 20 C59 20 65 26 65 33 C65 41 59 47 50 47 C41 47 35 41 35 33 C35 26 41 20 50 20 Z M50 62 C60 62 67 69 67 78 C67 87 60 93 50 93 C40 93 33 87 33 78 C33 69 40 62 50 62 Z",
    description: "两个内孔在上腰处形成窄负空间，适合检验严格拓扑与错误分类。",
    notes: ["双内孔", "窄腰", "相邻内曲线"],
    annotations: [
      { x: 50, y: 33, label: "上 counter", kind: "counter" },
      { x: 50, y: 55, label: "窄腰", kind: "gap" },
      { x: 50, y: 78, label: "下 counter", kind: "counter" },
    ],
  },
  {
    id: "k-wedge",
    char: "K",
    title: "K",
    className: "锐角 / 窄楔形",
    path: "M12 8 L28 8 L28 43 L60 8 L82 8 L45 45 L84 94 L61 94 L28 57 L28 94 L12 94 Z",
    description: "竖笔与斜臂交会处形成窄楔形负空间，重点观察角点颜色分组。",
    notes: ["锐角接合", "窄楔形", "斜线"],
    annotations: [
      { x: 29, y: 47, label: "锐角接合", kind: "sharp" },
      { x: 43, y: 51, label: "窄楔形", kind: "gap" },
    ],
  },
  {
    id: "s-open",
    char: "S",
    title: "S*",
    className: "开放轮廓 / 故障样本",
    path: "M78 21 C67 10 49 6 35 11 C21 16 16 28 26 37 C34 44 54 44 65 52 C77 61 77 79 62 89 C50 97 30 96 16 84",
    description: "末尾未闭合的刻意损坏轮廓。所有字号都会保留拓扑错误，可与采样误差区分。",
    notes: ["开放轮廓", "稳定复现", "轮廓错误样本"],
    fault: true,
    annotations: [
      { x: 16, y: 84, label: "缺失闭合边", kind: "fault" },
      { x: 55, y: 45, label: "相邻曲线", kind: "curve" },
    ],
  },
];

export function buildSpecimen(definition, cornerAngle = 42) {
  const rawContours = definition.rawContours || parsePathData(definition.path);
  const normalized = normalizeContours(rawContours);
  const analysis = analyzeGlyph(normalized.contours, cornerAngle);
  const annotations = (definition.annotations || []).map((annotation) => ({
    ...annotation,
    ...transformRawPoint(annotation, normalized.transform),
  }));

  return {
    ...definition,
    rawContours,
    contours: normalized.contours,
    transform: normalized.transform,
    analysis,
    annotations,
    source: definition.source || "builtin",
  };
}

export function buildFontSpecimen({ glyph, font, character, index }) {
  const path = glyph.getPath(0, 0, 1000);
  const rawContours = [];
  let current = null;

  for (const command of path.commands) {
    if (command.type === "M") {
      current = { segments: [], closed: false, start: { x: command.x, y: command.y } };
      rawContours.push(current);
    } else if (command.type === "L" && current) {
      const previous = current.segments.at(-1);
      const p0 = previous ? previous.p3 || previous.p2 || previous.p1 : current.start;
      current.segments.push({ type: "line", p0, p1: { x: command.x, y: command.y } });
    } else if (command.type === "Q" && current) {
      const previous = current.segments.at(-1);
      const p0 = previous ? previous.p3 || previous.p2 || previous.p1 : current.start;
      current.segments.push({
        type: "quad",
        p0,
        p1: { x: command.x1, y: command.y1 },
        p2: { x: command.x, y: command.y },
      });
    } else if (command.type === "C" && current) {
      const previous = current.segments.at(-1);
      const p0 = previous ? previous.p3 || previous.p2 || previous.p1 : current.start;
      current.segments.push({
        type: "cubic",
        p0,
        p1: { x: command.x1, y: command.y1 },
        p2: { x: command.x2, y: command.y2 },
        p3: { x: command.x, y: command.y },
      });
    } else if (command.type === "Z" && current) {
      current.closed = true;
    }
  }
  for (const contour of rawContours) {
    contour.closed = true;
  }

  const id = `font-${index}-${character.codePointAt(0).toString(16)}`;
  return buildSpecimen(
    {
      id,
      char: character,
      title: character,
      className: `${font.names?.fontFamily?.en || font.names?.fullName?.en || "Local font"} / 导入轮廓`,
      rawContours: rawContours.filter((contour) => contour.segments.length > 0),
      description: `来自本地字体 ${font.names?.fullName?.en || font.names?.fontFamily?.en || "未命名字体"} 的 ${character} 字形。`,
      notes: ["本地轮廓", `${rawContours.length} 环`, "OpenType"],
      source: "font",
      fontName: font.names?.fullName?.en || font.names?.fontFamily?.en || "Local font",
    },
    42,
  );
}
