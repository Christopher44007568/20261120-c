import { DATASETS, getDataset } from "./datasets.js";
import { bounds } from "./math.js";
import { buildMesh } from "./mesh.js";
import { MeshRenderer } from "./renderer.js";
import { buildShadowVolume, cameraCrossing } from "./shadow.js";

const $ = (selector) => document.querySelector(selector);
const canvas = $("#mesh-canvas");
const renderer = new MeshRenderer(canvas);

const ui = {
  tabs: $("#dataset-tabs"),
  caseName: $("#active-case-name"),
  caseDescription: $("#active-case-description"),
  inspectorTitle: $("#inspector-title"),
  casePass: $("#case-pass"),
  topologyStatus: $("#topology-status"),
  hullClosed: $("#hull-closed-live"),
  tetManifold: $("#tet-manifold-live"),
  emptySphere: $("#empty-sphere-live"),
  volume: $("#volume-live"),
  vertices: $("#count-vertices"),
  verticesNote: $("#count-vertices-note"),
  edges: $("#count-edges"),
  edgesNote: $("#count-edges-note"),
  faces: $("#count-faces"),
  facesNote: $("#count-faces-note"),
  tets: $("#count-tets"),
  tetsNote: $("#count-tets-note"),
  euler: $("#euler-label"),
  auditList: $("#audit-list"),
  ledger: $("#degeneracy-ledger"),
  strategy: $("#strategy-summary"),
  caseTable: $("#case-table-body"),
  crossingLog: $("#crossing-log"),
  capVerdict: $("#cap-verdict"),
  footer: $("#footer-summary"),
  templateLive: $("#template-live"),
  replayFill: $("#replay-fill"),
  replayState: $("#replay-state"),
  enterMark: $("#enter-mark"),
  exitMark: $("#exit-mark"),
  replayButton: $("#replay-button"),
  legend: $("#legend"),
  toast: $("#toast"),
};

let activeId = "random";
let replayFrame = 0;
let toastTimer = 0;
const results = new Map();

