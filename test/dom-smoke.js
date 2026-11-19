// Load src/app.js against a minimal DOM stub to catch wiring/runtime errors
// without a browser.
const path = require('path');
global.TRMath = require('../src/math.js');
global.TRGeometry = require('../src/geometry.js');
global.TRRaster = require('../src/rasterizer.js');
global.TRCompositor = require('../src/compositor.js');
global.TRViz = require('../src/visualization.js');

const listeners = {};
function makeCtx() {
  return {
    createImageData: (w, h) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }),
    putImageData() {}, drawImage() {}, clearRect() {},
  };
}
function makeEl(id) {
  return {
    id, width: 180, height: 180, value: id === 'pass-slider' ? '4' : 'occluder',
    textContent: '', className: '',
    listeners: {},
    getContext: makeCtx,
    addEventListener(ev, fn) { this.listeners[ev] = fn; },
    classList: { toggle() {}, add() {}, remove() {} },
    setPointerCapture() {},
  };
}
const els = {};
global.document = {
  getElementById: (id) => (els[id] ||= makeEl(id)),
  createElement: () => makeEl('tmp'),
  querySelectorAll: () => [],
};
global.window = { addEventListener() {} };

require(path.join('..', 'src', 'app.js'));

// Exercise every control path once.
els['scene-select'].listeners.change({ target: { value: 'intersect' } });
els['scene-select'].listeners.change({ target: { value: 'coplanar' } });
els['pass-slider'].listeners.input({ target: { value: '1' } });
els['pass-slider'].listeners.input({ target: { value: '8' } });
els['resolution-select'].listeners.change({ target: { value: '120' } });
els['order-reverse'].listeners.click();
els['order-shuffle'].listeners.click();
els['order-shuffle'].listeners.click();
els['order-natural'].listeners.click();

const ref = els['canvas-ref'];
ref.listeners.pointerdown({ clientX: 10, clientY: 10, pointerId: 1 });
ref.listeners.pointermove({ clientX: 24, clientY: 16 });
ref.listeners.pointerup();
ref.listeners.wheel({ deltaY: 100, preventDefault() {} });

if (!els['hud-budget'].textContent.includes('预算')) {
  throw new Error('HUD budget line was not populated');
}
console.log('dom smoke passed; HUD =', els['hud-budget'].textContent);
