import {
  DEG,
  f32,
  lookAt,
  multiply,
  perspective,
} from "./math.js";
import {
  COLORS,
  STATIC_BOXES,
  STATIC_GEOMETRY,
  UNIT_CUBE,
  WORLD,
} from "./scene.js";

const BACKGROUND = [0.028, 0.077, 0.088];

const SKY_VERTEX_SHADER = `#version 300 es
precision highp float;

out vec2 vUv;

void main() {
  vec2 position = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  vUv = position;
  gl_Position = vec4(position * 2.0 - 1.0, 0.9999, 1.0);
}
`;

const SKY_FRAGMENT_SHADER = `#version 300 es
precision highp float;

in vec2 vUv;
uniform vec3 uTop;
uniform vec3 uBottom;
uniform vec3 uTint;

out vec4 outColor;

void main() {
  float gradient = pow(clamp(vUv.y, 0.0, 1.0), 0.68);
  vec3 color = mix(uBottom, uTop, gradient);
  float horizon = exp(-pow((vUv.y - 0.43) * 7.5, 2.0));
  color += vec3(0.022, 0.06, 0.061) * horizon;
  outColor = vec4(color * uTint, 1.0);
}
`;

const STATIC_VERTEX_SHADER = `#version 300 es
precision highp float;

in vec3 aPosition;
in vec3 aColor;

uniform mat4 uViewProjection;
uniform vec3 uChunkOffset;
uniform vec3 uTint;

out vec3 vColor;
out float vDepth;

void main() {
  vec3 position = aPosition + uChunkOffset;
  vec4 clip = uViewProjection * vec4(position, 1.0);
  gl_Position = clip;
  vColor = aColor * uTint;
  vDepth = max(0.0, clip.w);
}
`;

const STATIC_FRAGMENT_SHADER = `#version 300 es
precision highp float;

in vec3 vColor;
in float vDepth;

uniform vec3 uBackground;

out vec4 outColor;

void main() {
  float fog = smoothstep(420.0, 1480.0, vDepth);
  vec3 color = mix(vColor, uBackground, fog * 0.92);
  outColor = vec4(color, 1.0);
}
`;

const INSTANCED_VERTEX_SHADER = `#version 300 es
precision highp float;

in vec3 aLocal;
in vec3 aNormal;
in vec3 iPosition;
in vec3 iScale;
in vec3 iColor;
in float iYaw;

uniform mat4 uViewProjection;
uniform vec3 uTint;

out vec3 vColor;
out float vDepth;

void main() {
  float c = cos(iYaw);
  float s = sin(iYaw);
  vec3 local = aLocal * iScale;
  local.xz = mat2(c, -s, s, c) * local.xz;
  vec3 normal = aNormal;
  normal.xz = mat2(c, -s, s, c) * normal.xz;

  vec3 lightDirection = normalize(vec3(-0.42, 0.82, 0.31));
  float light = 0.64 + max(dot(normal, lightDirection), 0.0) * 0.42;
  float edge = 0.9 + max(normal.y, 0.0) * 0.1;

  vec4 clip = uViewProjection * vec4(iPosition + local, 1.0);
  gl_Position = clip;
  vColor = iColor * light * edge * uTint;
  vDepth = max(0.0, clip.w);
}
`;

const INSTANCED_FRAGMENT_SHADER = `#version 300 es
precision highp float;

in vec3 vColor;
in float vDepth;

uniform vec3 uBackground;

out vec4 outColor;

void main() {
  float fog = smoothstep(420.0, 1480.0, vDepth);
  vec3 color = mix(vColor, uBackground, fog * 0.88);
  outColor = vec4(color, 1.0);
}
`;

const REFERENCE_VERTEX_SHADER = `#version 300 es
precision highp float;

in vec4 aClip;
in vec3 aColor;

out vec3 vColor;
out float vDepth;

void main() {
  gl_Position = aClip;
  vColor = aColor;
  vDepth = max(0.0, aClip.w);
}
`;

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

