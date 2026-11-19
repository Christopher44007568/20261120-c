import { mat4, vec3 } from "./math.js";
import { LIGHT_DIRECTION, volumeDebugLines } from "./shadow-volume.js";
import {
  blitFragment,
  depthFragment,
  depthVertex,
  flatFragment,
  flatVertex,
  fullscreenVertex,
  sceneFragment,
  sceneVertex,
  shadowOverlayFragment,
  volumeFragment,
  volumeLineFragment,
  volumeVertex,
} from "./shaders.js";

const GROUND_POSITIONS = new Float32Array([
  -24, 0, -24,
  24, 0, -24,
  24, 0, 24,
  -24, 0, 24,
]);
const GROUND_INDICES = new Uint32Array([0, 2, 1, 0, 3, 2]);
const HISTOGRAM_BUCKETS = 10;

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(shader));
  }
  return shader;
}

function createProgram(gl, vertexSource, fragmentSource) {
  const program = gl.createProgram();
  gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, vertexSource));
  gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, fragmentSource));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(program));
  }
  const uniforms = new Map();
  const uniformCount = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS);
  for (let index = 0; index < uniformCount; index += 1) {
    const info = gl.getActiveUniform(program, index);
    uniforms.set(info.name, gl.getUniformLocation(program, info.name));
  }
  const attributes = new Map();
  const attributeCount = gl.getProgramParameter(program, gl.ACTIVE_ATTRIBUTES);
  for (let index = 0; index < attributeCount; index += 1) {
    const info = gl.getActiveAttrib(program, index);
    attributes.set(info.name, gl.getAttribLocation(program, info.name));
  }
  return { program, uniforms, attributes };
}

function makeMeshGpu(gl, positions, indices) {
  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);
  const positionBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
  const indexBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indices, gl.STATIC_DRAW);
  gl.bindVertexArray(null);
  return { vao, indexBuffer, count: indices.length };
}

function createDepthStencilFramebuffer(gl, width, height) {
  const framebuffer = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
  const colorTexture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, colorTexture);
  gl.texStorage2D(gl.TEXTURE_2D, 1, gl.RGBA8, width, height);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, colorTexture, 0);
  const depthStencil = gl.createRenderbuffer();
  gl.bindRenderbuffer(gl.RENDERBUFFER, depthStencil);
  gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH24_STENCIL8, width, height);
  gl.framebufferRenderbuffer(
    gl.FRAMEBUFFER,
    gl.DEPTH_STENCIL_ATTACHMENT,
    gl.RENDERBUFFER,
    depthStencil,
  );
  const status = gl.checkFramebufferStatus(gl.FRAMEBUFFER);
  if (status !== gl.FRAMEBUFFER_COMPLETE) throw new Error(`Incomplete framebuffer: ${status}`);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  return { framebuffer, colorTexture, depthStencil };
}

function createShadowFramebuffer(gl, size) {
  const framebuffer = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
  const depthTexture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, depthTexture);
  gl.texStorage2D(gl.TEXTURE_2D, 1, gl.DEPTH_COMPONENT24, size, size);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.TEXTURE_2D, depthTexture, 0);
  gl.drawBuffers([gl.NONE]);
  gl.readBuffer(gl.NONE);
  const status = gl.checkFramebufferStatus(gl.FRAMEBUFFER);
  if (status !== gl.FRAMEBUFFER_COMPLETE) throw new Error(`Incomplete shadow framebuffer: ${status}`);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  return { framebuffer, depthTexture, size };
}

