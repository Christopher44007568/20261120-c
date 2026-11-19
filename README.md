# 20261120-c

程序化星球地形管线：球面 3D 噪声（天然无缝）生成山脉与海洋，
输出高度图/法线图，并附极地映射与 UI 图集验证。

## 运行

```bash
python3 src/planet_terrain.py    # 生成高度场 + 法线 + 元数据
python3 src/verify_sphere.py     # 接缝/极点/纬度带梯度验证 (A-E)
python3 src/polar_caps.py        # 极地帽纹理映射 + 验证 (F)
python3 src/render_previews.py   # 地形预览/星球渲染/梯度图
python3 src/ui_atlas_churn.py    # UI 图集高频增删压力测试
```

产物在 `artifacts/`，映射关系文档见
`docs/spherical_noise_mapping.md`。
