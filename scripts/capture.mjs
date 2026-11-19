import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { chromium } from 'playwright-core';

const artifacts = resolve('artifacts');
mkdirSync(artifacts, { recursive: true });
const port = 43817;
const base = `http://127.0.0.1:${port}`;

function findChromium() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const caches = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    process.env.HOME && join(process.env.HOME, '.cache/ms-playwright'),
    '/home/hj/.cache/ms-playwright'
  ].filter(Boolean);
  for (const cache of caches) {
    if (!existsSync(cache)) continue;
    const directories = readdirSync(cache)
      .filter((name) => name.startsWith('chromium-'))
      .sort()
      .reverse();
    for (const directory of directories) {
      for (const candidate of [
        join(cache, directory, 'chrome-linux64/chrome'),
        join(cache, directory, 'chrome-linux/chrome')
      ]) {
        if (existsSync(candidate)) return candidate;
      }
    }
  }
  return null;
}

const allScenarios = [
  { name: 'default', query: '?sunElevation=14' },
  { name: 'noon', query: '?sunElevation=62' },
  { name: 'sunset', query: '?sunElevation=2' },
  { name: 'clear', query: '?sunElevation=14&cloudCoverage=0' },
  { name: 'clouds-shadow', query: '?sunElevation=24&cloudCoverage=0.78&cloudThickness=2.2' },
  { name: 'clouds-no-shadow', query: '?sunElevation=24&cloudCoverage=0.78&cloudThickness=2.2&cloudShadows=0' }
];
const requested = process.env.CAPTURE_ONLY?.split(',').filter(Boolean);
const scenarios = requested
  ? allScenarios.filter((scenario) => requested.includes(scenario.name))
  : allScenarios;

const server = spawn(process.execPath, ['scripts/serve.mjs'], {
  cwd: process.cwd(),
  env: { ...process.env, PORT: String(port) },
  stdio: ['ignore', 'pipe', 'pipe']
});
await new Promise((resolvePromise, reject) => {
  const timer = setTimeout(() => reject(new Error('Server start timed out')), 5000);
  server.stdout.on('data', (chunk) => {
    if (chunk.toString().includes('ATMOS sky lab')) {
      clearTimeout(timer);
      resolvePromise();
    }
  });
  server.stderr.on('data', (chunk) => process.stderr.write(chunk));
  server.on('exit', (code) => reject(new Error(`Server exited with ${code}`)));
});

const executablePath = findChromium();
if (!executablePath) throw new Error('Chromium was not found');

const browser = await chromium.launch({
  executablePath,
  headless: true,
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
    '--ignore-gpu-blocklist'
  ]
});

try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1
  });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  for (const scenario of scenarios) {
    await page.goto(`${base}/${scenario.query}`, { waitUntil: 'networkidle' });
    await page.waitForFunction(() =>
      document.querySelector('#sky-canvas')?.dataset.pixels, null, { timeout: 15000 });
    await page.waitForTimeout(900);
    await page.screenshot({
      path: join(artifacts, `preview-${scenario.name}.png`),
      fullPage: false
    });
    const canvasData = await page.evaluate(() =>
      document.querySelector('#sky-canvas').toDataURL('image/png'));
    writeFileSync(
      join(artifacts, `canvas-${scenario.name}.png`),
      Buffer.from(canvasData.split(',')[1], 'base64')
    );
    console.log(`${scenario.name}: ${await page.locator('#sky-canvas').getAttribute('data-pixels')}`);
  }
  if (errors.length) console.error(errors.join('\n'));
} finally {
  await browser.close();
  server.kill('SIGTERM');
}
