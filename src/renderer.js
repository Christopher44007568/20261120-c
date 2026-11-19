import { FRAGMENT_SHADER, VERTEX_SHADER } from './sky-shader.js';
import { sunDirection } from './atmosphere.js';

function compileShader(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const message = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`Shader compile failed: ${message}`);
  }
  return shader;
}

function createProgram(gl) {
  const program = gl.createProgram();
  const vertex = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER);
  const fragment = compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.linkProgram(program);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const message = gl.getProgramInfoLog(program);
    gl.deleteProgram(program);
    throw new Error(`Program link failed: ${message}`);
  }
  return program;
}

export class SkyRenderer {
  constructor(canvas, params) {
    this.canvas = canvas;
    this.params = params;
    this.startTime = performance.now();
    this.frame = 0;
    this.running = false;
    this.gl = canvas.getContext('webgl2', {
      alpha: false,
      antialias: false,
      depth: false,
      powerPreference: 'high-performance',
      preserveDrawingBuffer: true
    });
    if (!this.gl) throw new Error('WebGL 2 is not available');
    this.program = createProgram(this.gl);
    this.locations = this.uniformLocations();
    this.buffer = this.gl.createBuffer();
    this.vertexArray = this.gl.createVertexArray();
    this.gl.bindVertexArray(this.vertexArray);
    this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.buffer);
    this.gl.bufferData(
      this.gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]),
      this.gl.STATIC_DRAW
    );
    const position = this.gl.getAttribLocation(this.program, 'aPosition');
    this.gl.enableVertexAttribArray(position);
    this.gl.vertexAttribPointer(position, 2, this.gl.FLOAT, false, 0, 0);
    this.resize();
  }

  uniformLocations() {
    const names = [
      'uResolution', 'uTime', 'uSunDirection', 'uSunElevation',
      'uRayleighScale', 'uMieScale', 'uCloudCoverage', 'uCloudThickness',
      'uCloudShadows'
    ];
    return Object.fromEntries(names.map((name) => [name, this.gl.getUniformLocation(this.program, name)]));
  }

  resize() {
    const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
    const width = Math.max(1, Math.floor(this.canvas.clientWidth * ratio));
    const height = Math.max(1, Math.floor(this.canvas.clientHeight * ratio));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
  }

  render(timeSeconds) {
    const { gl, locations, params } = this;
    if (!this.running) return;
    this.resize();
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.useProgram(this.program);
    const sun = sunDirection(params.sunElevation, params.sunAzimuth);
    gl.uniform2f(locations.uResolution, this.canvas.width, this.canvas.height);
    gl.uniform1f(locations.uTime, timeSeconds);
    gl.uniform3f(locations.uSunDirection, sun.x, sun.y, sun.z);
    gl.uniform1f(locations.uSunElevation, params.sunElevation);
    gl.uniform1f(locations.uRayleighScale, params.rayleighScale);
    gl.uniform1f(locations.uMieScale, params.mieScale);
    gl.uniform1f(locations.uCloudCoverage, params.cloudCoverage);
    gl.uniform1f(locations.uCloudThickness, params.cloudThickness);
    gl.uniform1f(locations.uCloudShadows, params.cloudShadows ? 1 : 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (!this.canvas.dataset.pixels) {
      const diagnostics = new Uint8Array(4);
      gl.readPixels(
        Math.floor(this.canvas.width * 0.5),
        Math.floor(this.canvas.height * 0.85),
        1, 1, gl.RGBA, gl.UNSIGNED_BYTE, diagnostics
      );
      this.canvas.dataset.pixels = [...diagnostics].join(',');
      this.canvas.dataset.glError = String(gl.getError());
    }
    this.frame += 1;
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.render(0);
    const loop = (now) => {
      if (!this.running) return;
      this.render((now - this.startTime) / 1000);
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  stop() {
    this.running = false;
  }
}
