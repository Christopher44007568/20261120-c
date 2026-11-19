// 浏览器演示：InstancedMesh 渲染 boids 群集 + 旋转织物各向异性高光
import * as THREE from 'three';
import { BoidsSimulation } from './boids.js';

const app = document.getElementById('app');
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
app.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0e14);
scene.fog = new THREE.Fog(0x0b0e14, 120, 320);

const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 600);
camera.position.set(0, 42, 105);
camera.lookAt(0, 0, 0);

scene.add(new THREE.HemisphereLight(0x8fb8ff, 0x1a2030, 0.9));
const keyLight = new THREE.DirectionalLight(0xffffff, 1.6);
keyLight.position.set(40, 60, 50);
scene.add(keyLight);

// ---------- 模拟 ----------
const sim = new BoidsSimulation({
  count: 400,
  bounds: 55,
  perceptionRadius: 8,
  separationRadius: 3,
});
sim.addObstacle(0, 0, 0, 9);
sim.addObstacle(-28, 12, -18, 6);
sim.addObstacle(26, -14, 16, 7);

// ---------- 障碍物网格 ----------
const obstacleGroup = new THREE.Group();
for (const ob of sim.obstacles) {
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(ob.radius, 32, 24),
    new THREE.MeshStandardMaterial({
      color: 0xff5a4e, roughness: 0.35, metalness: 0.1,
      transparent: true, opacity: 0.35,
    })
  );
  mesh.position.set(ob.x, ob.y, ob.z);
  obstacleGroup.add(mesh);
  const halo = new THREE.Mesh(
    new THREE.SphereGeometry(ob.radius + sim.params.obstacleMargin, 24, 16),
    new THREE.MeshBasicMaterial({ color: 0xff5a4e, wireframe: true, transparent: true, opacity: 0.08 })
  );
  halo.position.copy(mesh.position);
  obstacleGroup.add(halo);
}
scene.add(obstacleGroup);

// ---------- 实例化 boids ----------
// 圆锥体沿 +Y 指向，用四元数对齐到速度方向
const boidGeo = new THREE.ConeGeometry(0.55, 2.2, 6);
boidGeo.translate(0, 0.6, 0);
const boidMat = new THREE.MeshStandardMaterial({
  color: 0x7fc4ff, roughness: 0.4, metalness: 0.3,
  emissive: 0x12304f, emissiveIntensity: 0.6,
});
const boidMesh = new THREE.InstancedMesh(boidGeo, boidMat, sim.params.count);
boidMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
scene.add(boidMesh);

const _pos = new THREE.Vector3();
const _vel = new THREE.Vector3();
const _quat = new THREE.Quaternion();
const _up = new THREE.Vector3(0, 1, 0);
const _scale = new THREE.Vector3(1, 1, 1);
const _mat = new THREE.Matrix4();

function syncBoidInstances() {
  const { positions, velocities } = sim;
  for (let i = 0; i < sim.params.count; i++) {
    const i3 = i * 3;
    _pos.set(positions[i3], positions[i3 + 1], positions[i3 + 2]);
    _vel.set(velocities[i3], velocities[i3 + 1], velocities[i3 + 2]).normalize();
    _quat.setFromUnitVectors(_up, _vel);
    _mat.compose(_pos, _quat, _scale);
    boidMesh.setMatrixAt(i, _mat);
  }
  boidMesh.instanceMatrix.needsUpdate = true;
}

// ---------- 旋转织物：Kajiya-Kay 各向异性高光 ----------
const fabricUniforms = {
  uTime: { value: 0 },
  uShininess: { value: 48 },
  uLightDir: { value: new THREE.Vector3(0.4, 0.65, 0.55).normalize() },
  uBaseColor: { value: new THREE.Color(0x35328a) },
  uSpecColor: { value: new THREE.Color(0xfff2c8) },
};