function createProgram(gl, vertexSource, fragmentSource) {
  const program = gl.createProgram();
  const vertex = compileShader(gl, gl.VERTEX_SHADER, vertexSource);
  const fragment = compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
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

function uniforms(gl, program, names) {
  const result = {};
  for (const name of names) result[name] = gl.getUniformLocation(program, name);
  return result;
}

function createBuffer(gl, target, data, usage = gl.STATIC_DRAW) {
  const buffer = gl.createBuffer();
  gl.bindBuffer(target, buffer);
  gl.bufferData(target, data, usage);
  return buffer;
}

function makeVertexArray(gl) {
  return gl.createVertexArray();
}

function configureStaticVao(gl, chunk) {
  const vao = makeVertexArray(gl);
  gl.bindVertexArray(vao);
  const positions = createBuffer(gl, gl.ARRAY_BUFFER, new Float32Array(chunk.positions));
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
  const colors = createBuffer(gl, gl.ARRAY_BUFFER, new Float32Array(chunk.colors));
  gl.enableVertexAttribArray(1);
  gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);
  gl.bindVertexArray(null);
  return {
    vao,
    count: chunk.positions.length / 3,
    positions,
    colors,
    originX: chunk.originX,
    originZ: chunk.originZ,
  };
}

function configureCubeVao(gl) {
  const vao = makeVertexArray(gl);
  gl.bindVertexArray(vao);
  createBuffer(gl, gl.ARRAY_BUFFER, UNIT_CUBE.vertices);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 24, 0);
  gl.enableVertexAttribArray(1);
  gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 24, 12);

  const instanceBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, instanceBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, 10 * 4 * 420, gl.DYNAMIC_DRAW);
  const stride = 40;
  gl.enableVertexAttribArray(2);
  gl.vertexAttribPointer(2, 3, gl.FLOAT, false, stride, 0);
  gl.vertexAttribDivisor(2, 1);
  gl.enableVertexAttribArray(3);
  gl.vertexAttribPointer(3, 3, gl.FLOAT, false, stride, 12);
  gl.vertexAttribDivisor(3, 1);
  gl.enableVertexAttribArray(4);
  gl.vertexAttribPointer(4, 3, gl.FLOAT, false, stride, 24);
  gl.vertexAttribDivisor(4, 1);
  gl.enableVertexAttribArray(5);
  gl.vertexAttribPointer(5, 1, gl.FLOAT, false, stride, 36);
  gl.vertexAttribDivisor(5, 1);
  gl.bindVertexArray(null);
  return { vao, instanceBuffer, instanceCapacity: 420 };
}

function configureReferenceVao(gl) {
  const vao = makeVertexArray(gl);
  gl.bindVertexArray(vao);
  const buffer = createBuffer(gl, gl.ARRAY_BUFFER, 7 * 4 * 500000, gl.DYNAMIC_DRAW);
  const stride = 28;
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 4, gl.FLOAT, false, stride, 0);
  gl.enableVertexAttribArray(1);
  gl.vertexAttribPointer(1, 3, gl.FLOAT, false, stride, 16);
  gl.bindVertexArray(null);
  return { vao, buffer, capacity: 500000 };
}

