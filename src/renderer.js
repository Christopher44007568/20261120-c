const VERTEX_SHADER = `#version 300 es
in vec2 aPosition;
out vec2 vScreen;

void main() {
  vScreen = aPosition * 0.5 + 0.5;
  gl_Position = vec4(aPosition, 0.0, 1.0);
}
`;

const FRAGMENT_SHADER = `#version 300 es
precision highp float;

in vec2 vScreen;
out vec4 outColor;

uniform sampler2D uField;
uniform vec2 uResolution;
uniform vec2 uGlyphOrigin;
uniform float uDisplayPx;
uniform float uTestPx;
uniform int uViewMode;
uniform bool uChannelTint;
uniform bool uShowGrid;

float median3(float a, float b, float c) {
  return max(min(a, b), min(max(a, b), c));
}

float contourLine(vec2 p, float frequency) {
  float value = sin(p.x * frequency + sin(p.y * frequency * 0.7) * 2.2);
  return smoothstep(0.982, 1.0, abs(value));
}

void main() {
  vec2 screenPx = vScreen * uResolution;
  vec2 glyphUV = vec2(
    (screenPx.x - uGlyphOrigin.x) / uDisplayPx,
    1.0 - (screenPx.y - uGlyphOrigin.y) / uDisplayPx
  );
  bool insideQuad = all(greaterThanEqual(glyphUV, vec2(0.0))) &&
                    all(lessThanEqual(glyphUV, vec2(1.0)));

  vec4 encoded = texture(uField, clamp(glyphUV, vec2(0.0), vec2(1.0)));
  vec3 rgbDistance = encoded.rgb * 2.0 - 1.0;
  float scalarDistance = encoded.a * 2.0 - 1.0;
  float msdfDistance = median3(rgbDistance.r, rgbDistance.g, rgbDistance.b);
  float fieldDistance = uViewMode == 1 || uViewMode == 3 ? scalarDistance : msdfDistance;

  vec2 backgroundP = (screenPx - uResolution * 0.5) / max(uResolution.y, 1.0);
  vec3 backgroundColor = mix(vec3(0.043, 0.105, 0.111), vec3(0.078, 0.153, 0.157), vScreen.y);
  backgroundColor -= contourLine(backgroundP, 23.0) * 0.012;
  float vignette = smoothstep(0.24, 0.86, length(backgroundP));
  backgroundColor *= 1.0 - vignette * 0.22;
  vec3 color = backgroundColor;

  if (insideQuad) {
    float displayPerTestPixel = uDisplayPx / max(uTestPx, 1.0);
    float fwidthDistance = fwidth(fieldDistance) * displayPerTestPixel;
    float pixelRange = max(1e-5, fwidthDistance * 0.5);
    float coverage = smoothstep(-pixelRange, pixelRange, -fieldDistance);
    vec3 ink = vec3(0.955, 0.929, 0.858);

    if (uChannelTint && uViewMode != 1 && uViewMode != 3) {
      float lowest = min(min(rgbDistance.r, rgbDistance.g), rgbDistance.b);
      float spread = max(max(rgbDistance.r, rgbDistance.g), rgbDistance.b) - lowest;
      vec3 weights = max(rgbDistance - vec3(lowest), vec3(0.0));
      float weightSum = max(dot(weights, vec3(1.0)), 0.001);
      vec3 tintColor = (
        weights.r * vec3(1.0, 0.42, 0.30) +
        weights.g * vec3(0.38, 0.92, 0.58) +
        weights.b * vec3(0.36, 0.66, 1.0)
      ) / weightSum;
      float edgeMask = 1.0 - smoothstep(0.0, 0.13, abs(fieldDistance));
      ink = mix(ink, tintColor, clamp(spread * 0.8, 0.0, 0.28) * edgeMask);
    }

    if (uViewMode <= 1) {
      color = mix(backgroundColor, ink, coverage);
    } else if (uViewMode <= 3) {
      vec3 raw = uViewMode == 2 ? rgbDistance * 0.5 + 0.5 : vec3(scalarDistance * 0.5 + 0.5);
      raw = pow(clamp(raw, 0.0, 1.0), vec3(1.18));
      color = mix(backgroundColor, raw, 0.94);
      float isoline = 1.0 - smoothstep(0.0, max(fwidth(fieldDistance) * 1.5, 1e-5), abs(fieldDistance));
      color = mix(color, vec3(0.91, 0.36, 0.18), isoline * 0.72);
    } else {
      color = mix(backgroundColor, ink, coverage * 0.4);
    }
  }

  if (uShowGrid && insideQuad) {
    vec2 testPx = (screenPx - uGlyphOrigin) / max(uDisplayPx / uTestPx, 0.001);
    vec2 gridDelta = abs(fract(testPx + 0.5) - 0.5);
    vec2 gridWidth = max(fwidth(testPx), vec2(0.001));
    float grid = max(
      1.0 - smoothstep(0.0, gridWidth.x * 0.65, gridDelta.x),
      1.0 - smoothstep(0.0, gridWidth.y * 0.65, gridDelta.y)
    );
    vec3 gridColor = uViewMode == 4 ? vec3(0.45, 0.8, 0.82) : vec3(0.55, 0.86, 0.85);
    color = mix(color, gridColor, grid * 0.08);
  }

  outColor = vec4(color, 1.0);
}
`;