export class ShadowRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.width = canvas.width;
    this.height = canvas.height;
    this.gl = canvas.getContext("webgl2", {
      antialias: true,
      alpha: false,
      depth: true,
      stencil: true,
      preserveDrawingBuffer: true,
    });
    if (!this.gl) throw new Error("WebGL2 is not available");
    this.gl.enable(this.gl.DEPTH_TEST);
    this.gl.depthFunc(this.gl.LEQUAL);
    this.gl.frontFace(this.gl.CCW);
    this.programs = this.createPrograms();
    this.emptyVao = this.gl.createVertexArray();
    this.ground = makeMeshGpu(this.gl, GROUND_POSITIONS, GROUND_INDICES);
    this.sceneTarget = createDepthStencilFramebuffer(this.gl, this.width, this.height);
    this.volumeBuffer = this.gl.createBuffer();
    this.volumeVao = this.gl.createVertexArray();
    this.gl.bindVertexArray(this.volumeVao);
    this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.volumeBuffer);
    this.gl.enableVertexAttribArray(0);
    this.gl.vertexAttribPointer(0, 3, this.gl.FLOAT, false, 0, 0);
    this.gl.bindVertexArray(null);
    this.lineBuffer = this.gl.createBuffer();
    this.lineVao = this.gl.createVertexArray();
    this.gl.bindVertexArray(this.lineVao);
    this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.lineBuffer);
    this.gl.enableVertexAttribArray(0);
    this.gl.vertexAttribPointer(0, 3, this.gl.FLOAT, false, 0, 0);
    this.gl.bindVertexArray(null);
    this.shadowMap = createShadowFramebuffer(this.gl, 1024);
    this.meshGpu = new Map();
    this.histogram = null;
    this.statsRequested = false;
  }

  createPrograms() {
    const gl = this.gl;
    return {
      scene: createProgram(gl, sceneVertex, sceneFragment),
      depth: createProgram(gl, depthVertex, depthFragment),
      volume: createProgram(gl, volumeVertex, volumeFragment),
      flat: createProgram(gl, flatVertex, flatFragment),
      fullscreen: createProgram(gl, fullscreenVertex, shadowOverlayFragment),
      volumeLine: createProgram(gl, volumeVertex, volumeLineFragment),
      blit: createProgram(gl, fullscreenVertex, blitFragment),
    };
  }

  ensureMeshGpu(key, mesh) {
    if (!this.meshGpu.has(key)) {
      this.meshGpu.set(key, makeMeshGpu(this.gl, mesh.positions, mesh.indices));
    }
    return this.meshGpu.get(key);
  }

  getCamera(position, target) {
    const view = mat4.lookAt(position, target, [0, 1, 0]);
    const projection = mat4.perspective(
      Math.PI * 43 / 180,
      this.width / this.height,
      0.08,
      120,
    );
    return {
      position,
      target,
      view,
      projection,
      viewProjection: mat4.multiply(projection, view),
    };
  }

  getLightViewProjection() {
    const center = [0, 2.6, 0];
    const eye = vec3.add(center, vec3.scale(LIGHT_DIRECTION, 30));
    const view = mat4.lookAt(eye, center, [0, 1, 0]);
    const projection = mat4.ortho(-16, 16, -16, 16, 1, 72);
    return mat4.multiply(projection, view);
  }

  uniform(program, name) {
    return program.uniforms.get(name);
  }

  uploadVolume(volume) {
    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.volumeBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, volume.positions, gl.DYNAMIC_DRAW);
  }

  bindSceneTarget() {
    this.gl.bindFramebuffer(this.gl.FRAMEBUFFER, this.sceneTarget.framebuffer);
    this.gl.viewport(0, 0, this.width, this.height);
  }

  clearScene() {
    const gl = this.gl;
    gl.clearColor(0.023, 0.043, 0.037, 1);
    gl.clearDepth(1);
    gl.clearStencil(0);
    gl.depthMask(true);
    gl.colorMask(true, true, true, true);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT | gl.STENCIL_BUFFER_BIT);
  }

  configureSceneProgram(camera, options = {}) {
    const gl = this.gl;
    const program = this.programs.scene;
    gl.useProgram(program.program);
    gl.uniformMatrix4fv(this.uniform(program, "uViewProjection"), false, camera.viewProjection);
    gl.uniformMatrix4fv(
      this.uniform(program, "uLightViewProjection"),
      false,
      this.getLightViewProjection(),
    );
    gl.uniform3fv(this.uniform(program, "uCameraPosition"), camera.position);
    gl.uniform3fv(this.uniform(program, "uLightDirection"), LIGHT_DIRECTION);
    gl.uniform1f(this.uniform(program, "uUseShadowMap"), options.useShadowMap ? 1 : 0);
    gl.uniform1f(this.uniform(program, "uDebugMask"), options.debugMask ? 1 : 0);
    gl.uniform1i(this.uniform(program, "uShadowMap"), 0);
    return program;
  }

  drawGround(program, camera, ground = true, color = [0.39, 0.38, 0.30]) {
    const gl = this.gl;
    gl.uniformMatrix4fv(this.uniform(program, "uModel"), false, mat4.identity());
    gl.uniform3fv(this.uniform(program, "uColor"), color);
    gl.uniform1f(this.uniform(program, "uGround"), ground ? 1 : 0);
    gl.bindVertexArray(this.ground.vao);
    gl.drawElements(gl.TRIANGLES, this.ground.count, gl.UNSIGNED_INT, 0);
  }

  drawMesh(program, meshGpu, color = [0.73, 0.66, 0.51]) {
    const gl = this.gl;
    gl.uniformMatrix4fv(this.uniform(program, "uModel"), false, mat4.identity());
    gl.uniform3fv(this.uniform(program, "uColor"), color);
    gl.uniform1f(this.uniform(program, "uGround"), 0);
    gl.bindVertexArray(meshGpu.vao);
    gl.drawElements(gl.TRIANGLES, meshGpu.count, gl.UNSIGNED_INT, 0);
  }

  drawScene(camera, meshGpu, options = {}) {
    const gl = this.gl;
    const program = this.configureSceneProgram(camera, options);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.depthMask(true);
    gl.disable(gl.CULL_FACE);
    gl.disable(gl.BLEND);
    gl.uniform1f(this.uniform(program, "uDebugMask"), options.debugMask ? 1 : 0);

    if (options.useShadowMap) {
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.shadowMap.depthTexture);
    }

    this.drawGround(program, camera);
    if (!options.maskGroundOnly && meshGpu) this.drawMesh(program, meshGpu);
  }

  renderShadowDepth(meshGpu) {
    const gl = this.gl;
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.shadowMap.framebuffer);
    gl.viewport(0, 0, this.shadowMap.size, this.shadowMap.size);
    gl.colorMask(false, false, false, false);
    gl.depthMask(true);
    gl.clearDepth(1);
    gl.clear(gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LESS);
    gl.disable(gl.CULL_FACE);
    gl.disable(gl.STENCIL_TEST);
    gl.enable(gl.POLYGON_OFFSET_FILL);
    gl.polygonOffset(1.4, 2.0);
    const program = this.programs.depth;
    gl.useProgram(program.program);
    gl.uniformMatrix4fv(
      this.uniform(program, "uLightViewProjection"),
      false,
      this.getLightViewProjection(),
    );
    gl.uniformMatrix4fv(this.uniform(program, "uModel"), false, mat4.identity());
    gl.bindVertexArray(meshGpu.vao);
    gl.drawElements(gl.TRIANGLES, meshGpu.count, gl.UNSIGNED_INT, 0);
    gl.disable(gl.POLYGON_OFFSET_FILL);
    gl.colorMask(true, true, true, true);
  }

  drawVolumeStencil(volume, zFail) {
    const gl = this.gl;
    const program = this.programs.volume;
    gl.useProgram(program.program);
    gl.uniformMatrix4fv(
      this.uniform(program, "uViewProjection"),
      false,
      this.activeCamera.viewProjection,
    );
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LESS);
    gl.depthMask(false);
    gl.colorMask(false, false, false, false);
    gl.disable(gl.BLEND);
    gl.disable(gl.CULL_FACE);
    gl.enable(gl.STENCIL_TEST);
    gl.stencilMask(0xff);
    gl.stencilFunc(gl.ALWAYS, 0, 0xff);
    gl.stencilOp(gl.KEEP, gl.KEEP, gl.KEEP);
    if (zFail) {
      gl.stencilOpSeparate(gl.FRONT, gl.KEEP, gl.DECR_WRAP, gl.KEEP);
      gl.stencilOpSeparate(gl.BACK, gl.KEEP, gl.INCR_WRAP, gl.KEEP);
    } else {
      gl.stencilOpSeparate(gl.FRONT, gl.KEEP, gl.KEEP, gl.DECR_WRAP);
      gl.stencilOpSeparate(gl.BACK, gl.KEEP, gl.KEEP, gl.INCR_WRAP);
    }
    gl.bindVertexArray(this.volumeVao);
    gl.drawArrays(gl.TRIANGLES, 0, volume.vertexCount);
    gl.colorMask(true, true, true, true);
    gl.depthMask(true);
  }

  collectHistogram() {
    const gl = this.gl;
    this.bindSceneTarget();
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.BLEND);
    gl.colorMask(true, true, true, true);
    gl.depthMask(false);
    gl.enable(gl.STENCIL_TEST);
    gl.stencilMask(0);
    gl.stencilOp(gl.KEEP, gl.KEEP, gl.KEEP);
    const program = this.programs.fullscreen;
    gl.useProgram(program.program);
    gl.bindVertexArray(this.emptyVao);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    for (let bucket = 0; bucket <= 8; bucket += 1) {
      gl.stencilFunc(gl.EQUAL, bucket, 0xff);
      const red = bucket === 0 ? 1 : bucket * 25;
      gl.uniform4f(this.uniform(program, "uColor"), red / 255, 0, 0, 1);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    gl.stencilFunc(gl.LEQUAL, 9, 0xff);
    gl.uniform4f(this.uniform(program, "uColor"), 225 / 255, 0, 0, 1);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    const pixels = new Uint8Array(this.width * this.height * 4);
    gl.readPixels(0, 0, this.width, this.height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    const values = new Array(HISTOGRAM_BUCKETS).fill(0);
    for (let index = 0; index < this.width * this.height; index += 1) {
      const red = pixels[index * 4];
      const bucket = red === 1 ? 0 : Math.round(red / 25);
      if (bucket >= 0 && bucket < values.length) values[bucket] += 1;
    }
    this.histogram = values;
    gl.disable(gl.STENCIL_TEST);
    gl.stencilMask(0xff);
    gl.depthMask(true);
    gl.depthFunc(gl.LEQUAL);
    this.statsRequested = false;
  }

  pollHistogram() {
    return this.histogram;
  }

  requestStats() {
    this.statsRequested = true;
  }

  drawShadowOverlay() {
    const gl = this.gl;
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.depthMask(false);
    gl.disable(gl.CULL_FACE);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.enable(gl.STENCIL_TEST);
    gl.stencilMask(0);
    gl.stencilFunc(gl.NOTEQUAL, 0, 0xff);
    gl.stencilOp(gl.KEEP, gl.KEEP, gl.KEEP);
    const program = this.programs.flat;
    gl.useProgram(program.program);
    gl.uniformMatrix4fv(
      this.uniform(program, "uViewProjection"),
      false,
      this.activeCamera.viewProjection,
    );
    gl.uniformMatrix4fv(this.uniform(program, "uModel"), false, mat4.identity());
    gl.uniform4f(this.uniform(program, "uColor"), 0.009, 0.022, 0.021, 0.78);
    gl.bindVertexArray(this.ground.vao);
    gl.drawElements(gl.TRIANGLES, this.ground.count, gl.UNSIGNED_INT, 0);
    gl.depthMask(true);
    gl.disable(gl.BLEND);
  }

  drawStencilMask() {
    const gl = this.gl;
    gl.clearColor(0.008, 0.012, 0.011, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.depthMask(false);
    gl.disable(gl.BLEND);
    gl.enable(gl.STENCIL_TEST);
    gl.stencilMask(0);
    gl.stencilFunc(gl.NOTEQUAL, 0, 0xff);
    gl.stencilOp(gl.KEEP, gl.KEEP, gl.KEEP);
    const program = this.programs.flat;
    gl.useProgram(program.program);
    gl.uniformMatrix4fv(
      this.uniform(program, "uViewProjection"),
      false,
      this.activeCamera.viewProjection,
    );
    gl.uniformMatrix4fv(this.uniform(program, "uModel"), false, mat4.identity());
    gl.uniform4f(this.uniform(program, "uColor"), 0.95, 1.0, 0.76, 1);
    gl.bindVertexArray(this.ground.vao);
    gl.drawElements(gl.TRIANGLES, this.ground.count, gl.UNSIGNED_INT, 0);
    gl.depthMask(true);
  }

  drawVolumeDebug(volume) {
    const gl = this.gl;
    const lines = volumeDebugLines(volume);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.lineBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, lines, gl.DYNAMIC_DRAW);
    gl.disable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.disable(gl.STENCIL_TEST);
    const program = this.programs.volumeLine;
    gl.useProgram(program.program);
    gl.uniformMatrix4fv(
      this.uniform(program, "uViewProjection"),
      false,
      this.activeCamera.viewProjection,
    );
    gl.uniform4f(this.uniform(program, "uColor"), 0.36, 1.0, 0.86, 0.34);
    gl.bindVertexArray(this.lineVao);
    gl.drawArrays(gl.LINES, 0, lines.length / 3);
    gl.disable(gl.BLEND);
  }

  finishStencilFrame(options) {
    const gl = this.gl;
    if (options.debugMask) {
      this.drawStencilMask();
    } else {
      this.drawShadowOverlay();
    }
    gl.disable(gl.STENCIL_TEST);
    gl.stencilMask(0xff);
    gl.depthMask(true);
    gl.enable(gl.DEPTH_TEST);
    if (options.showVolume) this.drawVolumeDebug(options.volume);
  }

  renderStencil(camera, meshGpu, volume, options) {
    this.activeCamera = camera;
    this.bindSceneTarget();
    this.clearScene();
    this.drawScene(camera, meshGpu);
    this.uploadVolume(volume);
    this.drawVolumeStencil(volume, options.zFail);
    this.finishStencilFrame({ ...options, volume });
  }

  renderShadowMapped(camera, meshGpu, options) {
    const gl = this.gl;
    this.activeCamera = camera;
    this.renderShadowDepth(meshGpu);
    this.bindSceneTarget();
    this.clearScene();
    this.drawScene(camera, meshGpu, {
      useShadowMap: true,
      debugMask: options.debugMask,
      maskGroundOnly: options.debugMask,
    });
    gl.disable(gl.STENCIL_TEST);
    gl.depthMask(true);
    if (options.showVolume) this.drawVolumeDebug(options.volume);
  }

  blit(x0 = 0, x1 = this.width) {
    const gl = this.gl;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(x0, 0, x1 - x0, this.height);
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.STENCIL_TEST);
    gl.disable(gl.BLEND);
    gl.colorMask(true, true, true, true);
    const program = this.programs.blit;
    gl.useProgram(program.program);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.sceneTarget.colorTexture);
    gl.uniform1i(this.uniform(program, "uTexture"), 0);
    gl.bindVertexArray(this.emptyVao);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindTexture(gl.TEXTURE_2D, null);
  }

  render(options) {
    const {
      mode,
      camera,
      meshGpu,
      volume,
      shadowMapSize = 1024,
      zFail = true,
      debugMask = false,
      showVolume = false,
    } = options;
    this.ensureShadowMapSize(shadowMapSize);
    if (mode === "stencil") {
      this.renderStencil(camera, meshGpu, volume, { zFail, debugMask, showVolume });
      this.blit();
      if (this.statsRequested) this.collectHistogram();
    } else if (mode === "shadowmap") {
      this.renderShadowMapped(camera, meshGpu, { debugMask, showVolume, volume });
      this.blit();
    } else {
      this.renderStencil(camera, meshGpu, volume, { zFail, debugMask, showVolume });
      this.blit(0, Math.floor(this.width / 2));
      if (this.statsRequested) this.collectHistogram();
      this.renderShadowMapped(camera, meshGpu, { debugMask, showVolume, volume });
      this.blit(Math.floor(this.width / 2), this.width);
    }
  }

  ensureShadowMapSize(size) {
    if (this.shadowMap.size === size) return;
    const gl = this.gl;
    gl.deleteFramebuffer(this.shadowMap.framebuffer);
    gl.deleteTexture(this.shadowMap.depthTexture);
    this.shadowMap = createShadowFramebuffer(gl, size);
  }

  readMaskPixels() {
    const gl = this.gl;
    const pixels = new Uint8Array(this.width * this.height * 4);
    gl.readPixels(0, 0, this.width, this.height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    const mask = new Uint8Array(this.width * this.height);
    for (let index = 0; index < mask.length; index += 1) {
      mask[index] = pixels[index * 4];
    }
    return mask;
  }

  captureMask(mode, camera, meshGpu, volume, zFail) {
    const gl = this.gl;
    this.activeCamera = camera;
    if (mode === "stencil") {
      this.bindSceneTarget();
      this.clearScene();
      this.drawScene(camera, meshGpu);
      this.uploadVolume(volume);
      this.drawVolumeStencil(volume, zFail);
      this.drawStencilMask();
    } else {
      this.renderShadowDepth(meshGpu);
      this.bindSceneTarget();
      gl.clearColor(0, 0, 0, 1);
      gl.clearDepth(1);
      gl.depthMask(true);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      this.drawScene(camera, meshGpu, {
        useShadowMap: true,
        debugMask: true,
        maskGroundOnly: true,
      });
    }
    gl.disable(gl.STENCIL_TEST);
    return {
      width: this.width,
      height: this.height,
      mask: this.readMaskPixels(),
    };
  }

  getInfo() {
    const gl = this.gl;
    const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
    return {
      vendor: debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
      renderer: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
      maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE),
      version: gl.getParameter(gl.VERSION),
    };
  }
}