function integer(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

function sci(value) {
  if (value === 0) return "0";
  if (!Number.isFinite(value)) return "∞";
  return value.toExponential(2).replace("e-", "e−");
}

function resultPath(result) {
  return result.mesh.degeneracy.intrinsicRank === 2 ? "2D LIFT" : "3D BW";
}

function strategyText(result) {
  const degeneracy = result.mesh.degeneracy;
  if (degeneracy.intrinsicRank === 2) {
    return "检测到内在维数 2：先投影做二维 Delaunay，再添加法向两侧合成支撑点。原始 40 个平面点全部保留，双锥网格没有零体积单元。";
  }
  if (degeneracy.planarClusters > 0 || degeneracy.cosphericalEmptySphereHits > 0) {
    return "检测到共面与共球叠加退化：正则化坐标打破空球平局，源坐标单独统计极大共面簇与空球边界命中；远端与近端封帽始终成对生成。";
  }
  return "一般位置点集直接使用增量凸包与 Bowyer–Watson。边入射、定向、Euler 特征和体积守恒均通过自动审计。";
}

function initialize() {
  for (const dataset of DATASETS) {
    const mesh = buildMesh(dataset);
    if (mesh.error) {
      results.set(dataset.id, { dataset, mesh, error: mesh.error });
      continue;
    }
    const shadow = buildShadowVolume(mesh);
    const crossing = cameraCrossing(shadow, mesh.points);
    shadow.crossing = crossing;
    results.set(dataset.id, { dataset, mesh, shadow, crossing, error: null });
  }
  buildTabs();
  buildCaseTable();
  const failures = [...results.values()].filter((result) => result.error || !result.mesh.allPassed).length;
  ui.footer.textContent = `${results.size - failures} / ${results.size} CASES PASS`;
  $("#system-state").textContent = failures ? `${failures} CASE FAILURE` : "KERNEL READY";
  selectDataset(activeId);
  updateClock();
  window.setInterval(updateClock, 47);
}

function buildTabs() {
  ui.tabs.innerHTML = "";
  for (const dataset of DATASETS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "dataset-tab";
    button.dataset.id = dataset.id;
    button.setAttribute("role", "tab");
    button.innerHTML = `${dataset.short}<span>${dataset.name}</span>`;
    button.addEventListener("click", () => selectDataset(dataset.id));
    ui.tabs.append(button);
  }
}

function buildCaseTable() {
  ui.caseTable.innerHTML = "";
  for (const dataset of DATASETS) {
    const result = results.get(dataset.id);
    const row = document.createElement("tr");
    row.dataset.id = dataset.id;
    if (result.error) {
      row.innerHTML = `<td><span class="case-name"><i class="case-dot warn"></i>${dataset.name}</span></td><td>ERROR</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td><span class="mini-fail">FAIL</span></td>`;
    } else {
      const { mesh } = result;
      const hasDegeneracy = mesh.degeneracy.planarClusters > 0 || mesh.degeneracy.cosphericalEmptySphereHits > 0;
      row.innerHTML = `<td><span class="case-name"><i class="case-dot ${hasDegeneracy ? "warn" : ""}"></i>${dataset.name}</span></td>
        <td><span class="path-tag">${resultPath(result)}</span></td>
        <td class="num">${integer(mesh.counts.meshVertices)}</td>
        <td class="num">${integer(mesh.counts.tetraEdges)}</td>
        <td class="num">${integer(mesh.counts.hullFaces)}</td>
        <td class="num">${integer(mesh.counts.tetrahedra)}</td>
        <td class="num">${mesh.hullAudit.euler}</td>
        <td><span class="mini-pass">${mesh.allPassed ? "PASS" : "FAIL"}</span></td>`;
    }
    row.addEventListener("click", () => selectDataset(dataset.id));
    ui.caseTable.append(row);
  }
}

function selectDataset(id) {
  const result = results.get(getDataset(id).id);
  if (!result) return;
  activeId = result.dataset.id;
  if (!result.error) {
    renderer.setMesh(result.mesh);
    renderer.setShadow(result.shadow);
    updateInspector(result);
    updateCrossing(result);
    resetReplay();
  }
  for (const tab of ui.tabs.querySelectorAll(".dataset-tab")) {
    const active = tab.dataset.id === activeId;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  }
  for (const row of ui.caseTable.querySelectorAll("tr")) {
    row.classList.toggle("active", row.dataset.id === activeId);
  }
}

function setPass(element, passed, text = passed ? "PASS" : "FAIL") {
  element.textContent = text;
  element.classList.toggle("pass", passed);
  element.classList.toggle("fail", !passed);
}

function updateInspector(result) {
  const { mesh, dataset, crossing, shadow } = result;
  const passed = mesh.allPassed;
  ui.caseName.textContent = dataset.name;
  ui.caseDescription.textContent = dataset.description;
  ui.inspectorTitle.textContent = dataset.name;
  setPass(ui.casePass, passed, passed ? "VALID" : "INVALID");
  setPass(ui.topologyStatus, passed);
  ui.hullClosed.textContent = mesh.audits.hullClosed ? "YES" : "NO";
  ui.tetManifold.textContent = mesh.audits.tetraManifold ? "YES" : "NO";
  ui.emptySphere.textContent = mesh.audits.delaunayEmpty ? "YES" : "NO";
  ui.volume.textContent = mesh.audits.volumeConserved ? "YES" : "NO";
  ui.vertices.textContent = integer(mesh.counts.meshVertices);
  ui.verticesNote.textContent = `HULL ${mesh.counts.hullVertices}`;
  ui.edges.textContent = integer(mesh.counts.tetraEdges);
  ui.edgesNote.textContent = `HULL ${mesh.counts.hullEdges}`;
  ui.faces.textContent = integer(mesh.counts.hullFaces);
  ui.facesNote.textContent = `∂T ${mesh.counts.boundaryFaces}`;
  ui.tets.textContent = integer(mesh.counts.tetrahedra);
  ui.tetsNote.textContent = `E ${integer(mesh.counts.tetraEdges)}`;
  ui.euler.textContent = `χ = ${mesh.hullAudit.euler}`;
  renderAuditRows(mesh);
  renderLedger(result);
  ui.strategy.textContent = strategyText(result);
  updateLegend();
  updateCapVerdict(result);
  if (replayFrame) cancelAnimationFrame(replayFrame);
  renderer.setReplay(0, false);
}

function renderAuditRows(mesh) {
  const rows = [
    ["凸包边入射", mesh.hullAudit.closed ? "2 · 2E/F" : `${mesh.hullAudit.edgeIncidenceErrors} ERR`, mesh.hullAudit.closed],
    ["定向一致性", mesh.hullAudit.orientable ? "0 ERR" : `${mesh.hullAudit.orientationErrors} ERR`, mesh.hullAudit.orientable],
    ["四面体流形", mesh.tetAudit.manifold ? "2-FACE" : "BROKEN", mesh.tetAudit.manifold],
    ["边界连通分量", `${mesh.tetAudit.components} COMP`, mesh.tetAudit.components === 1],
    ["体积相对误差", sci(mesh.tetAudit.volumeError), mesh.tetAudit.volumeError <= 2e-5],
    ["空球违例", `${mesh.tetAudit.emptySphereViolations}`, mesh.tetAudit.emptySphereViolations === 0],
    ["零体积四面体", `${mesh.tetAudit.negativeTets}`, mesh.tetAudit.negativeTets === 0],
  ];
  ui.auditList.innerHTML = rows.map(([label, value, pass]) => `
    <div class="audit-row ${pass ? "" : "fail"}">
      <span>${label}</span><span>${value}</span>
    </div>`).join("");
}

function renderLedger(result) {
  const { mesh } = result;
  const degeneracy = mesh.degeneracy;
  const scale = bounds(mesh.points).size;
  const regularizationRatio = scale > 0 ? degeneracy.maxRegularizationOffset / scale : 0;
  const rows = [
    ["重复点合并", integer(degeneracy.duplicatesRemoved)],
    ["内在维数", `${degeneracy.intrinsicRank}D`],
    ["合成支撑点", integer(degeneracy.syntheticAnchors), degeneracy.syntheticAnchors > 0],
    ["极大共面簇", integer(degeneracy.planarClusters), degeneracy.planarClusters > 0],
    ["最大共面点数", integer(degeneracy.maxPlanarPoints), degeneracy.maxPlanarPoints > 0],
    ["额外共面点", integer(degeneracy.extraCoplanarPoints), degeneracy.extraCoplanarPoints > 0],
    ["共球插入平局", integer(degeneracy.cosphericalInsertionTies)],
    ["共球空球命中", integer(degeneracy.cosphericalEmptySphereHits), degeneracy.cosphericalEmptySphereHits > 0],
    ["退化四面体", integer(degeneracy.degenerateTetsRemoved)],
    ["正则化位移", regularizationRatio ? `${sci(regularizationRatio)} bbox` : "0"],
  ];
  ui.ledger.innerHTML = rows.map(([label, value, warn]) => `
    <div class="ledger-row ${warn ? "warn" : ""}"><span>${label}</span><b>${value}</b></div>`).join("");
}

function surfaceName(surface) {
  return {
    "near-cap": "近端封帽",
    "far-cap": "远端封帽",
    side: "轮廓侧面",
    unresolved: "未解析",
  }[surface] ?? surface;
}

function updateCrossing(result) {
  const { crossing, shadow } = result;
  ui.crossingLog.innerHTML = "";
  if (!crossing || !crossing.records.length) {
    ui.crossingLog.innerHTML = `<span class="crossing-empty">${crossing?.error ?? "未记录到穿越"}</span>`;
    ui.enterMark.style.display = "none";
    ui.exitMark.style.display = "none";
    return;
  }
  crossing.records.forEach((record, index) => {
    if (index > 0) {
      const arrow = document.createElement("span");
      arrow.className = "flip-arrow";
      arrow.textContent = "→";
      ui.crossingLog.append(arrow);
    }
    const card = document.createElement("article");
    card.className = `flip-card ${record.direction}`;
    card.innerHTML = `
      <span class="flip-direction">${record.delta > 0 ? "+1" : "−1"}</span>
      <div class="flip-copy">
        <b>${surfaceName(record.surface)}</b>
        <span>t ${record.t.toFixed(3)} · ${record.direction.toUpperCase()}</span>
      </div>
      <span class="flip-count">${record.templateBefore} → ${record.templateAfter}</span>`;
    ui.crossingLog.append(card);
  });
  const enter = crossing.records.find((record) => record.direction === "enter");
  const exit = crossing.records.find((record) => record.direction === "exit");
  ui.enterMark.style.display = enter ? "block" : "none";
  ui.exitMark.style.display = exit ? "block" : "none";
  if (enter) ui.enterMark.style.left = `${enter.t * 100}%`;
  if (exit) ui.exitMark.style.left = `${exit.t * 100}%`;
  ui.templateLive.textContent = "TEMPLATE Σ 0";
  ui.replayFill.style.width = "0%";
  ui.replayState.textContent = shadow.audit.capped && crossing.valid ? "CAPPED" : "AUDIT";
}

function updateCapVerdict(result) {
  const { shadow, crossing } = result;
  const passed = shadow.audit.capped && crossing.valid;
  ui.capVerdict.textContent = passed ? "封帽正确 · WATERTIGHT" : "封帽异常";
  ui.capVerdict.classList.toggle("pass", passed);
  ui.capVerdict.style.color = passed ? "" : "var(--red)";
  ui.capVerdict.style.borderColor = passed ? "" : "rgba(238,125,107,.35)";
}

function resetReplay() {
  if (replayFrame) cancelAnimationFrame(replayFrame);
  replayFrame = 0;
  const result = results.get(activeId);
  if (!result || result.error) return;
  renderer.setReplay(0, false);
  ui.replayFill.style.width = "0%";
  ui.replayState.textContent = result.shadow.audit.capped && result.crossing.valid ? "CAPPED" : "AUDIT";
  ui.templateLive.textContent = "TEMPLATE Σ 0";
  ui.replayButton.classList.remove("playing");
}

function playReplay() {
  const result = results.get(activeId);
  if (!result || result.error) return;
  if (replayFrame) cancelAnimationFrame(replayFrame);
  setMode("shadow");
  const duration = 4600;
  const started = performance.now();
  ui.replayButton.classList.add("playing");
  ui.replayState.textContent = "OUTSIDE";
  const tick = (now) => {
    const progress = Math.min((now - started) / duration, 1);
    const e = progress * progress * (3 - 2 * progress);
    renderer.setReplay(e, true);
    ui.replayFill.style.width = `${e * 100}%`;
    const inside = (e >= result.crossing.records[0]?.t && e <= result.crossing.records[1]?.t) ? 1 : 0;
    ui.templateLive.textContent = `TEMPLATE Σ ${inside}`;
    ui.replayState.textContent = inside ? "INSIDE" : "OUTSIDE";
    if (progress < 1) {
      replayFrame = requestAnimationFrame(tick);
    } else {
      replayFrame = 0;
      ui.replayState.textContent = "RETURN 0";
      ui.templateLive.textContent = "TEMPLATE Σ 0";
      ui.replayButton.classList.remove("playing");
    }
  };
  replayFrame = requestAnimationFrame(tick);
}

function setMode(mode) {
  renderer.setMode(mode);
  for (const button of document.querySelectorAll(".mode-button")) {
    button.classList.toggle("active", button.dataset.mode === mode);
  }
  updateLegend();
}

function updateLegend() {
  const mode = renderer.mode;
  if (mode === "tetra") {
    ui.legend.innerHTML = `
      <span><i class="legend-dot hull"></i>网格顶点</span>
      <span><i class="legend-line tetra"></i>四面体边</span>
      <span><i class="legend-dot interior"></i>内部顶点</span>`;
  } else if (mode === "shadow") {
    ui.legend.innerHTML = `
      <span><i class="legend-dot near"></i>近端帽</span>
      <span><i class="legend-dot far"></i>远端帽</span>
      <span><i class="legend-dot side"></i>轮廓侧面</span>`;
  } else {
    ui.legend.innerHTML = `
      <span><i class="legend-dot hull"></i>凸包顶点</span>
      <span><i class="legend-dot interior"></i>内部点</span>
      <span><i class="legend-line hull"></i>网格边</span>`;
  }
}

function exportReport() {
  const payload = {
    generatedAt: new Date().toISOString(),
    strategy: {
      coplanar: "Intrinsic rank 2: project to plane, 2D Delaunay, add two normal support anchors.",
      cospherical: "Deterministic bounded regularization for topological predicates; source coordinates retained for degeneracy counts.",
      capping: "Near light-facing cap + translated back-facing far cap + silhouette side quads.",
    },
    datasets: [...results.values()].map((result) => {
      if (result.error) return { id: result.dataset.id, error: result.error };
      return {
        id: result.dataset.id,
        name: result.dataset.name,
        counts: result.mesh.counts,
        degeneracy: result.mesh.degeneracy,
        hullAudit: result.mesh.hullAudit,
        tetraAudit: result.mesh.tetAudit,
        audits: result.mesh.audits,
        allPassed: result.mesh.allPassed,
        shadow: {
          counts: result.shadow.counts,
          audit: result.shadow.audit,
          crossing: {
            valid: result.crossing.valid,
            enterSurface: result.crossing.enterSurface,
            exitSurface: result.crossing.exitSurface,
            records: result.crossing.records,
          },
        },
      };
    }),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "hull-delaunay-audit.json";
  anchor.click();
  URL.revokeObjectURL(url);
  showToast("AUDIT REPORT EXPORTED");
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  ui.toast.textContent = message;
  ui.toast.classList.add("visible");
  toastTimer = window.setTimeout(() => ui.toast.classList.remove("visible"), 2100);
}

function updateClock() {
  const now = new Date();
  const time = [now.getHours(), now.getMinutes(), now.getSeconds()]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
  $("#clock").textContent = `${time}.${String(now.getMilliseconds()).padStart(3, "0")}`;
}

document.querySelectorAll(".mode-button").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});
ui.replayButton.addEventListener("click", playReplay);
$("#reset-view-button").addEventListener("click", () => renderer.resetView());
$("#export-button").addEventListener("click", exportReport);
$("#strategy-button").addEventListener("click", () => $("#help-dialog").showModal());
$("#help-button").addEventListener("click", () => $("#help-dialog").showModal());
$("#close-help").addEventListener("click", () => $("#help-dialog").close());
$("#dialog-confirm").addEventListener("click", () => $("#help-dialog").close());

initialize();
