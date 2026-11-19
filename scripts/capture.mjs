import { runE2E } from "./e2e.mjs";

const report = await runE2E({ screenshots: true });
console.log(`Captured ${Object.keys(report.scenarios).length} scenarios to artifacts/final/results.json`);
