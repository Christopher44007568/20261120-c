(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SimTime = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  function normalizeHour(hour) {
    return ((hour % 24) + 24) % 24;
  }

  const DEFAULT_TIMING = Object.freeze({
    fixedStepSeconds: 1 / 60,
    maxFrameDeltaSeconds: 0.1,
    maxSubsteps: 12,
    defaultSpeed: 0.1,
  });

  function createClock(hour, speed) {
    return {
      hour: normalizeHour(hour ?? 17.75),
      speed: speed ?? DEFAULT_TIMING.defaultSpeed,
      accumulator: 0,
      frameCount: 0,
      simulationSteps: 0,
      droppedSeconds: 0,
      renderedHour: normalizeHour(hour ?? 17.75),
    };
  }

  function advanceClock(clock, frameDeltaSeconds, options) {
    const settings = { ...DEFAULT_TIMING, ...(options || {}) };
    const realDelta = clamp(
      Number.isFinite(frameDeltaSeconds) ? Math.max(frameDeltaSeconds, 0) : 0,
      0,
      settings.maxFrameDeltaSeconds,
    );
    const requested = realDelta + clock.accumulator;
    clock.accumulator = requested;
    clock.frameCount += 1;
    let steps = 0;
    while (
      clock.accumulator + 1e-12 >= settings.fixedStepSeconds &&
      steps < settings.maxSubsteps
    ) {
      clock.hour = normalizeHour(
        clock.hour + settings.fixedStepSeconds * clock.speed,
      );
      clock.accumulator -= settings.fixedStepSeconds;
      clock.simulationSteps += 1;
      steps += 1;
    }
    if (steps === settings.maxSubsteps && clock.accumulator >= settings.fixedStepSeconds) {
      clock.droppedSeconds += clock.accumulator;
      clock.accumulator = 0;
    }
    clock.renderedHour = clock.hour;
    return {
      hour: clock.hour,
      renderedHour: clock.renderedHour,
      steps,
      realDelta,
      advancedHours: steps * settings.fixedStepSeconds * clock.speed,
      rendered: true,
    };
  }

  function advanceByRealSeconds(clock, seconds, options) {
    const settings = { ...DEFAULT_TIMING, ...(options || {}) };
    let remaining = Math.max(seconds, 0);
    let frames = 0;
    while (remaining > 1e-12) {
      const delta = Math.min(remaining, settings.fixedStepSeconds);
      advanceClock(clock, delta, settings);
      remaining -= delta;
      frames += 1;
    }
    return frames;
  }

  function timeRenderRelationship(speed, renderFps) {
    const hoursPerSecond = speed;
    const minutesPerSecond = hoursPerSecond * 60;
    const minutesPerFrame = (minutesPerSecond / renderFps);
    return {
      speedHoursPerSecond: hoursPerSecond,
      minutesPerSecond,
      renderFps,
      minutesPerFrame,
      fullCycleSeconds: 24 / hoursPerSecond,
      description:
        `${minutesPerSecond.toFixed(1)} simulation minutes per real second; ` +
        `at ${renderFps} fps each rendered frame advances ` +
        `${minutesPerFrame.toFixed(2)} simulation minutes.`,
    };
  }

  function simulateSchedule(seconds, speed, framePattern) {
    const clock = createClock(17, speed);
    const pattern = framePattern || [1 / 60, 1 / 60, 1 / 30, 1 / 60];
    let elapsed = 0;
    let index = 0;
    const trace = [];
    while (elapsed < seconds - 1e-9) {
      const delta = Math.min(pattern[index % pattern.length], seconds - elapsed);
      const update = advanceClock(clock, delta);
      trace.push(update);
      elapsed += delta;
      index += 1;
    }
    return { clock, trace };
  }

  return {
    DEFAULT_TIMING,
    createClock,
    advanceClock,
    advanceByRealSeconds,
    timeRenderRelationship,
    simulateSchedule,
    normalizeHour,
  };
});
