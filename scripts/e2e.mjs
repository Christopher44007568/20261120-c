import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "playwright";
import { createSceneMeshes } from "../src/geometry.js";
import { buildShadowVolume } from "../src/shadow-volume.js";
import { startServer } from "./server.mjs";

const ROOT = process.cwd();
const ARTIFACTS = join(ROOT, "artifacts", "final");

function volumeTopology(positions) {
  const vertexIds = new Map();
  const edges = new Map();
  const vertexId = (offset) => {
    const key = [
      positions[offset].toFixed(4),
      positions[offset + 1].toFixed(4),
      positions[offset + 2].toFixed(4),
    ].join(",");
    if (!vertexIds.has(key)) vertexIds.set(key, vertexIds.size);
    return vertexIds.get(key);
  };
  for (let offset = 0; offset < positions.length; offset += 9) {
    const triangle = [vertexId(offset), vertexId(offset + 3), vertexId(offset + 6)];
    for (let edge = 0; edge < 3; edge += 1) {
      const a = triangle[edge];
      const b = triangle[(edge + 1) % 3];
      const key = a < b ? `${a}:${b}` : `${b}:${a}`;
      edges.set(key, (edges.get(key) ?? 0) + 1);
    }
  }
  let boundaryEdges = 0;
  let nonManifoldEdges = 0;
  for (const count of edges.values()) {
    if (count === 1) boundaryEdges += 1;
    if (count > 2) nonManifoldEdges += 1;
  }
  return { boundaryEdges, nonManifoldEdges, edges: edges.size };
}

function structuralAudit() {
  const meshes = createSceneMeshes();
  const output = {};
  for (const [key, mesh] of Object.entries(meshes)) {
    const capped = buildShadowVolume(mesh, { caps: true });
    const uncapped = buildShadowVolume(mesh, { caps: false });
    output[key] = {
      meshTriangles: mesh.triangles.length,
      meshBoundaryEdges: mesh.boundaryEdges,
      meshClosed: mesh.closed,
      capped: {
        volumeTriangles: capped.triangleCount,
        sideTriangles: capped.sideTriangles,
        capTriangles: capped.capTriangles,
        topology: volumeTopology(capped.positions),
      },
      uncapped: {
        volumeTriangles: uncapped.triangleCount,
        sideTriangles: uncapped.sideTriangles,
        capTriangles: uncapped.capTriangles,
        topology: volumeTopology(uncapped.positions),
      },
      method: capped.method,
    };
  }
  return output;
}

async function captureMaskPng(page, mode, path) {
  const dataUrl = await page.evaluate((maskMode) => {
    const result = window.__stencilLab.captureMask(maskMode);
    const canvas = document.createElement("canvas");
    canvas.width = result.width;
    canvas.height = result.height;
    const context = canvas.getContext("2d");
    const image = context.createImageData(result.width, result.height);
    for (let index = 0; index < result.mask.length; index += 1) {
      const x = index % result.width;
      const y = result.height - 1 - Math.floor(index / result.width);
      const target = (y * result.width + x) * 4;
      image.data[target] = result.mask[index];
      image.data[target + 1] = result.mask[index];
      image.data[target + 2] = result.mask[index];
      image.data[target + 3] = 255;
    }
    context.putImageData(image, 0, 0);
    return canvas.toDataURL("image/png");
  }, mode);
  await writeFile(path, Buffer.from(dataUrl.split(",")[1], "base64"));
}

async function scenarioMetrics(page, scenario, options = {}) {
  await page.evaluate((next) => window.__stencilLab.setState(next), scenario);
  await page.waitForTimeout(options.wait ?? 260);
  const stats = await page.evaluate(() => window.__stencilLab.getStats());
  if (!options.compare) return { stats, mismatch: null };
  const mismatch = await page.evaluate(() => {
    const stencil = window.__stencilLab.captureMask("stencil").mask;
    const reference = window.__stencilLab.captureMask("shadowmap").mask;
    let different = 0;
    for (let index = 0; index < stencil.length; index += 1) {
      if ((stencil[index] > 127) !== (reference[index] > 127)) different += 1;
    }
    return different / stencil.length;
  });
  return { stats, mismatch };
}

