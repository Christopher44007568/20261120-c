"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const app = fs.readFileSync(path.join(root, "src", "app.js"), "utf8");

test("every element requested by the app exists in the page", () => {
  const requested = [...app.matchAll(/querySelector\("#([^"]+)"\)/g)].map(
    (match) => match[1],
  );
  const missing = requested.filter((id) => !html.includes(`id="${id}"`));
  assert.deepEqual(missing, []);
  assert.ok(requested.length > 35);
});

test("all runtime modules are local ordinary scripts", () => {
  for (const filename of [
    "./src/lighting.js",
    "./src/routing.js",
    "./src/time.js",
    "./src/app.js",
  ]) {
    assert.match(html, new RegExp(`<script src="${filename.replaceAll(".", "\\.")}"><\\/script>`));
  }
  assert.doesNotMatch(html, /<script[^>]+type="module"/);
  assert.doesNotMatch(html, /<script[^>]+src="https?:/);
  assert.doesNotMatch(html, /<link[^>]+href="https?:\/\/[^"]+\.css/);
});

test("the dashboard exposes the required observation values", () => {
  for (const id of [
    "elevation-value",
    "azimuth-value",
    "global-lux",
    "intensity-value",
    "sunset-status",
    "shadow-error",
    "crossing-count",
    "via-count",
    "via-table-body",
  ]) {
    assert.ok(html.includes(`id="${id}"`), `missing ${id}`);
  }
});
