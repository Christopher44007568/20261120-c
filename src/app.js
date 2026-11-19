(function () {
  "use strict";

  const Lighting = window.SolarLighting;
  const Routing = window.PcbRouting;
  const SimTime = window.SimTime;
  const canvas = document.querySelector("#scene-canvas");
  const ctx = canvas.getContext("2d");
  const routeReport = Routing.buildRoutingReport();
  const sunsetReport = Lighting.validateSunset();
  const cycleReport = Lighting.validateCycle();
  const clock = SimTime.createClock(17.75, 0.1);
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const state = {
    paused: reducedMotion,
    speed: 0.1,
    fps: 60,
    activeLayer: 0,
    lastUiUpdate: 0,
    lastFrame: performance.now(),
    frameCount: 0,
    toastTimer: 0,
    stars: makeStars(135),
  };

  const el = {
    clock: document.querySelector("#clock-value"),
    play: document.querySelector("#play-button"),
    range: document.querySelector("#time-range"),
    fill: document.querySelector("#timeline-fill"),
    pin: document.querySelector("#sun-pin"),
    speed: document.querySelector("#speed-select"),
    elevation: document.querySelector("#elevation-value"),
    azimuth: document.querySelector("#azimuth-value"),
    globalLux: document.querySelector("#global-lux"),
    intensity: document.querySelector("#intensity-value"),
    meter: document.querySelector("#light-meter"),
    directLux: document.querySelector("#direct-lux"),
    irradiance: document.querySelector("#irradiance-value"),
    ambientHex: document.querySelector("#ambient-hex"),
    sunVector: document.querySelector("#sun-vector"),
    phase: document.querySelector("#phase-chip"),
    topHex: document.querySelector("#top-hex"),
    horizonHex: document.querySelector("#horizon-hex"),
    sunHex: document.querySelector("#sun-hex"),
    topSwatch: document.querySelector("#top-swatch"),
    horizonSwatch: document.querySelector("#horizon-swatch"),
    sunSwatch: document.querySelector("#sun-swatch"),
    skyPreview: document.querySelector("#sky-preview"),
    skySun: document.querySelector("#sky-sun"),
    sunsetStrip: document.querySelector("#sunset-strip"),
    sunsetStatus: document.querySelector("#sunset-status"),
    colorDelta: document.querySelector("#color-delta"),
    shadowError: document.querySelector("#shadow-error"),
    luxDelta: document.querySelector("#lux-delta"),
    wrapDelta: document.querySelector("#wrap-delta"),
    continuityNote: document.querySelector("#continuity-note"),
    shadowBearing: document.querySelector("#shadow-bearing"),
    needle: document.querySelector("#compass-needle"),
    routeStatus: document.querySelector("#route-status"),
    routedNets: document.querySelector("#routed-nets"),
    crossingCount: document.querySelector("#crossing-count"),
    viaCount: document.querySelector("#via-count"),
    viaTable: document.querySelector("#via-table-body"),
    routeProof: document.querySelector("#route-proof"),
    layerLegend: document.querySelector("#layer-legend"),
    timingDescription: document.querySelector("#timing-description"),
    timingExample: document.querySelector("#timing-example"),
    frameCount: document.querySelector("#frame-count"),
    stepCount: document.querySelector("#step-count"),
    renderState: document.querySelector("#render-state"),
    toast: document.querySelector("#toast"),
  };

  function makeStars(count) {
    let seed = 65065;
    const random = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 4294967296;
    };
    return Array.from({ length: count }, () => ({
      x: random(),
      y: random() * 0.52,
      size: 0.35 + random() * 1.35,
      phase: random() * Math.PI * 2,
      brightness: 0.25 + random() * 0.75,
    }));
  }

  function formatLux(value) {
    if (value >= 100000) return `${(value / 1000).toFixed(0)} klx`;
    if (value >= 1000) return `${(value / 1000).toFixed(1)} klx`;
    if (value >= 100) return `${Math.round(value)} lx`;
    if (value >= 1) return `${value.toFixed(1)} lx`;
    return `${value.toFixed(2)} lx`;
  }

  function phaseLabel(phase) {
    return {
      day: "DAY / 白昼",
      golden: "GOLDEN / 金色",
      sunset: "SUNSET / 日落",
      twilight: "TWILIGHT / 暮光",
      night: "NIGHT / 夜间",
    }[phase];
  }

  function showToast(message) {
    el.toast.textContent = message;
    el.toast.classList.add("visible");
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => {
      el.toast.classList.remove("visible");
    }, 1800);
  }

  function syncPlayButton() {
    el.play.classList.toggle("paused", state.paused);
    el.play.setAttribute("aria-label", state.paused ? "继续时间" : "暂停时间");
  }

  function buildStaticPanels() {
    el.routedNets.textContent = `${routeReport.routedNets}/${routeReport.totalNets}`;
    el.crossingCount.textContent = String(routeReport.crossings);
    el.viaCount.textContent = String(routeReport.viaCount);
    el.routeStatus.textContent = routeReport.passes ? "PASS" : "CHECK";
    el.routeProof.textContent =
      `交叉下界 ${routeReport.crossingLowerBound} · 当前 ${routeReport.crossings} · ` +
      (routeReport.minimumCrossingsProven ? "全局最少" : "待优化");

    el.sunsetStatus.textContent = sunsetReport.passes ? "PASS" : "CHECK";
    el.colorDelta.textContent = sunsetReport.maxAdjacentColorDelta.toFixed(0);
    el.shadowError.textContent = sunsetReport.maxShadowAzimuthError.toFixed(3);
    el.luxDelta.textContent = (sunsetReport.maxRelativeLuxStep * 100).toFixed(1);
    el.wrapDelta.textContent = cycleReport.midnightWrapColorDelta.toFixed(0);
    el.continuityNote.textContent =
      `${sunsetReport.sampleCount} 个 1 分钟样本；` +
      `颜色连续 ${sunsetReport.passes ? "PASS" : "CHECK"}，` +
      `太阳 → 阴影 180° 同步误差 ${sunsetReport.maxShadowAzimuthError.toFixed(3)}°。`;

    for (let index = 0; index < 23; index += 1) {
      const reading = Lighting.lightingAt(17 + (index / 22) * 2.5);
      const swatch = document.createElement("i");
      swatch.style.background = `linear-gradient(${reading.topHex}, ${reading.horizonHex})`;
      swatch.title = `${reading.timeLabel} · ${reading.elevation.toFixed(1)}°`;
      el.sunsetStrip.append(swatch);
    }

    const layerButtons = [];
    for (const layer of routeReport.layers) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.layer = layer.index;
      button.style.setProperty("--layer-color", layer.color);
      button.innerHTML = `<i></i>${layer.name}`;
      button.title = layer.label;
      button.addEventListener("click", () => {
        if (state.activeLayer === layer.index) {
          state.activeLayer = -1;
          showToast("显示全部铜层");
        } else {
          state.activeLayer = layer.index;
          showToast(`${layer.label} 单独高亮`);
        }
        layerButtons.forEach((item) => {
          item.classList.toggle(
            "active",
            Number(item.dataset.layer) === state.activeLayer,
          );
        });
      });
      layerButtons.push(button);
      el.layerLegend.append(button);
    }

    for (const via of routeReport.vias) {
      const row = document.createElement("div");
      row.className = "via-row";
      row.style.setProperty(
        "--net-color",
        routeReport.nets.find((net) => net.name === via.net)?.color || "#fff",
      );
      row.innerHTML =
        `<span class="via-main"><b>${via.net}</b>` +
        `<span>${String(via.x).padStart(2, "0")},${String(via.y).padStart(2, "0")}</span></span>` +
        `<span class="via-layer">${via.fromLayerName}→${via.toLayerName}</span>` +
        `<em>OK</em>`;
      el.viaTable.append(row);
    }
  }

  function updateReadouts(reading) {
    el.clock.textContent = reading.timeLabel;
    el.elevation.textContent = reading.elevation.toFixed(1);
    el.azimuth.textContent = Math.round(reading.azimuth);
    el.globalLux.textContent = formatLux(reading.globalLux);
    el.intensity.textContent = `${reading.intensityPercent.toFixed(1)}%`;
    el.meter.style.width = `${Math.max(reading.intensityPercent, 0.5)}%`;
    el.directLux.textContent = formatLux(reading.directLux);
    el.irradiance.textContent = `${reading.irradiance.toFixed(0)} W/m²`;
    el.ambientHex.textContent = reading.ambientHex;
    el.sunVector.textContent =
      `${reading.direction.x.toFixed(3)}, ${reading.direction.y.toFixed(3)}, ` +
      `${reading.direction.z.toFixed(3)}`;
    el.sunVector.textContent = el.sunVector.textContent.replaceAll("-", "−");
    el.phase.textContent = phaseLabel(reading.phase);
    el.shadowBearing.textContent = `${String(Math.round(reading.shadowAzimuth)).padStart(3, "0")}°`;
    el.needle.style.transform =
      `translateX(-50%) rotate(${reading.shadowAzimuth}deg)`;

    el.topHex.textContent = reading.topHex;
    el.horizonHex.textContent = reading.horizonHex;
    el.sunHex.textContent = reading.sunHex;
    el.topSwatch.style.background = reading.topCss;
    el.horizonSwatch.style.background = reading.horizonCss;
    el.sunSwatch.style.background = reading.sunCss;
    el.skyPreview.style.background =
      `linear-gradient(${reading.topHex}, ${reading.horizonHex})`;
    el.skySun.style.background = reading.sunCss;
    el.skySun.style.boxShadow = `0 0 18px 5px ${reading.sunCss}`;
    el.skySun.style.opacity = String(
      Lighting.clamp((reading.elevation + 8) / 20, 0.06, 1),
    );
    el.skySun.style.right = `${20 + (reading.azimuth / 360) * 60}%`;
    el.skySun.style.top = `${32 - Lighting.clamp(reading.elevation, 0, 60) * 0.22}px`;

    el.range.value = String(reading.hour);
    const progress = (reading.hour / 24) * 100;
    el.fill.style.width = `${progress}%`;
    el.pin.style.left = `${progress}%`;
    document.querySelectorAll("[data-hour]").forEach((button) => {
      const target = Number(button.dataset.hour);
      button.classList.toggle(
        "active",
        Math.abs(target - reading.hour) < 0.08,
      );
    });
  }

  function updateTiming() {
    const relationship = SimTime.timeRenderRelationship(state.speed, state.fps);
    const secondsPerMinute = 1 / Math.max(relationship.minutesPerSecond, 1e-9);
    el.timingDescription.textContent =
      `${relationship.minutesPerSecond.toFixed(1)} 分钟 / 秒 · ` +
      `${state.fps.toFixed(0)} FPS`;
    el.timingExample.textContent =
      `1 分钟 = ${secondsPerMinute < 10 ? secondsPerMinute.toFixed(1) : Math.round(secondsPerMinute)} 秒`;
    el.frameCount.textContent = String(state.frameCount).padStart(6, "0");
    el.stepCount.textContent = String(clock.simulationSteps).padStart(6, "0");
    el.renderState.textContent = state.paused
      ? "FIXED TIME"
      : `LIVE · ${state.fps.toFixed(0)} FPS`;
  }

  function setHour(hour, message) {
    clock.hour = Lighting.normalizeHour(hour);
    clock.accumulator = 0;
    state.lastUiUpdate = 0;
    if (message) showToast(message);
  }

  function setPaused(paused) {
    state.paused = paused;
    syncPlayButton();
    showToast(paused ? "时间已暂停" : "时间继续推进");
  }

  function bindControls() {
    el.play.addEventListener("click", () => setPaused(!state.paused));
    el.range.addEventListener("input", () => {
      setHour(Number(el.range.value));
    });
    el.speed.addEventListener("change", () => {
      state.speed = Number(el.speed.value);
      clock.speed = state.speed;
      updateTiming();
      showToast(el.speed.selectedOptions[0].textContent);
    });
    document.querySelectorAll("[data-hour]").forEach((button) => {
      button.addEventListener("click", () => {
        setHour(Number(button.dataset.hour), button.textContent);
      });
    });
    window.addEventListener("keydown", (event) => {
      if (event.code === "Space" && event.target === document.body) {
        event.preventDefault();
        setPaused(!state.paused);
      }
      if (event.key === "ArrowLeft") setHour(clock.hour - 0.25);
      if (event.key === "ArrowRight") setHour(clock.hour + 0.25);
    });
    document.addEventListener("visibilitychange", () => {
      state.lastFrame = performance.now();
    });
  }

  function rgba(color, alpha) {
    return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})`;
  }

  function shade(color, factor) {
    return color.map((value) => Lighting.clamp(Math.round(value * factor), 0, 255));
  }

  function sceneLayout() {
    const width = window.innerWidth;
    const height = window.innerHeight;
    const inspectorWidth =
      width > 1180 ? 423 : width > 900 ? 375 : width > 650 ? width * 0.48 : 0;
    const leftWidth = Math.max(width - inspectorWidth, 480);
    const minimumBoardWidth = width < 650 ? 280 : 445;
    const boardWidth = Lighting.clamp(leftWidth * 0.78, minimumBoardWidth, 760);
    return {
      width,
      height,
      inspectorWidth,
      horizonY: height * 0.505,
      board: {
        width: boardWidth,
        height: boardWidth * 0.56,
        centerX: Math.max(leftWidth * 0.53, boardWidth * 0.55 + 28),
        top: Math.max(height * 0.31, 220),
      },
    };
  }

  function projectCell(layer, x, y, layout) {
    const u = (x + 0.5) / Routing.BOARD.width;
    const v = (y + 0.5) / Routing.BOARD.height;
    const board = layout.board;
    const spread = 0.84 + v * 0.16;
    const layerShift = layer * 0.7;
    return {
      x: board.centerX + (u - 0.5) * board.width * spread + layerShift,
      y: board.top + v * board.height - layerShift * 0.3,
    };
  }

  function boardPolygon(layout, offsetX, offsetY, inset) {
    const board = layout.board;
    const pad = inset || 0;
    return [
      [board.centerX - board.width * 0.42 + pad + offsetX, board.top + pad + offsetY],
      [board.centerX + board.width * 0.42 - pad + offsetX, board.top + pad + offsetY],
      [board.centerX + board.width * 0.5 - pad + offsetX, board.top + board.height - pad + offsetY],
      [board.centerX - board.width * 0.5 + pad + offsetX, board.top + board.height - pad + offsetY],
    ];
  }

  function drawPolygon(points, fill, stroke) {
    ctx.beginPath();
    points.forEach(([x, y], index) => {
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    if (fill) {
      ctx.fillStyle = fill;
      ctx.fill();
    }
    if (stroke) {
      ctx.strokeStyle = stroke;
      ctx.stroke();
    }
  }

  function drawSky(reading, layout, time) {
    const { width, height, horizonY } = layout;
    const sky = ctx.createLinearGradient(0, 0, 0, horizonY + 35);
    sky.addColorStop(0, reading.topCss);
    sky.addColorStop(0.72, Lighting.rgbCss(
      Lighting.mixColor(reading.topColor, reading.horizonColor, 0.52),
    ));
    sky.addColorStop(1, reading.horizonCss);
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, width, horizonY + 35);

    const starAlpha = (1 - reading.dayFactor) * (1 - reading.twilight * 0.45);
    if (starAlpha > 0.02) {
      for (const star of state.stars) {
        const twinkle = 0.7 + Math.sin(time * 0.0007 + star.phase) * 0.3;
        ctx.globalAlpha = starAlpha * star.brightness * twinkle;
        ctx.fillStyle = "#eaf7ff";
        ctx.fillRect(star.x * width, star.y * horizonY, star.size, star.size);
      }
      ctx.globalAlpha = 1;
    }

    const sunX =
      width * 0.05 +
      (width - layout.inspectorWidth * 0.82) * 0.46 +
      Math.sin(((reading.azimuth - 180) * Math.PI) / 180) *
        (width - layout.inspectorWidth) *
        0.41;
    const sunY =
      horizonY -
      Math.sin(Lighting.clamp(reading.elevation, -12, 78) * (Math.PI / 180)) *
        height *
        0.55;
    const sunVisible = reading.elevation > -9;
    if (sunVisible) {
      const glow = ctx.createRadialGradient(sunX, sunY, 0, sunX, sunY, 118);
      const glowAlpha = Lighting.clamp(0.58 - Math.abs(reading.elevation) / 120, 0.16, 0.55);
      glow.addColorStop(0, rgba(reading.sunColor, glowAlpha));
      glow.addColorStop(0.18, rgba(reading.sunColor, glowAlpha * 0.48));
      glow.addColorStop(1, rgba(reading.sunColor, 0));
      ctx.fillStyle = glow;
      ctx.fillRect(sunX - 120, sunY - 120, 240, 240);
      ctx.beginPath();
      ctx.arc(sunX, sunY, 10 + Lighting.clamp(reading.twilight * 4, 0, 4), 0, Math.PI * 2);
      ctx.fillStyle = Lighting.rgbCss(reading.sunColor);
      ctx.shadowColor = rgba(reading.sunColor, 0.8);
      ctx.shadowBlur = 26;
      ctx.fill();
      ctx.shadowBlur = 0;
    }

    if (reading.dayFactor < 0.45) {
      const moonAzimuth = Lighting.normalizeDegrees(reading.azimuth + 180);
      const moonX =
        width * 0.05 +
        (width - layout.inspectorWidth * 0.82) * 0.46 +
        Math.sin(((moonAzimuth - 180) * Math.PI) / 180) *
          (width - layout.inspectorWidth) *
          0.4;
      const moonY = horizonY - height * (0.24 + (1 - reading.dayFactor) * 0.12);
      const moonAlpha = (1 - reading.dayFactor) * 0.82;
      ctx.globalAlpha = moonAlpha;
      const moonGlow = ctx.createRadialGradient(moonX, moonY, 1, moonX, moonY, 55);
      moonGlow.addColorStop(0, "rgba(203,225,255,.32)");
      moonGlow.addColorStop(1, "rgba(203,225,255,0)");
      ctx.fillStyle = moonGlow;
      ctx.fillRect(moonX - 55, moonY - 55, 110, 110);
      ctx.beginPath();
      ctx.arc(moonX, moonY, 7, 0, Math.PI * 2);
      ctx.fillStyle = "#d6e7ff";
      ctx.fill();
      ctx.beginPath();
      ctx.arc(moonX + 3, moonY - 1, 6.5, 0, Math.PI * 2);
      ctx.fillStyle = reading.topCss;
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    drawCloudBands(reading, layout);
    drawGround(reading, layout);
    drawSkyline(reading, layout);
  }

  function drawCloudBands(reading, layout) {
    const { width, horizonY } = layout;
    const cloudAlpha = 0.08 + reading.twilight * 0.16 + (1 - reading.dayFactor) * 0.02;
    const cloudColor = Lighting.mixColor(
      reading.horizonColor,
      reading.ambientColor,
      reading.dayFactor * 0.45,
    );
    ctx.save();
    for (let index = 0; index < 5; index += 1) {
      const bandWidth = width * (0.2 + index * 0.035);
      const x = width * (0.08 + index * 0.18) + Math.sin(index * 12.1) * 40;
      const y = horizonY - 72 - index * 12 + Math.cos(index * 5.2) * 13;
      const gradient = ctx.createRadialGradient(x, y, 2, x, y, bandWidth * 0.55);
      gradient.addColorStop(0, rgba(cloudColor, cloudAlpha * 0.72));
      gradient.addColorStop(0.55, rgba(cloudColor, cloudAlpha * 0.34));
      gradient.addColorStop(1, rgba(cloudColor, 0));
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.ellipse(x, y, bandWidth * 0.55, 18 + index * 1.5, -0.04, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function drawGround(reading, layout) {
    const { width, height, horizonY } = layout;
    const groundTop = Lighting.mixColor(
      reading.horizonColor,
      reading.ambientColor,
      0.48,
    );
    const groundBottom = shade(reading.ambientColor, 0.18);
    const ground = ctx.createLinearGradient(0, horizonY - 2, 0, height);
    ground.addColorStop(0, rgba(groundTop, 0.8));
    ground.addColorStop(0.22, rgba(shade(groundTop, 0.42), 0.95));
    ground.addColorStop(1, rgba(groundBottom, 1));
    ctx.fillStyle = ground;
    ctx.fillRect(0, horizonY - 1, width, height - horizonY + 1);

    const haze = ctx.createLinearGradient(0, horizonY - 25, 0, horizonY + 80);
    haze.addColorStop(0, rgba(reading.horizonColor, 0.08 + reading.twilight * 0.12));
    haze.addColorStop(1, rgba(reading.horizonColor, 0));
    ctx.fillStyle = haze;
    ctx.fillRect(0, horizonY - 25, width, 110);

    ctx.strokeStyle = rgba(reading.horizonColor, 0.14);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, horizonY);
    ctx.lineTo(width, horizonY);
    ctx.stroke();
  }

  function drawSkyline(reading, layout) {
    const { width, horizonY } = layout;
    const silhouette = shade(reading.ambientColor, 0.2);
    ctx.fillStyle = rgba(silhouette, 0.88);
    ctx.beginPath();
    ctx.moveTo(0, horizonY);
    for (let x = 0; x <= width; x += 22) {
      const mountain =
        Math.sin(x * 0.013 + 2.1) * 9 +
        Math.sin(x * 0.031 + 0.7) * 4 +
        Math.sin(x * 0.006) * 12;
      ctx.lineTo(x, horizonY - 5 - Math.max(mountain, -2));
    }
    ctx.lineTo(width, horizonY);
    ctx.closePath();
    ctx.fill();

    for (let index = 0; index < 37; index += 1) {
      const x = (index / 37) * width + ((index * 17) % 13);
      const height = 4 + ((index * 31) % 19);
      const widthUnit = 7 + ((index * 11) % 12);
      ctx.fillRect(x, horizonY - height, widthUnit, height + 2);
    }

    const litAlpha = reading.dayFactor * 0.08 + (1 - reading.dayFactor) * 0.4;
    ctx.fillStyle = rgba(reading.sunColor, litAlpha);
    for (let index = 0; index < 18; index += 1) {
      const x = ((index * 83) % 97) / 97 * width;
      const y = horizonY - 5 - ((index * 13) % 11);
      ctx.fillRect(x, y, 1.4, 1.4);
    }
  }

  function projectUV(u, v, layout, layer) {
    const board = layout.board;
    const spread = 0.84 + v * 0.16;
    return {
      x: board.centerX + (u - 0.5) * board.width * spread + (layer || 0) * 0.7,
      y: board.top + v * board.height - (layer || 0) * 0.21,
    };
  }

  function drawBoardShadow(reading, layout) {
    const angle = (reading.shadowAzimuth * Math.PI) / 180;
    const daylight = Lighting.clamp(reading.dayFactor + reading.twilight * 0.32, 0.025, 1);
    const offsetX = Math.sin(angle) * 88 * daylight;
    const offsetY = Math.cos(angle) * 34 * daylight + 22;
    ctx.save();
    for (let layer = 3; layer >= 0; layer -= 1) {
      const points = boardPolygon(
        layout,
        offsetX,
        offsetY,
        -3 - layer * 5,
      );
      ctx.globalAlpha = (0.11 + daylight * 0.14) * (1 - layer * 0.16);
      ctx.fillStyle = "rgba(0, 3, 7, 0.88)";
      drawPolygon(points);
    }
    ctx.restore();
  }

  function drawBoardBase(reading, layout) {
    const board = layout.board;
    const top = boardPolygon(layout, 0, 0, 0);
    const front = [
      top[3],
      top[2],
      [top[2][0], top[2][1] + 15],
      [top[3][0], top[3][1] + 15],
    ];
    const side = [
      top[1],
      top[2],
      [top[2][0], top[2][1] + 15],
      [top[1][0], top[1][1] + 15],
    ];
    drawPolygon(side, "rgba(8, 24, 25, 0.96)");
    drawPolygon(front, "rgba(5, 17, 19, 0.98)");

    const surface = ctx.createLinearGradient(
      board.centerX - board.width * 0.5,
      board.top,
      board.centerX + board.width * 0.5,
      board.top + board.height,
    );
    surface.addColorStop(0, "#102b2b");
    surface.addColorStop(0.44, "#122524");
    surface.addColorStop(1, "#0a1a19");
    drawPolygon(top, surface, "rgba(152, 210, 200, 0.2)");

    ctx.save();
    ctx.beginPath();
    top.forEach(([x, y], index) => {
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.clip();
    ctx.lineWidth = 0.6;
    for (let x = 0; x <= Routing.BOARD.width; x += 1) {
      const a = projectUV(x / Routing.BOARD.width, 0, layout, 0);
      const b = projectUV(x / Routing.BOARD.width, 1, layout, 0);
      ctx.strokeStyle = x % 4 === 0 ? "rgba(107,188,182,.075)" : "rgba(107,188,182,.032)";
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    for (let y = 0; y <= Routing.BOARD.height; y += 1) {
      const a = projectUV(0, y / Routing.BOARD.height, layout, 0);
      const b = projectUV(1, y / Routing.BOARD.height, layout, 0);
      ctx.strokeStyle = y % 4 === 0 ? "rgba(107,188,182,.065)" : "rgba(107,188,182,.026)";
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.restore();

    const sheen = ctx.createLinearGradient(
      board.centerX - board.width * 0.4,
      board.top,
      board.centerX + board.width * 0.25,
      board.top + board.height * 0.7,
    );
    sheen.addColorStop(0, `rgba(255,255,255,${0.045 + reading.dayFactor * 0.04})`);
    sheen.addColorStop(0.28, "rgba(255,255,255,0.008)");
    sheen.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = sheen;
    drawPolygon(top);

    ctx.save();
    ctx.translate(board.centerX - board.width * 0.41, board.top + board.height - 18);
    ctx.fillStyle = "rgba(185,224,210,.38)";
    ctx.font = "600 7px SFMono-Regular, monospace";
    ctx.fillText("PV-24 / HELIO BUS", 2, 0);
    ctx.fillStyle = "rgba(185,224,210,.22)";
    ctx.font = "6px SFMono-Regular, monospace";
    ctx.fillText("4L · 2.4 GHz · REV.C", 2, 9);
    ctx.restore();
  }

  function drawTraces(reading, layout) {
    const drawOrder = [3, 2, 1, 0];
    for (const layer of drawOrder) {
      for (const net of routeReport.nets) {
        const selected =
          state.activeLayer < 0 || state.activeLayer === layer;
        const opacity = selected
          ? state.activeLayer === layer
            ? 1
            : 0.78
          : 0.08;
        ctx.save();
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        for (let index = 1; index < net.path.length; index += 1) {
          const previous = net.path[index - 1];
          const current = net.path[index];
          if (previous.layer !== layer || current.layer !== layer) continue;
          const a = projectCell(layer, previous.x, previous.y, layout);
          const b = projectCell(layer, current.x, current.y, layout);
          ctx.globalAlpha = opacity * 0.17;
          ctx.strokeStyle = net.color;
          ctx.lineWidth = state.activeLayer === layer ? 9 : 6;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
          ctx.globalAlpha = opacity;
          ctx.strokeStyle = net.color;
          ctx.lineWidth = state.activeLayer === layer ? 3 : 2.15;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
          const shine = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
          shine.addColorStop(0, "rgba(255,255,255,.42)");
          shine.addColorStop(1, "rgba(255,255,255,.12)");
          ctx.strokeStyle = shine;
          ctx.lineWidth = 0.65;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
        ctx.restore();
      }
    }

    for (const net of routeReport.nets) {
      for (const pin of [net.start, net.end]) {
        const point = projectCell(pin.layer, pin.x, pin.y, layout);
        ctx.beginPath();
        ctx.arc(point.x, point.y, 4.2, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(4,12,15,.88)";
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = net.color;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(point.x, point.y, 1.25, 0, Math.PI * 2);
        ctx.fillStyle = net.color;
        ctx.fill();
      }
    }

    for (const via of routeReport.vias) {
      const net = routeReport.nets.find((item) => item.name === via.net);
      const point = projectCell(via.toLayer, via.x, via.y, layout);
      const layerColor =
        routeReport.layers[via.toLayer]?.color || net?.color || "#fff";
      const selected =
        state.activeLayer < 0 ||
        state.activeLayer === via.fromLayer ||
        state.activeLayer === via.toLayer;
      ctx.globalAlpha = selected ? 1 : 0.13;
      ctx.beginPath();
      ctx.arc(point.x, point.y, 6.8, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(4, 11, 15, 0.86)";
      ctx.fill();
      ctx.lineWidth = 1.1;
      ctx.strokeStyle = layerColor;
      ctx.shadowColor = layerColor;
      ctx.shadowBlur = 8;
      ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.beginPath();
      ctx.arc(point.x, point.y, 2.2, 0, Math.PI * 2);
      ctx.fillStyle = "#dceff1";
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }

  function componentBaseColor(label) {
    return {
      MCU: [29, 45, 51],
      PWR: [76, 58, 39],
      SENSOR: [39, 63, 58],
      DISPLAY: [40, 47, 67],
      XTAL: [61, 53, 71],
      CAP: [67, 52, 43],
    }[label] || [36, 48, 54];
  }

  function drawComponents(reading, layout) {
    for (const obstacle of routeReport.obstacles) {
      const x0 = obstacle.x / Routing.BOARD.width;
      const x1 = (obstacle.x + obstacle.width - 0.18) / Routing.BOARD.width;
      const y0 = obstacle.y / Routing.BOARD.height;
      const y1 = (obstacle.y + obstacle.height - 0.18) / Routing.BOARD.height;
      const base = [
        projectUV(x0, y0, layout, 0),
        projectUV(x1, y0, layout, 0),
        projectUV(x1, y1, layout, 0),
        projectUV(x0, y1, layout, 0),
      ].map((point) => [point.x, point.y]);
      const height = 5 + obstacle.height3d * 3.2;
      const angle = (reading.shadowAzimuth * Math.PI) / 180;
      const shadowX = Math.sin(angle) * 4 * reading.dayFactor;
      const shadowY = Math.cos(angle) * 2.4 * reading.dayFactor + 3;
      const shadow = base.map(([x, y]) => [x + shadowX, y + shadowY]);
      const top = base.map(([x, y]) => [x, y - height]);
      const color = componentBaseColor(obstacle.label);
      const light = 0.56 + reading.dayFactor * 0.52;
      const topColor = shade(color, light + 0.28);
      const sideColor = shade(color, light * 0.54);

      ctx.globalAlpha = 0.5 + reading.dayFactor * 0.3;
      drawPolygon(shadow, "rgba(0, 3, 5, 0.9)");
      ctx.globalAlpha = 1;
      drawPolygon(
        [top[3], top[2], base[2], base[3]],
        Lighting.rgbCss(sideColor),
      );
      drawPolygon(
        [top[1], top[2], base[2], base[1]],
        Lighting.rgbCss(shade(color, light * 0.7)),
      );
      drawPolygon(
        top,
        Lighting.rgbCss(topColor),
        `rgba(${Math.min(255, topColor[0] + 32)},${Math.min(255, topColor[1] + 32)},${Math.min(255, topColor[2] + 32)},.36)`,
      );

      const labelPoint = projectUV(
        (x0 + x1) * 0.5,
        (y0 + y1) * 0.5,
        layout,
        0,
      );
      ctx.fillStyle = "rgba(216,240,238,.54)";
      ctx.font = "600 5.8px SFMono-Regular, monospace";
      ctx.textAlign = "center";
      ctx.fillText(obstacle.label, labelPoint.x, labelPoint.y - height * 0.52);
      ctx.textAlign = "left";

      if (obstacle.label === "MCU") {
        ctx.fillStyle = "rgba(207,239,233,.36)";
        for (let pin = 0; pin < 5; pin += 1) {
          const p1 = projectUV(x0 + 0.19 + pin * 0.14, y0 - 0.03, layout, 0);
          const p2 = projectUV(x0 + 0.19 + pin * 0.14, y0 + 0.03, layout, 0);
          ctx.fillRect(p1.x - 1, p1.y - height, p2.x + 1, 1.1);
          ctx.fillRect(p1.x - 1, p1.y + 1, p2.x + 1, 1.1);
        }
      }
      if (obstacle.label === "SENSOR" || obstacle.label === "DISPLAY") {
        ctx.fillStyle = "rgba(110,231,242,.24)";
        ctx.fillRect(
          labelPoint.x - 10,
          labelPoint.y - height + 4,
          20,
          1,
        );
      }
    }

    const led = projectUV(1.5 / Routing.BOARD.width, 8.5 / Routing.BOARD.height, layout, 0);
    const ledGlow = 0.22 + (1 - reading.dayFactor) * 0.7;
    ctx.beginPath();
    ctx.arc(led.x, led.y - 1, 8, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(137,239,172,${ledGlow * 0.18})`;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(led.x, led.y - 1, 2.4, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(181,255,206,${ledGlow})`;
    ctx.fill();
  }

  function drawAmbientAccents(reading, layout) {
    const { width, height } = layout;
    ctx.save();
    ctx.globalAlpha = 0.16;
    ctx.strokeStyle = reading.horizonCss;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(24, height - 151);
    ctx.lineTo(24, height - 126);
    ctx.lineTo(40, height - 126);
    ctx.moveTo(width - layout.inspectorWidth - 26, 86);
    ctx.lineTo(width - layout.inspectorWidth - 46, 86);
    ctx.lineTo(width - layout.inspectorWidth - 46, 99);
    ctx.stroke();
    ctx.restore();
  }

  function drawScene(reading, now) {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.75);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
    const layout = sceneLayout();
    drawSky(reading, layout, now);
    drawBoardShadow(reading, layout);
    drawBoardBase(reading, layout);
    drawTraces(reading, layout);
    drawComponents(reading, layout);
    drawAmbientAccents(reading, layout);
  }

  function resizeCanvas() {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.75);
    const width = Math.max(1, Math.round(window.innerWidth * dpr));
    const height = Math.max(1, Math.round(window.innerHeight * dpr));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
  }

  function animate(now) {
    const realDelta = (now - state.lastFrame) / 1000;
    state.lastFrame = now;
    if (!state.paused) {
      SimTime.advanceClock(clock, realDelta);
    }
    state.frameCount += 1;
    if (realDelta > 0.0001) {
      const instantaneousFps = Lighting.clamp(1 / realDelta, 1, 144);
      state.fps = state.fps * 0.92 + instantaneousFps * 0.08;
    }
    const reading = Lighting.lightingAt(clock.hour);
    if (!state.paused || state.lastUiUpdate === 0 || now - state.lastUiUpdate > 110) {
      updateReadouts(reading);
      updateTiming();
      state.lastUiUpdate = now;
    }
    drawScene(reading, now);
    window.requestAnimationFrame(animate);
  }

  function initialize() {
    buildStaticPanels();
    bindControls();
    syncPlayButton();
    resizeCanvas();
    const initial = Lighting.lightingAt(clock.hour);
    updateReadouts(initial);
    updateTiming();
    window.addEventListener("resize", resizeCanvas);
    if ("ResizeObserver" in window) {
      new ResizeObserver(resizeCanvas).observe(document.documentElement);
    }
    window.requestAnimationFrame(animate);
  }

  window.__helio = {
    getClock: () => ({
      hour: clock.hour,
      speed: clock.speed,
      paused: state.paused,
      simulationSteps: clock.simulationSteps,
      frameCount: state.frameCount,
    }),
    getLighting: (hour) => Lighting.lightingAt(hour ?? clock.hour),
    getRouting: () => routeReport,
    validateSunset: () => Lighting.validateSunset(),
    validateCycle: () => Lighting.validateCycle(),
    setHour: (hour) => setHour(hour),
    setPaused,
    setSpeed(speed) {
      state.speed = speed;
      clock.speed = speed;
      el.speed.value = String(speed);
      updateTiming();
    },
    forceDraw() {
      resizeCanvas();
      drawScene(Lighting.lightingAt(clock.hour), performance.now());
    },
    report: {
      sunset: sunsetReport,
      cycle: cycleReport,
      routing: routeReport,
    },
  };

  initialize();
})();
