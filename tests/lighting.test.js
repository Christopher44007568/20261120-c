"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const Lighting = require("../src/lighting.js");

test("solar elevation and azimuth follow a continuous diurnal arc", () => {
  assert.ok(Math.abs(Lighting.solarElevation(6)) < 0.001);
  assert.ok(Math.abs(Lighting.solarElevation(18)) < 0.001);
  assert.ok(Math.abs(Lighting.solarElevation(12) - 58.77) < 0.01);
  assert.ok(Lighting.solarElevation(0) < -58);
  assert.ok(Math.abs(Lighting.solarElevation(0) - Lighting.solarElevation(24)) < 1e-9);
  assert.ok(Math.abs(Lighting.solarAzimuth(6) - 90) < 1e-9);
  assert.ok(Math.abs(Lighting.solarAzimuth(12) - 180) < 1e-9);
  assert.ok(Math.abs(Lighting.solarAzimuth(18) - 270) < 1e-9);
});

test("sunset color, illuminance, and shadow direction are continuous", () => {
  const report = Lighting.validateSunset();
  assert.equal(report.passes, true);
  assert.equal(report.sampleCount, 151);
  assert.ok(report.maxAdjacentColorDelta <= report.thresholds.colorDelta);
  assert.ok(report.maxAdjacentColorDelta <= 8);
  assert.ok(report.maxRelativeLuxStep <= report.thresholds.relativeLuxStep);
  assert.ok(report.maxShadowAzimuthError < 1e-9);
  assert.equal(report.hour18.phase, "sunset");
  assert.ok(report.hour18.globalLux > 0);
});

test("the full 24-hour cycle closes without a color or light seam", () => {
  const report = Lighting.validateCycle();
  assert.equal(report.passes, true);
  assert.equal(report.sampleCount, 1440);
  assert.equal(report.midnightWrapColorDelta, 0);
  assert.ok(report.maxAdjacentColorDelta <= 8);
  assert.ok(report.maxRelativeLuxStep <= 0.3);
  assert.ok(report.sunset.globalLux < report.noon.globalLux / 50);
  assert.ok(report.midnight.globalLux < 1);
});

test("shadow bearing stays exactly opposite the solar bearing", () => {
  for (let minute = 0; minute < 24 * 60; minute += 5) {
    const reading = Lighting.lightingAt(minute / 60);
    const error = Lighting.angularDifference(
      reading.shadowAzimuth,
      reading.azimuth + 180,
    );
    assert.ok(error < 1e-9);
  }
});

test("reported daylight intensity is finite and non-negative at every sample", () => {
  for (let minute = 0; minute <= 24 * 60; minute += 1) {
    const reading = Lighting.lightingAt(minute / 60);
    assert.ok(Number.isFinite(reading.elevation));
    assert.ok(Number.isFinite(reading.globalLux));
    assert.ok(Number.isFinite(reading.irradiance));
    assert.ok(reading.globalLux >= 0);
    assert.ok(reading.irradiance >= 0);
  }
});
