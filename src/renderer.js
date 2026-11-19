import {
  bounds,
  clamp,
  cross,
  dot,
  normalize,
  sub,
} from "./math.js";

const TAU = Math.PI * 2;

function rgba(color, alpha) {
  return `rgba(${color[0]},${color[1]},${color[2]},${alpha})`;
}

export class MeshRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.context = canvas.getContext("2d");
    this.mesh = null;
    this.shadow = null;
    this.mode = "hull";
    this.yaw = -0.72;
    this.pitch = 0.34;
    this.distance = 5;
    this.target = [0, 0, 0];
    this.fov = (42 * Math.PI) / 180;
    this.replayProgress = 0;
    this.showReplay = false;
    this.pointer = null;
    this.width = 1;
    this.height = 1;
    this.dpr = 1;
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas.parentElement);
    this.bindControls();
    this.resize();
  }

  bindControls() {
    this.canvas.addEventListener("pointerdown", (event) => {
      this.pointer = { x: event.clientX, y: event.clientY, yaw: this.yaw, pitch: this.pitch };
      this.canvas.setPointerCapture(event.pointerId);
      this.canvas.classList.add("dragging");
    });
    this.canvas.addEventListener("pointermove", (event) => {
      if (!this.pointer) return;
      const dx = event.clientX - this.pointer.x;
      const dy = event.clientY - this.pointer.y;
      this.yaw = this.pointer.yaw + dx * 0.007;
      this.pitch = clamp(this.pointer.pitch + dy * 0.006, -1.25, 1.25);
      this.draw();
    });
    const release = () => {
      this.pointer = null;
      this.canvas.classList.remove("dragging");
    };
    this.canvas.addEventListener("pointerup", release);
    this.canvas.addEventListener("pointercancel", release);
    this.canvas.addEventListener("wheel", (event) => {
      event.preventDefault();
      this.distance = clamp(this.distance * Math.exp(event.deltaY * 0.0009), 1.6, 24);
      this.draw();
    }, { passive: false });
    this.canvas.addEventListener("dblclick", () => this.resetView());
  }

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.width = Math.max(rect.width, 1);
    this.height = Math.max(rect.height, 1);
    this.canvas.width = Math.round(this.width * this.dpr);
    this.canvas.height = Math.round(this.height * this.dpr);
    this.canvas.style.width = `${this.width}px`;
    this.canvas.style.height = `${this.height}px`;
    this.context.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.draw();
  }

  setMesh(mesh) {
    this.mesh = mesh;
    if (!mesh || mesh.error) return;
    const box = bounds(mesh.points);
    this.target = box.center;
    this.distance = Math.max(box.size * 2.8, 2.2);
    this.yaw = -0.72;
    this.pitch = 0.34;
  }

  setShadow(shadow) {
    this.shadow = shadow;
  }

  setMode(mode) {
    this.mode = mode;
    this.draw();
  }

  setReplay(progress, active = true) {
    this.replayProgress = progress;
    this.showReplay = active;
    this.draw();
  }

  resetView() {
    if (!this.mesh) return;
    const box = bounds(this.mesh.points);
    this.target = box.center;
    this.distance = Math.max(box.size * 2.8, 2.2);
    this.yaw = -0.72;
    this.pitch = 0.34;
    this.draw();
  }

  camera() {
    const cp = Math.cos(this.pitch);
    const eye = [
      this.target[0] + Math.sin(this.yaw) * cp * this.distance,
      this.target[1] + Math.sin(this.pitch) * this.distance,
      this.target[2] + Math.cos(this.yaw) * cp * this.distance,
    ];
    const forward = normalize(sub(this.target, eye));
    const right = normalize(cross(forward, [0, 1, 0]));
    const up = normalize(cross(right, forward));
    return { eye, forward, right, up, focal: this.height / (2 * Math.tan(this.fov / 2)) };
  }

  project(point, camera = this.camera()) {
    const relative = sub(point, camera.eye);
    const z = dot(relative, camera.forward);
    if (z <= 0.03) return null;
    const x = dot(relative, camera.right);
    const y = dot(relative, camera.up);
    const perspective = camera.focal / z;
    return {
      x: this.width * 0.5 + x * perspective,
      y: this.height * 0.5 - y * perspective,
      z,
    };
  }

  draw() {
    const ctx = this.context;
    ctx.clearRect(0, 0, this.width, this.height);
    const background = ctx.createRadialGradient(
      this.width * 0.46,
      this.height * 0.42,
      10,
      this.width * 0.5,
      this.height * 0.5,
      Math.max(this.width, this.height) * 0.78,
    );
    background.addColorStop(0, "#142427");
    background.addColorStop(0.46, "#0b1518");
    background.addColorStop(1, "#060b0d");
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, this.width, this.height);
    if (!this.mesh || this.mesh.error) {
      ctx.fillStyle = "rgba(219,238,233,.55)";
      ctx.font = "12px ui-monospace, monospace";
      ctx.fillText("NO MESH DATA", 24, 34);
      return;
    }
    const camera = this.camera();
    this.drawGrid(camera);
    this.drawFactories(camera);
  }

  drawGrid(camera) {
    const ctx = this.context;
    const box = bounds(this.mesh.points);
    const y = box.min[1] - box.size * 0.12;
    const span = box.size * 1.75;
    const divisions = 8;
    const step = (span * 2) / divisions;
    ctx.save();
    ctx.lineWidth = 1;
    for (let index = 0; index <= divisions; index += 1) {
      const offset = -span + index * step;
      for (const [a, b] of [
        [[box.center[0] - span, y, box.center[2] + offset], [box.center[0] + span, y, box.center[2] + offset]],
        [[box.center[0] + offset, y, box.center[2] - span], [box.center[0] + offset, y, box.center[2] + span]],
      ]) {
        const pa = this.project(a, camera);
        const pb = this.project(b, camera);
        if (!pa || !pb) continue;
        ctx.strokeStyle = index === divisions / 2 ? "rgba(80,188,180,.14)" : "rgba(87,132,130,.075)";
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  drawFactories(camera) {
    const items = [];
    const { mesh, shadow } = this;
    if (this.mode === "shadow" && shadow) {
      for (const triangle of shadow.triangles) {
        const points = triangle.points.map((point) => this.project(point, camera));
        if (points.some((point) => !point)) continue;
        const depth = points.reduce((sum, point) => sum + point.z, 0) / 3;
        items.push({ type: "shadowFace", points, depth, kind: triangle.kind });
      }
    }
    const showHullFaces = this.mode !== "tetra";
    if (showHullFaces) {
      for (const face of mesh.hull.faces) {
        const points = face.vertices.map((index) => this.project(mesh.points[index], camera));
        if (points.some((point) => !point)) continue;
        const depth = points.reduce((sum, point) => sum + point.z, 0) / 3;
        const centroid = face.vertices.reduce(
          (sum, index) => [
            sum[0] + mesh.points[index][0] / 3,
            sum[1] + mesh.points[index][1] / 3,
            sum[2] + mesh.points[index][2] / 3,
          ],
          [0, 0, 0],
        );
        const facing = dot(face.normal, normalize(sub(camera.eye, centroid))) > 0;
        items.push({ type: "hullFace", points, depth, facing });
      }
    } else {
      for (const face of mesh.hull.faces) {
        const points = face.vertices.map((index) => this.project(mesh.points[index], camera));
        if (points.some((point) => !point)) continue;
        const depth = points.reduce((sum, point) => sum + point.z, 0) / 3;
        items.push({ type: "hullGhost", points, depth });
      }
    }
    if (this.mode === "tetra") {
      for (const edge of mesh.tetEdges) {
        const a = this.project(mesh.points[edge.a], camera);
        const b = this.project(mesh.points[edge.b], camera);
        if (!a || !b) continue;
        items.push({ type: "tetEdge", a, b, depth: (a.z + b.z) * 0.5 });
      }
    }
    for (const edge of mesh.hullEdges) {
      const a = this.project(mesh.points[edge.a], camera);
      const b = this.project(mesh.points[edge.b], camera);
      if (!a || !b) continue;
      items.push({ type: "hullEdge", a, b, depth: (a.z + b.z) * 0.5 });
    }
    if (this.shadow && this.mode === "shadow") {
      for (const edge of this.shadow.silhouette) {
        for (const [x, y] of [
          [edge.a, edge.b],
          [edge.a + this.shadow.translatedOffset, edge.b + this.shadow.translatedOffset],
        ]) {
          const a = this.project(this.shadow.vertices[x], camera);
          const b = this.project(this.shadow.vertices[y], camera);
          if (!a || !b) continue;
          items.push({ type: "silhouette", a, b, depth: (a.z + b.z) * 0.5 });
        }
      }
    }
    this.addPointItems(items, camera);
    if (this.shadow) this.addPathItems(items, camera);
    items.sort((a, b) => b.depth - a.depth);
    for (const item of items) this.drawItem(item);
    if (this.shadow) this.drawReplayMarker(camera);
    this.drawAxisTriad(camera);
  }

  addPointItems(items, camera) {
    const mesh = this.mesh;
    const hullSet = mesh.hullVertices ?? new Set();
    for (let index = 0; index < mesh.points.length; index += 1) {
      const projected = this.project(mesh.points[index], camera);
      if (!projected) continue;
      items.push({
        type: "point",
        point: projected,
        depth: projected.z,
        hull: hullSet.has(index),
        synthetic: mesh.synthetic?.has(index) ?? false,
      });
    }
  }

  addPathItems(items, camera) {
    const crossing = this.shadow.crossing;
    if (!crossing) return;
    const a = this.project(crossing.start, camera);
    const b = this.project(crossing.end, camera);
    if (a && b) items.push({ type: "path", a, b, depth: (a.z + b.z) * 0.5 });
    for (const record of crossing.records) {
      const point = this.project(record.position, camera);
      if (point) items.push({ type: "event", point, depth: point.z - 0.001, record });
    }
  }

  drawItem(item) {
    const ctx = this.context;
    if (item.type === "hullFace") {
      const base = item.facing ? [38, 154, 143] : [25, 80, 79];
      ctx.fillStyle = rgba(base, item.facing ? 0.22 : 0.075);
      this.fillPolygon(item.points);
      ctx.strokeStyle = rgba([94, 230, 207], item.facing ? 0.13 : 0.035);
      ctx.lineWidth = 0.7;
      this.strokePolygon(item.points);
    } else if (item.type === "hullGhost") {
      ctx.fillStyle = "rgba(34,95,91,.025)";
      this.fillPolygon(item.points);
    } else if (item.type === "shadowFace") {
      const colors = {
        "near-cap": [50, 232, 189],
        "far-cap": [255, 170, 73],
        side: [124, 128, 255],
      };
      const color = colors[item.kind] ?? [180, 180, 180];
      ctx.fillStyle = rgba(color, item.kind === "side" ? 0.075 : 0.105);
      this.fillPolygon(item.points);
      ctx.strokeStyle = rgba(color, 0.18);
      ctx.lineWidth = 0.55;
      this.strokePolygon(item.points);
    } else if (item.type === "hullEdge") {
      ctx.strokeStyle = "rgba(119,238,216,.48)";
      ctx.lineWidth = 0.9;
      this.line(item.a, item.b);
    } else if (item.type === "tetEdge") {
      ctx.strokeStyle = "rgba(76,184,220,.20)";
      ctx.lineWidth = 0.72;
      this.line(item.a, item.b);
    } else if (item.type === "silhouette") {
      ctx.strokeStyle = "rgba(255,194,110,.58)";
      ctx.lineWidth = 1.2;
      this.line(item.a, item.b);
    } else if (item.type === "path") {
      ctx.save();
      ctx.setLineDash([5, 6]);
      ctx.strokeStyle = "rgba(255,192,104,.55)";
      ctx.lineWidth = 1.2;
      this.line(item.a, item.b);
      ctx.restore();
    } else if (item.type === "event") {
      this.drawEvent(item.point, item.record);
    } else if (item.type === "point") {
      this.drawPoint(item);
    }
  }

  fillPolygon(points) {
    const ctx = this.context;
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let index = 1; index < points.length; index += 1) ctx.lineTo(points[index].x, points[index].y);
    ctx.closePath();
    ctx.fill();
  }

  strokePolygon(points) {
    const ctx = this.context;
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let index = 1; index < points.length; index += 1) ctx.lineTo(points[index].x, points[index].y);
    ctx.closePath();
    ctx.stroke();
  }

  line(a, b) {
    const ctx = this.context;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }

  drawPoint(item) {
    const ctx = this.context;
    const radius = clamp(118 / item.depth, 1.4, 4.8);
    if (item.synthetic) {
      ctx.save();
      ctx.translate(item.point.x, item.point.y);
      ctx.rotate(Math.PI / 4);
      ctx.fillStyle = "rgba(255,185,86,.92)";
      ctx.fillRect(-radius, -radius, radius * 2, radius * 2);
      ctx.restore();
    } else {
      ctx.beginPath();
      ctx.arc(item.point.x, item.point.y, radius, 0, TAU);
      ctx.fillStyle = item.hull ? "rgba(211,255,238,.92)" : "rgba(71,157,159,.68)";
      ctx.fill();
    }
  }

  drawEvent(point, record) {
    const ctx = this.context;
    ctx.save();
    ctx.strokeStyle = record.direction === "enter" ? "rgba(50,232,189,.9)" : "rgba(255,170,73,.9)";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.arc(point.x, point.y, 9, 0, TAU);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(point.x, point.y, 2.2, 0, TAU);
    ctx.fillStyle = ctx.strokeStyle;
    ctx.fill();
    ctx.font = "9px ui-monospace, monospace";
    ctx.fillStyle = "rgba(235,244,239,.78)";
    ctx.fillText(`${record.delta > 0 ? "+" : ""}${record.delta}`, point.x + 12, point.y + 3);
    ctx.restore();
  }

  drawReplayMarker(camera) {
    if (!this.shadow?.crossing || !this.showReplay) return;
    const crossing = this.shadow.crossing;
    const point = [
      crossing.start[0] + (crossing.end[0] - crossing.start[0]) * this.replayProgress,
      crossing.start[1] + (crossing.end[1] - crossing.start[1]) * this.replayProgress,
      crossing.start[2] + (crossing.end[2] - crossing.start[2]) * this.replayProgress,
    ];
    const projected = this.project(point, camera);
    if (!projected) return;
    const ctx = this.context;
    ctx.save();
    ctx.fillStyle = "rgba(255,193,100,.18)";
    ctx.beginPath();
    ctx.arc(projected.x, projected.y, 13, 0, TAU);
    ctx.fill();
    ctx.fillStyle = "rgba(255,209,137,.95)";
    ctx.beginPath();
    ctx.arc(projected.x, projected.y, 4, 0, TAU);
    ctx.fill();
    ctx.strokeStyle = "rgba(255,214,150,.55)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(projected.x, projected.y, 8, 0, TAU);
    ctx.stroke();
    ctx.restore();
  }

  drawAxisTriad(camera) {
    const ctx = this.context;
    const origin = [22, this.height - 28];
    const length = 25;
    const axes = [
      { vector: [1, 0, 0], color: "#de715e", label: "X" },
      { vector: [0, 1, 0], color: "#59d9b4", label: "Y" },
      { vector: [0, 0, 1], color: "#6fa5ef", label: "Z" },
    ];
    ctx.save();
    ctx.font = "9px ui-monospace, monospace";
    for (const axis of axes) {
      const x = dot(axis.vector, camera.right) * length;
      const y = -dot(axis.vector, camera.up) * length;
      ctx.strokeStyle = axis.color;
      ctx.fillStyle = axis.color;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(origin[0], origin[1]);
      ctx.lineTo(origin[0] + x, origin[1] + y);
      ctx.stroke();
      ctx.fillText(axis.label, origin[0] + x * 1.25 - 2, origin[1] + y * 1.25 + 3);
    }
    ctx.restore();
  }
}
