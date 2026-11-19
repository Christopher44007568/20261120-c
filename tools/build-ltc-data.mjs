import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceUrl =
  "https://raw.githubusercontent.com/mrdoob/three.js/r170/examples/jsm/lights/RectAreaLightTexturesLib.js";
const sourcePath = "/tmp/recttex-r170.js";

execFileSync("curl", ["-L", "--max-time", "30", "-s", sourceUrl, "-o", sourcePath]);

function readArray(source, name) {
  const marker = `const ${name} = [`;
  const start = source.indexOf(marker);
  if (start < 0) throw new Error(`missing ${name}`);
  const valueStart = start + marker.length;
  const end = source.indexOf("]", valueStart);
  const values = source
    .slice(valueStart, end)
    .replace(/\s*-\s*/g, "-")
    .replace(/\s*\+\s*/g, "+")
    .split(",")
    .filter((part) => part.trim())
    .map((part) => Number(part));
  if (values.length !== 64 * 64 * 4) {
    throw new Error(`${name}: expected 16384 values, got ${values.length}`);
  }
  if (values.some((value) => !Number.isFinite(value))) {
    throw new Error(`${name}: contains a non-finite value`);
  }
  return values;
}

const source = readFileSync(sourcePath, "utf8");
const matrix1 = readArray(source, "LTC_MAT_1");
const matrix2 = readArray(source, "LTC_MAT_2");
const data = new Float32Array(matrix1.length + matrix2.length);
data.set(matrix1, 0);
data.set(matrix2, matrix1.length);

const outputPath = resolve(root, "src/ltc-data.bin");
mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, new Uint8Array(data.buffer));

const digest = createHash("sha256")
  .update(new Uint8Array(data.buffer))
  .digest("hex");
console.log(`wrote ${outputPath}`);
console.log(`floats=${data.length} sha256=${digest}`);