export class SceneRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext("webgl2", {
      alpha: false,
      antialias: true,
      depth: true,
      powerPreference: "high-performance",
    });
    if (!this.gl) throw new Error("WebGL2 is not available in this browser.");

    const gl = this.gl;
    this.skyProgram = createProgram(gl, SKY_VERTEX_SHADER, SKY_FRAGMENT_SHADER);
    this.skyUniforms = uniforms(gl, this.skyProgram, ["uTop", "uBottom", "uTint"]);
    this.staticProgram = createProgram(gl, STATIC_VERTEX_SHADER, STATIC_FRAGMENT_SHADER);
    this.staticUniforms = uniforms(gl, this.staticProgram, [
      "uViewProjection",
      "uChunkOffset",
      "uTint",
      "uBackground",
    ]);
    this.instanceProgram = createProgram(gl, INSTANCED_VERTEX_SHADER, INSTANCED_FRAGMENT_SHADER);
    this.instanceUniforms = uniforms(gl, this.instanceProgram, [
      "uViewProjection",
      "uTint",
      "uBackground",
    ]);
    this.referenceProgram = createProgram(gl, REFERENCE_VERTEX_SHADER, STATIC_FRAGMENT_SHADER);
    this.referenceUniforms = uniforms(gl, this.referenceProgram, ["uBackground"]);

    this.staticChunks = STATIC_GEOMETRY.chunks.map((chunk) => configureStaticVao(gl, chunk));
    this.cube = configureCubeVao(gl);
    this.reference = configureReferenceVao(gl);

    this.staticWorld = STATIC_GEOMETRY.worldPositions;
    this.staticColors = STATIC_GEOMETRY.worldColors;
    this.referenceScratch = new Float32Array(this.reference.capacity);
    this.projection = new Float64Array(16);
    this.view = new Float64Array(16);
    this.viewProjection = new Float64Array(16);
    this.identity = new Float64Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);

    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.disable(gl.CULL_FACE);
    gl.clearColor(BACKGROUND[0], BACKGROUND[1], BACKGROUND[2], 1);
  }

  drawSky(tint) {
    const gl = this.gl;
    gl.disable(gl.DEPTH_TEST);
    gl.depthMask(false);
    gl.useProgram(this.skyProgram);
    gl.uniform3fv(this.skyUniforms.uTop, [0.008, 0.021, 0.03]);
    gl.uniform3fv(this.skyUniforms.uBottom, [0.035, 0.092, 0.103]);
    gl.uniform3fv(this.skyUniforms.uTint, tint);
    gl.bindVertexArray(null);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.depthMask(true);
    gl.enable(gl.DEPTH_TEST);
  }

  resize(width, height, dpr) {
    const pixelWidth = Math.max(1, Math.round(width * dpr));
    const pixelHeight = Math.max(1, Math.round(height * dpr));
    if (this.canvas.width !== pixelWidth || this.canvas.height !== pixelHeight) {
      this.canvas.width = pixelWidth;
      this.canvas.height = pixelHeight;
    }
    this.pixelWidth = pixelWidth;
    this.pixelHeight = pixelHeight;
    this.cssWidth = width;
    this.cssHeight = height;
  }

  cameraMatrices(camera, mode, origin, aspect) {
    perspective(this.projection, 48 * DEG, aspect, 0.45, 1700);
    if (mode === "raw") {
      const eye = camera.eye;
      const target = [
        eye[0] + camera.forward[0],
        eye[1] + camera.forward[1],
        eye[2] + camera.forward[2],
      ];
      lookAt(this.view, eye, target);
    } else {
      const eye = [
        camera.eye[0] - origin[0],
        camera.eye[1],
        camera.eye[2] - origin[1],
      ];
      const target = [
        eye[0] + camera.forward[0],
        eye[1] + camera.forward[1],
        eye[2] + camera.forward[2],
      ];
      lookAt(this.view, eye, target);
    }
    multiply(this.viewProjection, this.projection, this.view);
    return this.viewProjection;
  }

  referenceMatrix(camera, aspect) {
    const projection = new Float64Array(16);
    const view = new Float64Array(16);
    const viewProjection = new Float64Array(16);
    perspective(projection, 48 * DEG, aspect, 0.45, 1700);
    const eye = camera.eye;
    lookAt(view, eye, [
      eye[0] + camera.forward[0],
      eye[1] + camera.forward[1],
      eye[2] + camera.forward[2],
    ]);
    return multiply(viewProjection, projection, view);
  }

  drawStatic(viewProjection, origin, mode, tint) {
    const gl = this.gl;
    gl.useProgram(this.staticProgram);
    gl.uniformMatrix4fv(this.staticUniforms.uViewProjection, false, viewProjection);
    gl.uniform3fv(this.staticUniforms.uTint, tint);
    gl.uniform3fv(this.staticUniforms.uBackground, BACKGROUND);

    for (const chunk of this.staticChunks) {
      const offset = mode === "raw"
        ? [f32(chunk.originX), 0, f32(chunk.originZ)]
        : [f32(chunk.originX - origin[0]), 0, f32(chunk.originZ - origin[1])];
      gl.uniform3fv(this.staticUniforms.uChunkOffset, offset);
      gl.bindVertexArray(chunk.vao);
      gl.drawArrays(gl.TRIANGLES, 0, chunk.count);
    }
  }

  instanceData(instances, origin, mode) {
    const data = new Float32Array(instances.length * 10);
    let cursor = 0;
    for (const instance of instances) {
      data[cursor++] = mode === "raw" ? instance.x : instance.x - origin[0];
      data[cursor++] = instance.y;
      data[cursor++] = mode === "raw" ? instance.z : instance.z - origin[1];
      data[cursor++] = instance.sx;
      data[cursor++] = instance.sy;
      data[cursor++] = instance.sz;
      data[cursor++] = instance.color[0];
      data[cursor++] = instance.color[1];
      data[cursor++] = instance.color[2];
      data[cursor++] = instance.yaw;
    }
    return data;
  }

  drawInstances(viewProjection, instances, origin, mode, tint) {
    const gl = this.gl;
    const data = this.instanceData(instances, origin, mode);
    gl.useProgram(this.instanceProgram);
    gl.uniformMatrix4fv(this.instanceUniforms.uViewProjection, false, viewProjection);
    gl.uniform3fv(this.instanceUniforms.uTint, tint);
    gl.uniform3fv(this.instanceUniforms.uBackground, BACKGROUND);
    gl.bindVertexArray(this.cube.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.cube.instanceBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
    gl.drawArraysInstanced(gl.TRIANGLES, 0, UNIT_CUBE.count, instances.length);
  }

  drawReference(viewProjection, instances) {
    const gl = this.gl;
    const scratch = this.referenceScratch;
    let cursor = 0;
    const m = viewProjection;

    const pushVertex = (x, y, z, red, green, blue, shade = 1) => {
      scratch[cursor++] = m[0] * x + m[4] * y + m[8] * z + m[12];
      scratch[cursor++] = m[1] * x + m[5] * y + m[9] * z + m[13];
      scratch[cursor++] = m[2] * x + m[6] * y + m[10] * z + m[14];
      scratch[cursor++] = m[3] * x + m[7] * y + m[11] * z + m[15];
      scratch[cursor++] = red * shade;
      scratch[cursor++] = green * shade;
      scratch[cursor++] = blue * shade;
    };

    const positions = this.staticWorld;
    const colors = this.staticColors;
    for (let index = 0; index < positions.length; index += 3) {
      const vertex = index / 3;
      pushVertex(
        positions[index],
        positions[index + 1],
        positions[index + 2],
        colors[vertex * 3],
        colors[vertex * 3 + 1],
        colors[vertex * 3 + 2],
      );
    }

    const cube = UNIT_CUBE.vertices;
    for (const instance of instances) {
      const c = Math.cos(instance.yaw);
      const s = Math.sin(instance.yaw);
      for (let vertex = 0; vertex < UNIT_CUBE.count; vertex += 1) {
        const offset = vertex * 6;
        let lx = cube[offset] * instance.sx;
        const ly = cube[offset + 1] * instance.sy;
        let lz = cube[offset + 2] * instance.sz;
        const nx = cube[offset + 3];
        const ny = cube[offset + 4];
        const nz = cube[offset + 5];
        const rx = c * lx + s * lz;
        const rz = -s * lx + c * lz;
        lx = rx;
        lz = rz;
        const normalX = c * nx + s * nz;
        const normalZ = -s * nx + c * nz;
        const light = 0.64 + Math.max(
          normalX * -0.42 + ny * 0.82 + normalZ * 0.31,
          0,
        ) * 0.42;
        pushVertex(
          instance.x + lx,
          instance.y + ly,
          instance.z + lz,
          instance.color[0],
          instance.color[1],
          instance.color[2],
          light,
        );
      }
    }

    const vertexCount = cursor / 7;
    gl.useProgram(this.referenceProgram);
    gl.uniform3fv(this.referenceUniforms.uBackground, BACKGROUND);
    gl.bindVertexArray(this.reference.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.reference.buffer);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, scratch.subarray(0, cursor));
    gl.drawArrays(gl.TRIANGLES, 0, vertexCount);
  }

  render(frame) {
    const gl = this.gl;
    const { camera, origin, instances } = frame;
    const width = this.pixelWidth;
    const height = this.pixelHeight;
    const paneWidth = Math.floor(width / 3);
    const aspect = paneWidth / height;

    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.disable(gl.SCISSOR_TEST);
    gl.viewport(0, 0, width, height);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.SCISSOR_TEST);

    const modes = [
      { mode: "raw", tint: [1.035, 0.965, 0.955] },
      { mode: "relative", tint: [0.975, 1.025, 1.015] },
      { mode: "reference", tint: [1.02, 1.01, 0.96] },
    ];

    for (let pane = 0; pane < 3; pane += 1) {
      gl.viewport(pane * paneWidth, 0, paneWidth, height);
      gl.scissor(pane * paneWidth, 0, paneWidth, height);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      const mode = modes[pane];
      this.drawSky(mode.tint);
      gl.viewport(pane * paneWidth, 0, paneWidth, height);
      gl.scissor(pane * paneWidth, 0, paneWidth, height);
      gl.clear(gl.DEPTH_BUFFER_BIT);
      if (mode.mode === "reference") {
        this.drawReference(this.referenceMatrix(camera, aspect), instances);
      } else {
        const matrix = this.cameraMatrices(camera, mode.mode, origin, aspect);
        this.drawStatic(matrix, origin, mode.mode, mode.tint);
        this.drawInstances(matrix, instances, origin, mode.mode, mode.tint);
      }
    }

    gl.disable(gl.SCISSOR_TEST);
    gl.bindVertexArray(null);
  }

  static baseBoxes() {
    return STATIC_BOXES;
  }
}

export const RENDER_BACKGROUND = BACKGROUND;