function compileShader(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const error = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(error || "Shader compilation failed");
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
    throw new Error(gl.getProgramInfoLog(program) || "Program link failed");
  }
  return program;
}

export class GlyphRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext("webgl2", {
      antialias: true,
      alpha: false,
      premultipliedAlpha: false,
      preserveDrawingBuffer: true,
    });
    if (!this.gl) throw new Error("WebGL2 不可用");
    this.program = createProgram(this.gl);
    this.locations = {
      field: this.gl.getUniformLocation(this.program, "uField"),
      resolution: this.gl.getUniformLocation(this.program, "uResolution"),
      glyphOrigin: this.gl.getUniformLocation(this.program, "uGlyphOrigin"),
      displayPx: this.gl.getUniformLocation(this.program, "uDisplayPx"),
      testPx: this.gl.getUniformLocation(this.program, "uTestPx"),
      viewMode: this.gl.getUniformLocation(this.program, "uViewMode"),
      channelTint: this.gl.getUniformLocation(this.program, "uChannelTint"),
      showGrid: this.gl.getUniformLocation(this.program, "uShowGrid"),
    };
    this.vao = this.gl.createVertexArray();
    this.buffer = this.gl.createBuffer();
    this.texture = this.gl.createTexture();
    this.setupGeometry();
    this.setupTexture();
    this.gl.enable(this.gl.BLEND);
    this.gl.blendFunc(this.gl.SRC_ALPHA, this.gl.ONE_MINUS_SRC_ALPHA);
  }

  setupGeometry() {
    const gl = this.gl;
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
      gl.STATIC_DRAW,
    );
    const position = gl.getAttribLocation(this.program, "aPosition");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);
  }

  setupTexture() {
    const gl = this.gl;
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  }

  uploadField(field) {
    const gl = this.gl;
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      gl.RGBA8,
      field.size,
      field.size,
      0,
      gl.RGBA,
      gl.UNSIGNED_BYTE,
      field.data,
    );
  }

  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(this.canvas.clientWidth * dpr));
    const height = Math.max(1, Math.round(this.canvas.clientHeight * dpr));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    return { width, height, dpr };
  }

  draw(field, options = {}) {
    const gl = this.gl;
    const { width, height } = this.resize();
    const testPx = options.testPx || 48;
    const displayPx = Math.max(80, Math.min(width, height) * 0.76);
    const shiftScale = displayPx / testPx;
    const originX = width * 0.5 - displayPx * 0.5 + (options.shiftX || 0) * shiftScale;
    const originY = height * 0.5 - displayPx * 0.5 + (options.shiftY || 0) * shiftScale;
    const modeMap = {
      msdf: options.raw ? 2 : 0,
      sdf: options.raw ? 3 : 1,
      error: 4,
    };

    gl.viewport(0, 0, width, height);
    gl.clearColor(0.043, 0.105, 0.111, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(this.program);
    gl.bindVertexArray(this.vao);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.uniform1i(this.locations.field, 0);
    gl.uniform2f(this.locations.resolution, width, height);
    gl.uniform2f(this.locations.glyphOrigin, originX, originY);
    gl.uniform1f(this.locations.displayPx, displayPx);
    gl.uniform1f(this.locations.testPx, testPx);
    gl.uniform1i(this.locations.viewMode, modeMap[options.view] ?? 0);
    gl.uniform1i(this.locations.channelTint, options.channelTint === false ? 0 : 1);
    gl.uniform1i(this.locations.showGrid, options.showGrid === false ? 0 : 1);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
    gl.bindVertexArray(null);

    return {
      displayPx,
      originX,
      originY,
      width,
      height,
      zoom: displayPx / testPx,
    };
  }

  readPixels() {
    const gl = this.gl;
    const { width, height } = this.resize();
    const pixels = new Uint8Array(width * height * 4);
    gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    return { pixels, width, height };
  }
}
