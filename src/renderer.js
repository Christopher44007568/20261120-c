import {
  clamp,
  mat4LookAt,
  mat4Multiply,
  mat4Perspective,
  transformPoint,
} from "./math.js";
import {
  LINE_FRAGMENT_SHADER,
  LINE_VERTEX_SHADER,
  MESH_FRAGMENT_SHADER,
  MESH_VERTEX_SHADER,
} from "./shaders.js";

const MODE_INDEX = { lbs: 0, dqs: 1, error: 2 };

export class ViewportRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext("webgl2", {
      antialias: true,
      alpha: false,
      depth: true,
      powerPreference: "high-performance",
      preserveDrawingBuffer: true,
    });
    if (!this.gl) throw new Error("当前浏览器不支持 WebGL2，无法启动实时蒙皮视口。");
    this.gl.enable(this.gl.DEPTH_TEST);
    this.gl.depthFunc(this.gl.LEQUAL);
    this.gl.enable(this.gl.BLEND);
    this.gl.blendFunc(this.gl.SRC_ALPHA, this.gl.ONE_MINUS_SRC_ALPHA);
    this.gl.clearColor(0.026, 0.045, 0.06, 1);
    this.meshProgram = this.createProgram(MESH_VERTEX_SHADER, MESH_FRAGMENT_SHADER);
    this.lineProgram = this.createProgram(LINE_VERTEX_SHADER, LINE_FRAGMENT_SHADER);
    this.meshUniforms = this.uniformMap(this.meshProgram, [
      "uViewProj",
      "uBoneMatrices[0]",
      "uDqReal[0]",
      "uDqDual[0]",
      "uMode",
      "uHeatMax",
      "uCameraPosition",
      "uBaseColor",
    ]);
    this.lineUniforms = this.uniformMap(this.lineProgram, ["uViewProj", "uColor", "uPointSize", "uIsPoint"]);
    this.meshVao = this.gl.createVertexArray();
    this.lineVao = this.gl.createVertexArray();
    this.scene = null;
    this.camera = {
      yaw: -1.08,
      pitch: 0.28,
      distance: 7.7,
      target: [0, 0, 2],
    };
    this.pointer = null;
    this.cameraMatrix = null;
    this.projectionMatrix = null;
    this.viewProjection = null;
    this.installInput();
    this.resize();
  }

  createProgram(vertexSource, fragmentSource) {
    const gl = this.gl;
    const vertexShader = this.compileShader(gl.VERTEX_SHADER, vertexSource);
    const fragmentShader = this.compileShader(gl.FRAGMENT_SHADER, fragmentSource);
    const program = gl.createProgram();
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(`WebGL program link failed: ${gl.getProgramInfoLog(program)}`);
    }
    gl.deleteShader(vertexShader);
    gl.deleteShader(fragmentShader);
    return program;
  }

  compileShader(type, source) {
    const gl = this.gl;
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const stage = type === gl.VERTEX_SHADER ? "vertex" : "fragment";
      throw new Error(`WebGL ${stage} shader compile failed: ${gl.getShaderInfoLog(shader)}`);
    }
    return shader;
  }

  uniformMap(program, names) {
    const map = {};
    for (const name of names) map[name] = this.gl.getUniformLocation(program, name);
    return map;
  }

  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(this.canvas.clientWidth * dpr));
    const height = Math.max(1, Math.round(this.canvas.clientHeight * dpr));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    this.dpr = dpr;
    this.gl.viewport(0, 0, width, height);
  }

  setScene(model, trajectories) {
    this.scene = model;
    this.uploadMesh(model);
    const flatten = (points) => {
      const data = new Float32Array(points.length * 3);
      points.forEach((point, index) => data.set(point, index * 3));
      return data;
    };
    this.trailLbs = this.createArrayBuffer(flatten(trajectories.lbs));
    this.trailDqs = this.createArrayBuffer(flatten(trajectories.dqs));
    this.trailCount = trajectories.lbs.length;
    this.orphanBuffer = this.createArrayBuffer(this.extractVertices(model, model.orphanStart, model.vertexCount));
    this.probeRingBuffer = this.createArrayBuffer(new Float32Array((model.radialSegments + 1) * 3), this.gl.DYNAMIC_DRAW);
    this.probePointBuffer = this.createArrayBuffer(new Float32Array(6), this.gl.DYNAMIC_DRAW);
    this.boneBuffer = this.createArrayBuffer(new Float32Array(18), this.gl.DYNAMIC_DRAW);
    const grid = this.buildGrid();
    this.gridBuffer = this.createArrayBuffer(grid);
    this.gridCount = grid.length / 3;
    this.camera.target = [0, 0, model.jointZ];
    this.camera.distance = model.kind === "elbow" ? 7.9 : 7.7;
  }

  uploadMesh(model) {
    const gl = this.gl;
    gl.bindVertexArray(this.meshVao);
    this.bindAttribute(0, model.positions, 3, gl.FLOAT);
    this.bindAttribute(1, model.normals, 3, gl.FLOAT);
    this.bindAttribute(2, model.skinIndex, 4, gl.UNSIGNED_SHORT);
    this.bindAttribute(3, model.skinWeight, 4, gl.FLOAT);
    this.bindAttribute(4, model.tints, 3, gl.FLOAT);
    const indexBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, model.indices, gl.STATIC_DRAW);
    this.indexCount = model.indices.length;
    gl.bindVertexArray(null);
  }

  bindAttribute(location, data, size, type) {
    const gl = this.gl;
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(location);
    gl.vertexAttribPointer(location, size, type, false, 0, 0);
  }

  createArrayBuffer(data, usage = this.gl.DYNAMIC_DRAW) {
    const gl = this.gl;
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, data, usage);
    return buffer;
  }

  extractVertices(model, start, end) {
    const values = model.positions.slice(start * 3, end * 3);
    return values;
  }

  buildGrid() {
    const points = [];
    const extent = 3.2;
    const step = 0.4;
    for (let value = -extent; value <= extent + 1e-6; value += step) {
      points.push(-extent, value, 0, extent, value, 0);
      points.push(value, -extent, 0, value, extent, 0);
    }
    for (const radius of [0.9, 1.8, 2.7]) {
      const segments = 80;
      for (let index = 0; index < segments; index += 1) {
        const a = (index / segments) * Math.PI * 2;
        const b = ((index + 1) / segments) * Math.PI * 2;
        points.push(Math.cos(a) * radius, Math.sin(a) * radius, 0);
        points.push(Math.cos(b) * radius, Math.sin(b) * radius, 0);
      }
    }
    points.push(0, 0, 0, 0, 0, 4.7);
    return new Float32Array(points);
  }

  installInput() {
    const canvas = this.canvas;
    canvas.addEventListener("contextmenu", (event) => event.preventDefault());
    canvas.addEventListener("pointerdown", (event) => {
      this.pointer = {
        id: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        yaw: this.camera.yaw,
        pitch: this.camera.pitch,
      };
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", (event) => {
      if (!this.pointer || event.pointerId !== this.pointer.id) return;
      const dx = event.clientX - this.pointer.x;
      const dy = event.clientY - this.pointer.y;
      this.camera.yaw = this.pointer.yaw - dx * 0.006;
      this.camera.pitch = clamp(this.pointer.pitch + dy * 0.005, -0.08, 1.24);
    });
    const release = (event) => {
      if (!this.pointer || event.pointerId !== this.pointer.id) return;
      this.pointer = null;
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    };
    canvas.addEventListener("pointerup", release);
    canvas.addEventListener("pointercancel", release);
    canvas.addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        this.camera.distance = clamp(this.camera.distance * Math.exp(event.deltaY * 0.001), 4.5, 13.5);
      },
      { passive: false },
    );
    canvas.addEventListener("dblclick", () => this.resetCamera());
  }

  resetCamera() {
    this.camera.yaw = -1.08;
    this.camera.pitch = 0.28;
    this.camera.distance = this.scene?.kind === "elbow" ? 7.9 : 7.7;
  }

  updateCamera() {
    const aspect = this.canvas.width / Math.max(1, this.canvas.height);
    const responsiveDistance = this.camera.distance * (aspect < 0.8 ? 1.24 : 1);
    const position = [
      this.camera.target[0] + responsiveDistance * Math.cos(this.camera.pitch) * Math.cos(this.camera.yaw),
      this.camera.target[1] + responsiveDistance * Math.cos(this.camera.pitch) * Math.sin(this.camera.yaw),
      this.camera.target[2] + responsiveDistance * Math.sin(this.camera.pitch),
    ];
    this.cameraPosition = position;
    this.projectionMatrix = mat4Perspective((38 * Math.PI) / 180, aspect, 0.08, 40);
    this.cameraMatrix = mat4LookAt(position, this.camera.target, [0, 0, 1]);
    this.viewProjection = mat4Multiply(this.projectionMatrix, this.cameraMatrix);
  }

  render({ model, palette, mode, analysis, heatMax }) {
    if (!this.scene || !palette || !analysis) return;
    const gl = this.gl;
    this.resize();
    this.updateCamera();
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    this.drawGrid();
    this.drawTrails();
    this.drawMesh(model, palette, mode, heatMax);
    this.updateDynamicLines(model, palette, mode, analysis);
    this.drawDynamicLines();
  }

  drawGrid() {
    const gl = this.gl;
    gl.useProgram(this.lineProgram);
    gl.uniformMatrix4fv(this.lineUniforms.uViewProj, false, this.viewProjection);
    gl.uniform1f(this.lineUniforms.uPointSize, 1);
    gl.uniform1f(this.lineUniforms.uIsPoint, 0);
    gl.uniform4f(this.lineUniforms.uColor, 0.22, 0.35, 0.38, 0.18);
    gl.bindVertexArray(this.lineVao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.gridBuffer);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.LINES, 0, this.gridCount);
  }

  drawTrails() {
    const gl = this.gl;
    gl.useProgram(this.lineProgram);
    gl.uniform1f(this.lineUniforms.uPointSize, 1);
    gl.uniform1f(this.lineUniforms.uIsPoint, 0);
    gl.bindVertexArray(this.lineVao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.trailLbs);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    gl.uniform4f(this.lineUniforms.uColor, 0.94, 0.35, 0.3, 0.58);
    gl.drawArrays(gl.LINE_STRIP, 0, this.trailCount);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.trailDqs);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    gl.uniform4f(this.lineUniforms.uColor, 0.22, 0.78, 0.7, 0.72);
    gl.drawArrays(gl.LINE_STRIP, 0, this.trailCount);
  }

  drawMesh(model, palette, mode, heatMax) {
    const gl = this.gl;
    gl.useProgram(this.meshProgram);
    gl.bindVertexArray(this.meshVao);
    gl.uniformMatrix4fv(this.meshUniforms.uViewProj, false, this.viewProjection);
    gl.uniformMatrix4fv(this.meshUniforms["uBoneMatrices[0]"], false, palette.matrices);
    gl.uniform4fv(this.meshUniforms["uDqReal[0]"], palette.dualReal);
    gl.uniform4fv(this.meshUniforms["uDqDual[0]"], palette.dualDual);
    gl.uniform1i(this.meshUniforms.uMode, MODE_INDEX[mode] ?? 0);
    gl.uniform1f(this.meshUniforms.uHeatMax, heatMax);
    gl.uniform3fv(this.meshUniforms.uCameraPosition, this.cameraPosition);
    const base = mode === "lbs" ? [0.96, 0.29, 0.25] : mode === "dqs" ? [0.1, 0.64, 0.56] : [0.68, 0.68, 0.68];
    gl.uniform3fv(this.meshUniforms.uBaseColor, base);
    gl.drawElements(gl.TRIANGLES, this.indexCount, gl.UNSIGNED_INT, 0);
  }

  updateDynamicLines(model, palette, mode, analysis) {
    const positions = mode === "lbs" ? analysis.positions.lbs : analysis.positions.dqs;
    const ring = new Float32Array((model.radialSegments + 1) * 3);
    for (let radial = 0; radial <= model.radialSegments; radial += 1) {
      const source = model.midRing * model.radialSegments + (radial % model.radialSegments);
      const x = positions[source * 3];
      const y = positions[source * 3 + 1];
      const z = positions[source * 3 + 2];
      const centerX = 0;
      const centerY = 0;
      ring[radial * 3] = centerX + (x - centerX) * 1.012;
      ring[radial * 3 + 1] = centerY + (y - centerY) * 1.012;
      ring[radial * 3 + 2] = z;
    }
    this.updateBuffer(this.probeRingBuffer, ring);

    const probe = new Float32Array(6);
    const lbsProbe = this.vertexAt(analysis.positions.lbs, model.probeVertex);
    const dqsProbe = this.vertexAt(analysis.positions.dqs, model.probeVertex);
    probe.set(lbsProbe, 0);
    probe.set(dqsProbe, 3);
    this.updateBuffer(this.probePointBuffer, probe);

    const root = transformPoint(palette.matrices.slice(0, 16), [0, 0, 0]);
    const joint = transformPoint(palette.matrices.slice(16, 32), [0, 0, model.jointZ]);
    const tip = transformPoint(palette.matrices.slice(16, 32), [0, 0, model.height]);
    this.updateBuffer(this.boneBuffer, new Float32Array([...root, ...joint, ...joint, ...tip]));
  }

  vertexAt(positions, vertex) {
    return [positions[vertex * 3], positions[vertex * 3 + 1], positions[vertex * 3 + 2]];
  }

  updateBuffer(buffer, data) {
    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, data);
  }

  drawDynamicLines() {
    const gl = this.gl;
    gl.useProgram(this.lineProgram);
    gl.uniformMatrix4fv(this.lineUniforms.uViewProj, false, this.viewProjection);
    gl.bindVertexArray(this.lineVao);
    gl.enableVertexAttribArray(0);

    gl.uniform1f(this.lineUniforms.uIsPoint, 0);
    gl.uniform1f(this.lineUniforms.uPointSize, 1);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.probeRingBuffer);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    gl.uniform4f(this.lineUniforms.uColor, 0.9, 0.97, 0.96, 0.58);
    gl.drawArrays(gl.LINE_LOOP, 0, this.scene.radialSegments + 1);

    gl.disable(gl.DEPTH_TEST);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.boneBuffer);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    gl.uniform4f(this.lineUniforms.uColor, 0.82, 0.9, 0.9, 0.34);
    gl.drawArrays(gl.LINES, 0, 4);

    gl.uniform1f(this.lineUniforms.uIsPoint, 1);
    gl.uniform1f(this.lineUniforms.uPointSize, 8 * this.dpr);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.probePointBuffer);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    gl.uniform4f(this.lineUniforms.uColor, 0.98, 0.42, 0.35, 0.95);
    gl.drawArrays(gl.POINTS, 0, 1);
    gl.uniform4f(this.lineUniforms.uColor, 0.32, 0.94, 0.83, 0.95);
    gl.drawArrays(gl.POINTS, 1, 1);

    gl.uniform1f(this.lineUniforms.uPointSize, 6 * this.dpr);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.orphanBuffer);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    gl.uniform4f(this.lineUniforms.uColor, 1.0, 0.72, 0.36, 0.92);
    gl.drawArrays(gl.POINTS, 0, this.scene.vertexCount - this.scene.orphanStart);
    gl.uniform1f(this.lineUniforms.uIsPoint, 0);
    gl.enable(gl.DEPTH_TEST);
  }
}