const fabricMat = new THREE.ShaderMaterial({
  uniforms: fabricUniforms,
  side: THREE.DoubleSide,
  vertexShader: /* glsl */`
    uniform float uTime;
    varying vec3 vNormal;
    varying vec3 vTangent;   // 织物的切线（纤维/编织方向）
    varying vec3 vWorldPos;
    varying vec2 vUv;

    // 波浪位移及其解析偏导，保证切线/法线与位移严格一致
    float wave(vec2 p, float t) {
      return sin(p.x * 0.35 + t * 1.3) * cos(p.y * 0.28 + t * 0.9) * 2.2
           + sin(p.x * 0.12 - t * 0.7) * 1.4;
    }

    void main() {
      vUv = uv;
      vec3 pos = position;
      float t = uTime;
      float h = wave(pos.xy, t);
      pos.z += h;

      // 数值偏导求切线/法线
      float e = 0.15;
      float hx = wave(pos.xy + vec2(e, 0.0), t) - h;
      float hy = wave(pos.xy + vec2(0.0, e), t) - h;
      vec3 tx = normalize(vec3(e, 0.0, hx)); // 沿编织方向的切线
      vec3 ty = normalize(vec3(0.0, e, hy));
      vNormal = normalize(cross(tx, ty));
      vTangent = normalize((modelMatrix * vec4(tx, 0.0)).xyz);
      vNormal = normalize((modelMatrix * vec4(vNormal, 0.0)).xyz);
      vec4 wp = modelMatrix * vec4(pos, 1.0);
      vWorldPos = wp.xyz;
      gl_Position = projectionMatrix * viewMatrix * wp;
    }
  `,
  fragmentShader: /* glsl */`
    uniform vec3 uLightDir;
    uniform vec3 uBaseColor;
    uniform vec3 uSpecColor;
    uniform float uShininess;
    varying vec3 vNormal;
    varying vec3 vTangent;
    varying vec3 vWorldPos;
    varying vec2 vUv;

    void main() {
      vec3 N = normalize(vNormal);
      vec3 T = normalize(vTangent);
      vec3 L = normalize(uLightDir);
      vec3 V = normalize(cameraPosition - vWorldPos);
      vec3 H = normalize(L + V);

      // 漫反射
      float diff = max(dot(N, L), 0.0);

      // Kajiya-Kay 各向异性高光：强度由切线 T 与半角向量 H 的夹角决定
      float tdh = clamp(dot(T, H), -1.0, 1.0);
      float sinTH = sqrt(max(0.0, 1.0 - tdh * tdh));
      float aniso = pow(sinTH, uShininess);

      // 编织纹理，便于观察织物旋转
      float weave = 0.85 + 0.15 * sin(vUv.x * 220.0) * sin(vUv.y * 220.0);

      vec3 color = uBaseColor * weave * (0.25 + 0.75 * diff)
                 + uSpecColor * aniso * 1.6;
      gl_FragColor = vec4(color, 1.0);
    }
  `,
});

const fabric = new THREE.Mesh(new THREE.PlaneGeometry(70, 70, 160, 160), fabricMat);
fabric.position.set(0, -78, 0);
fabric.rotation.x = -Math.PI / 3;
scene.add(fabric);

// ---------- HUD 与交互 ----------
const el = (id) => document.getElementById(id);
el('statCount').textContent = sim.params.count;

function bindSlider(id, key, fmt = (v) => v.toFixed(2)) {
  const input = el(id);
  const label = el(id + 'V');
  input.value = sim.params[key];
  label.textContent = fmt(sim.params[key]);
  input.addEventListener('input', () => {
    sim.params[key] = parseFloat(input.value);
    label.textContent = fmt(sim.params[key]);
  });
}
bindSlider('sep', 'separationWeight');
bindSlider('ali', 'alignmentWeight');
bindSlider('coh', 'cohesionWeight');

let rotSpeed = 0.6;
el('rotV').textContent = rotSpeed.toFixed(2);
el('rotSpeed').addEventListener('input', (e) => {
  rotSpeed = parseFloat(e.target.value);
  el('rotV').textContent = rotSpeed.toFixed(2);
});
el('shiV').textContent = fabricUniforms.uShininess.value;
el('shininess').addEventListener('input', (e) => {
  fabricUniforms.uShininess.value = parseFloat(e.target.value);
  el('shiV').textContent = e.target.value;
});

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ---------- 主循环 ----------
const clock = new THREE.Clock();
let frameMsAvg = 0;
let simMsAvg = 0;
let hudTimer = 0;

function animate() {
  requestAnimationFrame(animate);
  const frameStart = performance.now();
  const dt = Math.min(clock.getDelta(), 1 / 30);

  const simStart = performance.now();
  sim.update(dt);
  const simMs = performance.now() - simStart;

  syncBoidInstances();

  // 织物绕自身法线旋转：切线场转动 -> 各向异性高光方向同步转动
  fabric.rotation.z += rotSpeed * dt;
  fabricUniforms.uTime.value += dt;

  // 相机缓慢环绕
  const t = clock.elapsedTime * 0.08;
  camera.position.x = Math.sin(t) * 110;
  camera.position.z = Math.cos(t) * 110;
  camera.lookAt(0, -10, 0);

  renderer.render(scene, camera);

  const frameMs = performance.now() - frameStart;
  frameMsAvg = frameMsAvg * 0.95 + frameMs * 0.05;
  simMsAvg = simMsAvg * 0.95 + simMs * 0.05;

  hudTimer += dt;
  if (hudTimer > 0.25) {
    hudTimer = 0;
    el('statFrame').textContent = frameMsAvg.toFixed(2);
    el('statSim').textContent = simMsAvg.toFixed(2);
    el('statClearance').textContent = sim.minObstacleClearance().toFixed(2);
  }
}
animate();
