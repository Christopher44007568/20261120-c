"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const SimTime = require("../src/time.js");

test("fixed-step progression keeps simulation time tied to real time", () => {
  const clock = SimTime.createClock(17, 0.1);
  for (let index = 0; index < 600; index += 1) {
    SimTime.advanceClock(clock, 1 / 60);
  }
  assert.ok(Math.abs(clock.hour - 18) < 1e-9);
  assert.equal(clock.simulationSteps, 600);
  assert.equal(clock.frameCount, 600);
  assert.equal(clock.accumulator, 0);
});

test("time wraps continuously at midnight", () => {
  const clock = SimTime.createClock(23.99, 1);
  SimTime.advanceClock(clock, 1 / 60);
  assert.ok(clock.hour >= 0 && clock.hour < 1);
  assert.ok(clock.hour < 0.01);
});

test("large frame gaps are capped instead of jumping the light state", () => {
  const clock = SimTime.createClock(12, 0.1);
  const update = SimTime.advanceClock(clock, 10);
  assert.equal(update.realDelta, SimTime.DEFAULT_TIMING.maxFrameDeltaSeconds);
  assert.ok(clock.hour - 12 < 0.011);
});

test("time-to-render relationship reports minutes per second and frame", () => {
  const relationship = SimTime.timeRenderRelationship(0.1, 60);
  assert.equal(relationship.minutesPerSecond, 6);
  assert.ok(Math.abs(relationship.minutesPerFrame - 0.1) < 1e-12);
  assert.equal(relationship.fullCycleSeconds, 240);
  assert.match(relationship.description, /60 fps/);
});
