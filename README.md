# Boids 群集模拟 + 各向异性织物高光

## 运行

- 无头验证（避障 / 帧耗时 / 参数形态 / 高光方向）：`npm run verify`
- 可视化演示：`npm run demo` 后打开 http://localhost:8000

## 结构

- `src/boids.js` — 核心模拟：分离 / 对齐 / 聚合三规则 + 球形障碍物避让（径向推离 + 切向绕行）
- `src/demo.js` — Three.js 演示：InstancedMesh 实例化渲染 boids、旋转织物 Kajiya-Kay 各向异性高光
- `verify.mjs` — Node 无头验证脚本

## 参数对群集形态的影响

- 分离 (separation)：增大个体间距，群体更分散（最近邻距离增大）
- 对齐 (alignment)：速度趋同，群体凝聚成队；置零则群体散乱
- 聚合 (cohesion)：群体向质心收拢，回转半径减小、个体更密集