export async function runE2E(options = {}) {
  const screenshots = options.screenshots ?? false;
  await mkdir(ARTIFACTS, { recursive: true });
  const structural = structuralAudit();
  const server = await startServer(ROOT);
  const browser = await chromium.launch({
    headless: true,
    args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"],
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
  });
  const browserErrors = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  await page.goto(server.url, { waitUntil: "networkidle" });
  await page.waitForFunction(() => Boolean(window.__stencilLab));
  await page.waitForTimeout(500);
  const gpu = await page.evaluate(() => window.__stencilLab.getGpuInfo());

  const scenarios = {
    closedOutsideZfail: {
      meshKey: "closed", cameraMode: "outside", caps: true, zFail: true, mode: "stencil",
    },
    closedOutsideZpass: {
      meshKey: "closed", cameraMode: "outside", caps: true, zFail: false, mode: "stencil",
    },
    closedInsideZfail: {
      meshKey: "closed", cameraMode: "inside", caps: true, zFail: true, mode: "stencil",
    },
    closedInsideZpass: {
      meshKey: "closed", cameraMode: "inside", caps: true, zFail: false, mode: "stencil",
    },
    openOutsideCaps: {
      meshKey: "open", cameraMode: "outside", caps: true, zFail: true, mode: "stencil",
    },
    openOutsideNoCaps: {
      meshKey: "open", cameraMode: "outside", caps: false, zFail: true, mode: "stencil",
    },
    openInsideCaps: {
      meshKey: "open", cameraMode: "inside", caps: true, zFail: true, mode: "stencil",
    },
    openInsideNoCaps: {
      meshKey: "open", cameraMode: "inside", caps: false, zFail: true, mode: "stencil",
    },
  };

  const measured = {};
  for (const [name, scenario] of Object.entries(scenarios)) {
    const result = await scenarioMetrics(page, scenario, { compare: true });
    measured[name] = {
      scenario,
      cameraInside: result.stats.cameraInside,
      meshClosed: result.stats.meshClosed,
      meshTriangles: result.stats.meshTriangles,
      volumeTriangles: result.stats.volumeTriangles,
      capTriangles: result.stats.capTriangles,
      fillRate: result.stats.fillRate,
      fillPixels: result.stats.fillPixels,
      overdraw: result.stats.overdraw,
      stencilHistogram: result.stats.stencilHistogram,
      stencilNonzero: result.stats.stencilNonzero,
      mismatchVsShadowMap: result.mismatch,
    };
    if (screenshots && ["closedOutsideZfail", "closedInsideZfail", "closedInsideZpass",
      "openOutsideCaps", "openOutsideNoCaps", "openInsideCaps", "openInsideNoCaps"].includes(name)) {
      await page.screenshot({ path: join(ARTIFACTS, `${name}.png`), fullPage: true });
    }
  }

  if (screenshots) {
    for (const [name, mode] of [
      ["openOutsideCaps", "stencil"],
      ["openOutsideNoCaps", "stencil"],
      ["closedOutsideZfail", "stencil"],
      ["closedInsideZfail", "stencil"],
    ]) {
      await page.evaluate((scenario) => window.__stencilLab.setState(scenario), scenarios[name]);
      await page.waitForTimeout(180);
      await captureMaskPng(page, mode, join(ARTIFACTS, `${name}-mask.png`));
    }
  }

  const edgeRuns = {};
  for (const size of [512, 1024, 2048]) {
    await page.evaluate((shadowMapSize) => window.__stencilLab.setState({
      meshKey: "plank",
      cameraMode: "outside",
      caps: true,
      zFail: true,
      mode: "stencil",
      shadowMapSize,
    }), size);
    await page.waitForTimeout(850);
    const stats = await page.evaluate(() => window.__stencilLab.getStats());
    edgeRuns[size] = stats.quality;
    if (screenshots) {
      if (size === 1024) {
        await page.screenshot({ path: join(ARTIFACTS, "plankOutsideStencil.png"), fullPage: true });
        await captureMaskPng(page, "stencil", join(ARTIFACTS, "plank-stencil-mask.png"));
        await captureMaskPng(page, "shadowmap", join(ARTIFACTS, "plank-shadowmap-1024-mask.png"));
      }
      if (size === 2048) {
        await page.evaluate(() => window.__stencilLab.setState({ mode: "split" }));
        await page.waitForTimeout(450);
        await page.screenshot({ path: join(ARTIFACTS, "plankSplitCompare.png"), fullPage: true });
        await page.evaluate(() => window.__stencilLab.setState({ mode: "shadowmap" }));
        await page.waitForTimeout(350);
        await page.screenshot({ path: join(ARTIFACTS, "plankOutsideShadowMap.png"), fullPage: true });
      }
    }
  }

  await page.evaluate(() => window.__stencilLab.setState({
    meshKey: "closed",
    cameraMode: "enter",
    caps: true,
    zFail: true,
    mode: "stencil",
  }));
  await page.evaluate(() => window.__stencilLab.setEnterProgress(0.64));
  await page.waitForTimeout(220);
  const enterOutside = await page.evaluate(() => window.__stencilLab.getStats());
  if (screenshots) {
    await page.screenshot({ path: join(ARTIFACTS, "enterOutside.png"), fullPage: true });
  }
  await page.evaluate(() => window.__stencilLab.setEnterProgress(0.86));
  await page.waitForTimeout(220);
  const enterInside = await page.evaluate(() => window.__stencilLab.getStats());
  const enterMismatch = await page.evaluate(() => {
    const stencil = window.__stencilLab.captureMask("stencil").mask;
    const reference = window.__stencilLab.captureMask("shadowmap").mask;
    let different = 0;
    for (let index = 0; index < stencil.length; index += 1) {
      if ((stencil[index] > 127) !== (reference[index] > 127)) different += 1;
    }
    return different / stencil.length;
  });
  if (screenshots) {
    await page.screenshot({ path: join(ARTIFACTS, "enterInside.png"), fullPage: true });
  }

  const report = {
    generatedAt: new Date().toISOString(),
    gpu,
    resolution: { width: 960, height: 620 },
    structural,
    scenarios: measured,
    thinEdge: {
      object: "12-triangle thin plank",
      metric: "RMS residual in pixels after straight-line fit of both shadow boundaries",
      runs: edgeRuns,
    },
    cameraEnter: {
      before: {
        progress: 0.64,
        cameraInside: enterOutside.cameraInside,
        cameraPosition: enterOutside.cameraPosition,
        stencilHistogram: enterOutside.stencilHistogram,
        stencilNonzero: enterOutside.stencilNonzero,
        fillRate: enterOutside.fillRate,
      },
      after: {
        progress: 0.86,
        cameraInside: enterInside.cameraInside,
        cameraPosition: enterInside.cameraPosition,
        stencilHistogram: enterInside.stencilHistogram,
        stencilNonzero: enterInside.stencilNonzero,
        fillRate: enterInside.fillRate,
        mismatchVsShadowMap: enterMismatch,
      },
    },
    browserErrors,
  };
  await writeFile(join(ARTIFACTS, "results.json"), JSON.stringify(report, null, 2));
  await browser.close();
  await server.close();
  return report;
}
