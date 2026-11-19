(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SolarLighting = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const RAD = Math.PI / 180;
  const DEG = 180 / Math.PI;

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  function smoothstep(low, high, value) {
    const t = clamp((value - low) / (high - low), 0, 1);
    return t * t * (3 - 2 * t);
  }

  function mix(a, b, t) {
    return a + (b - a) * t;
  }

  function mixColor(a, b, t) {
    return a.map((value, index) => Math.round(mix(value, b[index], t)));
  }

  function normalizeHour(hour) {
    return ((hour % 24) + 24) % 24;
  }

  function normalizeDegrees(angle) {
    return ((angle % 360) + 360) % 360;
  }

  function angularDifference(a, b) {
    const delta = Math.abs(normalizeDegrees(a) - normalizeDegrees(b));
    return Math.min(delta, 360 - delta);
  }

  function formatHour(hour) {
    const minutes = Math.round(normalizeHour(hour) * 60) % 1440;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  }

  function rgbCss(color) {
    return `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
  }

  function rgbHex(color) {
    return `#${color
      .map((value) => clamp(Math.round(value), 0, 255).toString(16).padStart(2, "0"))
      .join("")
      .toUpperCase()}`;
  }

  const OBSERVER = Object.freeze({
    latitude: 31.23,
    longitude: 121.47,
    declination: 0,
    sunrise: 6,
    sunset: 18,
  });

  const PALETTE = Object.freeze([
    { elevation: -35, top: [2, 5, 15], horizon: [5, 9, 21], ambient: [3, 6, 16], sun: [105, 132, 210] },
    { elevation: -18, top: [4, 10, 28], horizon: [11, 18, 41], ambient: [5, 10, 25], sun: [130, 158, 224] },
    { elevation: -10, top: [8, 17, 44], horizon: [27, 29, 57], ambient: [11, 17, 38], sun: [166, 141, 171] },
    { elevation: -5, top: [19, 31, 65], horizon: [72, 48, 70], ambient: [25, 28, 55], sun: [226, 116, 102] },
    { elevation: -1.5, top: [35, 46, 82], horizon: [139, 68, 69], ambient: [52, 43, 66], sun: [255, 126, 77] },
    { elevation: 2, top: [51, 73, 112], horizon: [232, 105, 70], ambient: [110, 70, 67], sun: [255, 157, 88] },
    { elevation: 7, top: [66, 101, 149], horizon: [255, 153, 99], ambient: [176, 117, 103], sun: [255, 198, 135] },
    { elevation: 16, top: [68, 121, 176], horizon: [242, 192, 154], ambient: [188, 180, 169], sun: [255, 232, 200] },
    { elevation: 35, top: [58, 121, 186], horizon: [210, 222, 221], ambient: [180, 203, 211], sun: [255, 244, 224] },
    { elevation: 62, top: [42, 109, 187], horizon: [203, 231, 243], ambient: [183, 216, 233], sun: [255, 247, 234] },
    { elevation: 89, top: [35, 100, 181], horizon: [195, 226, 241], ambient: [178, 211, 230], sun: [255, 249, 239] },
  ]);

  function solarElevation(hour) {
    const latitude = OBSERVER.latitude * RAD;
    const declination = OBSERVER.declination * RAD;
    const hourAngle = (normalizeHour(hour) - 12) * 15 * RAD;
    const sinElevation =
      Math.sin(latitude) * Math.sin(declination) +
      Math.cos(latitude) * Math.cos(declination) * Math.cos(hourAngle);
    return Math.asin(clamp(sinElevation, -1, 1)) * DEG;
  }

  function solarAzimuth(hour) {
    const latitude = OBSERVER.latitude * RAD;
    const declination = OBSERVER.declination * RAD;
    const hourAngle = (normalizeHour(hour) - 12) * 15 * RAD;
    const x = Math.sin(hourAngle);
    const y =
      Math.cos(hourAngle) * Math.sin(latitude) -
      Math.tan(declination) * Math.cos(latitude);
    return normalizeDegrees(Math.atan2(x, y) * DEG + 180);
  }

  function sunDirection(elevation, azimuth) {
    const altitude = elevation * RAD;
    const bearing = azimuth * RAD;
    const horizontal = Math.cos(altitude);
    return {
      x: horizontal * Math.sin(bearing),
      y: Math.sin(altitude),
      z: horizontal * Math.cos(bearing),
    };
  }

  function airMass(elevation) {
    if (elevation <= -1) return 38;
    const altitude = Math.max(elevation, 0);
    if (altitude >= 89.5) return 1;
    const denominator =
      Math.sin(altitude * RAD) +
      0.50572 * Math.pow(altitude + 6.07995, -1.6364);
    return clamp(1 / denominator, 1, 38);
  }

  function interpolatePalette(elevation) {
    if (elevation <= PALETTE[0].elevation) return PALETTE[0];
    if (elevation >= PALETTE[PALETTE.length - 1].elevation) {
      return PALETTE[PALETTE.length - 1];
    }
    for (let index = 0; index < PALETTE.length - 1; index += 1) {
      const low = PALETTE[index];
      const high = PALETTE[index + 1];
      if (elevation <= high.elevation) {
        const t = clamp(
          (elevation - low.elevation) / (high.elevation - low.elevation),
          0,
          1,
        );
        return {
          elevation,
          top: mixColor(low.top, high.top, t),
          horizon: mixColor(low.horizon, high.horizon, t),
          ambient: mixColor(low.ambient, high.ambient, t),
          sun: mixColor(low.sun, high.sun, t),
        };
      }
    }
    return PALETTE[PALETTE.length - 1];
  }

  function paletteSignature(palette) {
    return [palette.top, palette.horizon, palette.ambient, palette.sun]
      .flat()
      .join(",");
  }

  function lightingAt(hour) {
    const normalizedHour = normalizeHour(hour);
    const elevation = solarElevation(normalizedHour);
    const azimuth = solarAzimuth(normalizedHour);
    const direction = sunDirection(elevation, azimuth);
    const palette = interpolatePalette(elevation);
    const azimuthWarmth = clamp(
      (0.5 + 0.5 * Math.cos((azimuth - 270) * RAD)) *
        smoothstep(-15, 0, elevation) *
        (1 - smoothstep(12, 34, elevation)),
      0,
      1,
    );
    const topColor = mixColor(palette.top, [66, 76, 105], azimuthWarmth * 0.08);
    const horizonColor = mixColor(
      palette.horizon,
      [255, 158, 112],
      azimuthWarmth * 0.14,
    );
    const ambientColor = mixColor(
      palette.ambient,
      [126, 86, 74],
      azimuthWarmth * 0.1,
    );
    const sunColor = mixColor(palette.sun, [255, 176, 104], azimuthWarmth * 0.08);
    const dayFactor = smoothstep(-8, 7, elevation);
    const twilight = Math.exp(-Math.pow((elevation + 1.2) / 5.3, 2));
    const mass = airMass(elevation);
    const directVisibility = smoothstep(-0.9, 1.8, elevation);
    const directLux =
      108000 *
      Math.exp(-0.18 * Math.max(mass - 1, 0)) *
      directVisibility;
    const diffuseLux =
      7600 * Math.pow(Math.max(Math.sin(elevation * RAD), 0), 0.72) +
      780 * twilight +
      0.16;
    const moonLux = 0.28 * (1 - dayFactor);
    const globalLux = directLux * Math.max(Math.sin(elevation * RAD), 0.025) +
      diffuseLux + moonLux;
    const irradiance =
      1050 *
      Math.max(Math.sin(elevation * RAD), 0) *
      Math.exp(-0.12 * Math.max(mass - 1, 0));
    const shadowAzimuth = normalizeDegrees(azimuth + 180);
    const shadowLength = clamp(1.25 / Math.max(Math.sin(elevation * RAD), 0.06), 0.8, 24);
    let phase = "night";
    if (elevation >= 18) phase = "day";
    else if (elevation >= 4) phase = "golden";
    else if (elevation >= -0.8) phase = "sunset";
    else if (elevation >= -8) phase = "twilight";

    return {
      hour: normalizedHour,
      timeLabel: formatHour(normalizedHour),
      elevation,
      azimuth,
      direction,
      shadowAzimuth,
      shadowLength,
      dayFactor,
      twilight,
      airMass: mass,
      directLux,
      diffuseLux,
      globalLux,
      moonLux,
      irradiance,
      intensityPercent: clamp((globalLux / 120000) * 100, 0, 100),
      phase,
      azimuthWarmth,
      topColor,
      horizonColor,
      ambientColor,
      sunColor,
      topCss: rgbCss(topColor),
      horizonCss: rgbCss(horizonColor),
      ambientCss: rgbCss(ambientColor),
      sunCss: rgbCss(sunColor),
      topHex: rgbHex(topColor),
      horizonHex: rgbHex(horizonColor),
      ambientHex: rgbHex(ambientColor),
      sunHex: rgbHex(sunColor),
    };
  }

  function maxColorDelta(a, b) {
    return Math.max(
      ...a.topColor.map((value, index) => Math.abs(value - b.topColor[index])),
      ...a.horizonColor.map((value, index) => Math.abs(value - b.horizonColor[index])),
    );
  }

  function sampleWindow(startHour, endHour, stepMinutes) {
    const rows = [];
    const step = stepMinutes / 60;
    for (let hour = startHour; hour <= endHour + 1e-9; hour += step) {
      rows.push(lightingAt(hour));
    }
    return rows;
  }

  function validateSunset(options) {
    const settings = {
      startHour: 17,
      endHour: 19.5,
      stepMinutes: 1,
      maxColorDelta: 8,
      maxLuxRelativeStep: 0.3,
      maxShadowError: 0.001,
      ...(options || {}),
    };
    const rows = sampleWindow(settings.startHour, settings.endHour, settings.stepMinutes);
    let colorDelta = 0;
    let colorSample = null;
    let luxRelative = 0;
    let luxSample = null;
    let shadowError = 0;
    for (let index = 1; index < rows.length; index += 1) {
      const previous = rows[index - 1];
      const current = rows[index];
      const delta = maxColorDelta(previous, current);
      if (delta > colorDelta) {
        colorDelta = delta;
        colorSample = { from: previous.timeLabel, to: current.timeLabel };
      }
      const luxBase = Math.max(previous.globalLux, current.globalLux, 1);
      const luxDelta = Math.abs(current.globalLux - previous.globalLux) / luxBase;
      if (luxDelta > luxRelative) {
        luxRelative = luxDelta;
        luxSample = { from: previous.timeLabel, to: current.timeLabel };
      }
      shadowError = Math.max(
        shadowError,
        angularDifference(current.shadowAzimuth, current.azimuth + 180),
      );
    }
    const passes =
      colorDelta <= settings.maxColorDelta &&
      luxRelative <= settings.maxLuxRelativeStep &&
      shadowError <= settings.maxShadowError;
    return {
      passes,
      sampleCount: rows.length,
      stepMinutes: settings.stepMinutes,
      window: [settings.startHour, settings.endHour],
      maxAdjacentColorDelta: colorDelta,
      colorDeltaSample: colorSample,
      maxRelativeLuxStep: luxRelative,
      luxStepSample: luxSample,
      maxShadowAzimuthError: shadowError,
      thresholds: {
        colorDelta: settings.maxColorDelta,
        relativeLuxStep: settings.maxLuxRelativeStep,
        shadowAzimuthError: settings.maxShadowError,
      },
      hour18: lightingAt(18),
    };
  }

  function validateCycle(options) {
    const settings = {
      stepMinutes: 1,
      maxColorDelta: 9,
      maxLuxRelativeStep: 0.42,
      maxShadowError: 0.001,
      ...(options || {}),
    };
    const rows = [];
    for (let minute = 0; minute < 24 * 60; minute += settings.stepMinutes) {
      rows.push(lightingAt(minute / 60));
    }
    let maxColor = 0;
    let maxLux = 0;
    let maxShadow = 0;
    let colorBoundary = null;
    let luxBoundary = null;
    for (let index = 0; index < rows.length; index += 1) {
      const previous = rows[index];
      const current = rows[(index + 1) % rows.length];
      const delta = maxColorDelta(previous, current);
      if (delta > maxColor) {
        maxColor = delta;
        colorBoundary = { from: previous.timeLabel, to: current.timeLabel };
      }
      const luxBase = Math.max(previous.globalLux, current.globalLux, 1);
      const luxDelta = Math.abs(current.globalLux - previous.globalLux) / luxBase;
      if (luxDelta > maxLux) {
        maxLux = luxDelta;
        luxBoundary = { from: previous.timeLabel, to: current.timeLabel };
      }
      maxShadow = Math.max(
        maxShadow,
        angularDifference(current.shadowAzimuth, current.azimuth + 180),
      );
    }
    const wrap = maxColorDelta(rows[rows.length - 1], rows[0]);
    return {
      passes:
        maxColor <= settings.maxColorDelta &&
        maxLux <= settings.maxLuxRelativeStep &&
        maxShadow <= settings.maxShadowError,
      sampleCount: rows.length,
      stepMinutes: settings.stepMinutes,
      maxAdjacentColorDelta: maxColor,
      colorBoundary,
      maxRelativeLuxStep: maxLux,
      luxBoundary,
      maxShadowAzimuthError: maxShadow,
      midnightWrapColorDelta: wrap,
      sunrise: lightingAt(6),
      noon: lightingAt(12),
      sunset: lightingAt(18),
      midnight: lightingAt(0),
      thresholds: {
        colorDelta: settings.maxColorDelta,
        relativeLuxStep: settings.maxLuxRelativeStep,
        shadowAzimuthError: settings.maxShadowError,
      },
    };
  }

  function cycleSeries(stepMinutes) {
    const step = stepMinutes || 15;
    const rows = [];
    for (let minute = 0; minute <= 24 * 60; minute += step) {
      const reading = lightingAt(minute / 60);
      rows.push({
        hour: reading.hour,
        elevation: reading.elevation,
        azimuth: reading.azimuth,
        directLux: reading.directLux,
        globalLux: reading.globalLux,
        irradiance: reading.irradiance,
        topHex: reading.topHex,
        horizonHex: reading.horizonHex,
        shadowAzimuth: reading.shadowAzimuth,
        phase: reading.phase,
      });
    }
    return rows;
  }

  return {
    OBSERVER,
    PALETTE,
    clamp,
    smoothstep,
    mix,
    mixColor,
    normalizeHour,
    normalizeDegrees,
    angularDifference,
    formatHour,
    rgbCss,
    rgbHex,
    solarElevation,
    solarAzimuth,
    sunDirection,
    airMass,
    interpolatePalette,
    paletteSignature,
    lightingAt,
    maxColorDelta,
    sampleWindow,
    validateSunset,
    validateCycle,
    cycleSeries,
  };
});
