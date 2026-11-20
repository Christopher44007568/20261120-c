import { FRAGMENT_SHADER, VERTEX_SHADER } from "./noise-shader.js";

export const NOISE_NAMES = ["Perlin", "Worley", "Simplex"];

function compileShader(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`Shader compile failed: ${log}`);
  }
  return shader;
}

function createProgram(gl) {
  const vertex = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER);
  const fragment = compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
  const program = gl.createProgram();
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.linkProgram(program);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(program);
    gl.deleteProgram(program);
    throw new Error(`Program link failed: ${log}`);
  }
  return program;
}

function uniformMap(gl, program) {
  const names = [
    "uResolution",
    "uScale",
    "uGain",
    "uWarp",
    "uTime",
    "uSeed",
    "uOctaves",
    "uWarped",
    "uNoise",
    "uMode",
  ];
  return Object.fromEntries(names.map((name) => [name, gl.getUniformLocation(program, name)]));
}

export class NoiseRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext("webgl2", {
      antialias: false,
      alpha: false,
      depth: false,
      preserveDrawingBuffer: true,
      powerPreference: "high-performance",
    });
    if (!this.gl) throw new Error("当前浏览器不支持 WebGL2");

    const gl = this.gl;
    this.program = createProgram(gl);
    this.uniforms = uniformMap(gl, this.program);
    this.vao = gl.createVertexArray();
    this.buffer = gl.createBuffer();
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]),
      gl.STATIC_DRAW
    );
    const position = gl.getAttribLocation(this.program, "aPosition");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);

    this.readTarget = null;
    this.readSize = 0;
    this.pixel = new Uint8Array(4);
    this.timerExt = gl.getExtension("EXT_disjoint_timer_query_webgl2");
    this.info = this.readRendererInfo();
  }

  readRendererInfo() {
    const gl = this.gl;
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    if (!ext) return { vendor: "WebGL2", renderer: "WebGL2" };
    return {
      vendor: gl.getParameter(ext.UNMASKED_VENDOR_WEBGL),
      renderer: gl.getParameter(ext.UNMASKED_RENDERER_WEBGL),
    };
  }

  resize(maxDpr = 1.5) {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, maxDpr);
    const width = Math.max(1, Math.round(rect.width * dpr));
    const height = Math.max(1, Math.round(rect.height * dpr));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
      return true;
    }
    return false;
  }

  setUniforms(params, mode, noiseId = 0, width = this.gl.drawingBufferWidth, height = this.gl.drawingBufferHeight) {
    const gl = this.gl;
    const u = this.uniforms;
    gl.useProgram(this.program);
    gl.uniform2f(u.uResolution, width, height);
    gl.uniform1f(u.uScale, params.scale);
    gl.uniform1f(u.uGain, params.gain);
    gl.uniform1f(u.uWarp, params.warp);
    gl.uniform1f(u.uTime, params.time || 0);
    gl.uniform2f(u.uSeed, params.seedX || 0, params.seedY || 0);
    gl.uniform1i(u.uOctaves, params.octaves);
    gl.uniform1i(u.uWarped, params.warped ? 1 : 0);
    gl.uniform1i(u.uNoise, noiseId);
    gl.uniform1i(u.uMode, mode);
  }

  draw() {
    const gl = this.gl;
    gl.bindVertexArray(this.vao);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindVertexArray(null);
  }

  renderMatrix(params) {
    const gl = this.gl;
    this.resize();
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    this.setUniforms(params, 0);
    this.draw();
    gl.flush();
  }

  ensureReadTarget(size) {
    const gl = this.gl;
    if (this.readTarget && this.readSize === size) return;
    if (this.readTarget) {
      gl.deleteFramebuffer(this.readTarget.framebuffer);
      gl.deleteTexture(this.readTarget.texture);
    }
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, size, size, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const framebuffer = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
    const status = gl.checkFramebufferStatus(gl.FRAMEBUFFER);
    if (status !== gl.FRAMEBUFFER_COMPLETE) throw new Error(`Framebuffer incomplete: ${status}`);
    this.readTarget = { framebuffer, texture };
    this.readSize = size;
  }

  bindReadTarget(size) {
    const gl = this.gl;
    this.ensureReadTarget(size);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.readTarget.framebuffer);
    gl.viewport(0, 0, size, size);
  }

  readField(noiseId, warped, size, params) {
    const gl = this.gl;
    this.bindReadTarget(size);
    this.setUniforms({ ...params, warped }, 1, noiseId, size, size);
    this.draw();
    const pixels = new Uint8Array(size * size * 4);
    gl.readPixels(0, 0, size, size, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);

    const values = new Float32Array(size * size);
    for (let i = 0; i < values.length; i++) values[i] = pixels[i * 4] / 255;
    return { values, width: size, height: size };
  }

  async benchmark(noiseId, warped, size, params, repetitions = 4) {
    if (this.timerExt) {
      return this.benchmarkTimer(noiseId, warped, size, params, repetitions);
    }
    return this.benchmarkSync(noiseId, warped, size, params, repetitions);
  }

  async benchmarkTimer(noiseId, warped, size, params, repetitions) {
    const gl = this.gl;
    const ext = this.timerExt;
    this.bindReadTarget(size);
    this.setUniforms({ ...params, warped }, 1, noiseId, size, size);
    this.draw();
    gl.finish();

    const samples = [];
    for (let i = 0; i < repetitions; i++) {
      const query = gl.createQuery();
      this.setUniforms({ ...params, warped }, 1, noiseId, size, size);
      gl.beginQuery(ext.TIME_ELAPSED_EXT, query);
      this.draw();
      gl.endQuery(ext.TIME_ELAPSED_EXT);
      gl.flush();

      let available = false;
      for (let attempt = 0; attempt < 2000; attempt++) {
        available = gl.getQueryParameter(query, gl.QUERY_RESULT_AVAILABLE);
        if (available) break;
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
      if (available) {
        const disjoint = gl.getParameter(ext.GPU_DISJOINT_EXT);
        if (!disjoint) samples.push(gl.getQueryParameter(query, gl.QUERY_RESULT) / 1e6);
      }
      gl.deleteQuery(query);
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    if (!samples.length) return this.benchmarkSync(noiseId, warped, size, params, repetitions);
    samples.sort((a, b) => a - b);
    return samples[Math.floor(samples.length / 2)];
  }

  benchmarkSync(noiseId, warped, size, params, repetitions) {
    const gl = this.gl;
    this.bindReadTarget(size);
    this.setUniforms({ ...params, warped }, 1, noiseId, size, size);
    this.draw();
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, this.pixel);

    const samples = [];
    for (let i = 0; i < repetitions; i++) {
      this.setUniforms({ ...params, warped }, 1, noiseId, size, size);
      gl.finish();
      const start = performance.now();
      this.draw();
      gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, this.pixel);
      samples.push(performance.now() - start);
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    samples.sort((a, b) => a - b);
    return samples[Math.floor(samples.length / 2)];
  }
}
