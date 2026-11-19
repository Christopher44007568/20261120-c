// Controller: wires UI state to render -> evaluate -> visualize.
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);

  const state = {
    sceneId: 'occluder',
    width: 180,
    height: 180,
    maxPasses: 4,
    orderMode: 'natural', // natural | reverse | shuffle
    shuffleSeed: 7,
    camera: new TRMath.OrbitCamera([0, 0, 0], 5.4, 0.25, 0.3),
  };

  const canvases = {
    ref: $('canvas-ref'),
    ddp: $('canvas-ddp'),
    naive: $('canvas-naive'),
    error: $('canvas-error'),
    leftover: $('canvas-leftover'),
    budget: $('canvas-budget'),
  };

  let currentScene = null;
  let currentRender = null;
  let currentResult = null;
  let permutation = [];

  function buildPermutation(meshes) {
    const transparent = meshes
      .map((m, i) => ({ m, i }))
      .filter((e) => e.m.transparent)
      .map((e) => e.i);
    if (state.orderMode === 'reverse') transparent.reverse();
    if (state.orderMode === 'shuffle') {
      let seed = state.shuffleSeed;
      const rnd = () => {
        seed = (seed * 1664525 + 1013904223) >>> 0;
        return seed / 4294967296;
      };
      for (let i = transparent.length - 1; i > 0; i--) {
        const j = Math.floor(rnd() * (i + 1));
        [transparent[i], transparent[j]] = [transparent[j], transparent[i]];
      }
    }
    // Opaque meshes keep their positions; only transparent order changes.
    return meshes.map((m, i) => (m.transparent ? transparent.indexOf(i) : i));
  }

  function repaint() {
    currentScene = TRGeometry.buildScene(state.sceneId);
    permutation = buildPermutation(currentScene.meshes);
    for (const key of Object.keys(canvases)) {
      canvases[key].width = state.width;
      canvases[key].height = state.height;
    }
    currentRender = TRRaster.renderScene(currentScene, state.camera,
      state.width, state.height);
    currentResult = TRCompositor.evaluate(currentRender, {
      maxPasses: state.maxPasses,
      meshPermutation: permutation,
    });

    TRViz.blit(canvases.ref, currentResult.ref);
    TRViz.blit(canvases.ddp, currentResult.ddp);
    TRViz.blit(canvases.naive, currentResult.naive);
    TRViz.blitHeat(canvases.error, currentResult.errorMap,
      Math.max(currentResult.stats.maxError, 1e-6));
    TRViz.blitHeat(canvases.leftover, currentResult.leftoverMask, 1,
      currentResult.leftoverMask, [0.95, 0.15, 0.15]);
    TRViz.blitBudget(canvases.budget, currentResult.requiredMap,
      currentResult.firstFailMap, state.maxPasses);
    updateHud();
  }

  function updateHud() {
    const s = currentResult.stats;
    const budgetClass = s.budgetSufficient ? 'ok' : 'loss';
    $('hud-budget').className = 'hud-pill ' + budgetClass;
    $('hud-budget').textContent = s.budgetSufficient
      ? `预算充足：剥离 ${state.maxPasses} 轮覆盖全部像素（最多需要 ${s.maxRequired} 轮）`
      : `预算不足：${s.leftoverPixels} 个像素仍有片元被丢弃（需要 ${s.maxRequired} 轮，当前 ${state.maxPasses} 轮）`;
    $('hud-ddp').textContent =
      `双深度剥离 vs 参考：平均误差 ${s.meanError.toFixed(5)}，` +
      `最大误差 ${s.maxError.toFixed(5)}，失真像素 ${s.failingPixels}`;
    $('hud-naive').textContent =
      `乱序单趟混合 vs 参考：平均误差 ${s.naive.meanError.toFixed(5)}，` +
      `最大误差 ${s.naive.maxError.toFixed(5)}，失真像素 ${s.naive.failingPixels}`;
    $('hud-scene').textContent =
      `场景 ${state.sceneId} · 分辨率 ${state.width}×${state.height} · ` +
      `单像素最多 ${s.maxFragCount} 层透明片元`;
    $('pass-value').textContent = state.maxPasses;

    const orderNames = { natural: '原始顺序', reverse: '交换为逆序', shuffle: '随机打乱' };
    const ddpNote = s.budgetSufficient
      ? '移动相机或交换透明物体顺序，DDP 结果与参考保持逐像素一致。'
      : '红色遮罩标出仍有未处理片元的像素；预算图红色为最先失真区域。';
    $('hud-order').textContent = `透明物体提交顺序：${orderNames[state.orderMode]}。${ddpNote}`;
  }

  // ---- Controls -----------------------------------------------------------
  $('scene-select').addEventListener('change', (e) => {
    state.sceneId = e.target.value;
    repaint();
  });
  $('pass-slider').addEventListener('input', (e) => {
    state.maxPasses = Number(e.target.value);
    repaint();
  });
  $('resolution-select').addEventListener('change', (e) => {
    const v = Number(e.target.value);
    state.width = v; state.height = v;
    repaint();
  });
  $('order-natural').addEventListener('click', () => setOrder('natural'));
  $('order-reverse').addEventListener('click', () => setOrder('reverse'));
  $('order-shuffle').addEventListener('click', () => {
    state.shuffleSeed = (state.shuffleSeed * 1103515245 + 12345) >>> 0;
    setOrder('shuffle');
  });
  function setOrder(mode) {
    state.orderMode = mode;
    document.querySelectorAll('.order-btn').forEach((b) =>
      b.classList.toggle('active', b.id === 'order-' + mode));
    repaint();
  }

  // ---- Camera orbit on the reference canvas --------------------------------
  const target = canvases.ref;
  let dragging = false, lastX = 0, lastY = 0;
  target.addEventListener('pointerdown', (e) => {
    dragging = true; lastX = e.clientX; lastY = e.clientY;
    target.setPointerCapture(e.pointerId);
  });
  target.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    const dx = e.clientX - lastX, dy = e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    state.camera.yaw -= dx * 0.01;
    state.camera.pitch = Math.max(-1.45, Math.min(1.45,
      state.camera.pitch + dy * 0.01));
    repaint();
  });
  target.addEventListener('pointerup', () => { dragging = false; });
  target.addEventListener('wheel', (e) => {
    e.preventDefault();
    state.camera.radius = Math.max(2.2, Math.min(12,
      state.camera.radius * (1 + Math.sign(e.deltaY) * 0.08)));
    repaint();
  }, { passive: false });

  window.addEventListener('resize', () => repaint());
  repaint();
})();
