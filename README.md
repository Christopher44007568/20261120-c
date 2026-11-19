# 20261120-c

迭代式 L-system 植物生成 + 高频棋盘 mip 边界钳制验证。仅依赖 Python 3
标准库（含自研 PNG 编码器 `proctree/imaging.py`），无需 numpy / pip。

## 运行

```bash
bash scripts/run_all.sh
```

也可分步运行：`scripts/run_experiments.py`（多深度生成与包围盒/层级统计）、
`scripts/rule_sweep.py`（规则参数对枝条分布的影响）、
`scripts/mip_heatmap.py`（斜视角 mip 热图与钳制闪点检测）。
测试：`python3 -m unittest discover -s tests`（10 个用例）。

## L-system 规则参数

- `upright_tree`：公理 `F`，规则 `F -> F[+F]F[-F][F]`，转角 20°，步长 1.0，
  每次迭代产生 4 个分叉、形态收敛直立。
- `spreading_bush`：公理 `X`，规则
  `X -> F+[[XL]-XL]-F[-FXL]+L`、`F -> FF`，转角 28°，步长 0.85，
  `L` 在末梢生成叶片，形态更开展。
- turtle 指令：`F/A` 前进成枝、`+/-` 转向、`[ ]` 压栈/出栈并形成新枝条层级、
  `L` 生叶；每个枝段记录其递归层级，包围盒在解释过程中实时累积。

## 不同递归深度的树形对比

| 规则 | 深度 | 枝段实例 | 叶片实例 | 最大层级 | 包围盒 (宽×高) | 耗时 ms |
| --- | --- | --- | --- | --- | --- | --- |
| upright_tree | 3 | 125 | 0 | 3 | 6.13 × 15.00 | 0.14 |
| upright_tree | 4 | 625 | 0 | 4 | 13.89 × 31.00 | 0.33 |
| upright_tree | 5 | 3125 | 0 | 5 | 29.41 × 63.00 | 1.52 |
| upright_tree | 6 | 15625 | 0 | 6 | 60.45 × 127.00 | 9.06 |
| spreading_bush | 3 | 57 | 52 | 5 | 9.98 × 15.01 | 0.09 |
| spreading_bush | 4 | 195 | 160 | 7 | 22.82 × 30.63 | 0.18 |
| spreading_bush | 5 | 633 | 484 | 9 | 47.93 × 62.13 | 0.55 |
| spreading_bush | 6 | 1995 | 1456 | 11 | 97.58 × 124.87 | 1.09 |

逐深度的层级实例数写入 `artifacts/plant_report.json` 的 `levels` 字段；
自然度启发式校验（枝段单调增加、高度不回缩、层级不丢失、包围盒非退化）全部通过。
对比面板见 `artifacts/*_comparison.svg`，单深度树形见 `artifacts/*_d{3..6}.svg`。

## 规则参数对枝条分布与密度的影响

同深度 5、仅改转角时，冠幅宽度随转角单调变宽：12° → 19.05，22° → 31.62，
38° → 43.89（单位同步长）。替换为更密的产生式
`F -> FF[+F][-F][+F][-F]` 后，同深度枝段实例由 3125 增至 7776，
密度显著上升。完整数据见 `artifacts/rule_sweep.json`。

## mip 热图与边界钳制

512×512、64×64 格高频棋盘经 box 滤波生成 10 级 mip 链；斜视角
（shear 0.9）渲染 256×256 视图，纹理坐标越过 1.0 后按
`GL_CLAMP_TO_EDGE` 钳制，并对越界采样强制 LOD ≥ 4（16×16 平均）。
`artifacts/mip_lod_heatmap.png` 为 LOD 热图（蓝 0 → 红 4），
`artifacts/oblique_color.png` 为斜视图，`artifacts/clamp_mask.png`
标注钳制区域。闪点检测（钳制区内相邻像素最大差）结果为 0.0，
阈值 0.2，结论：边界钳制无闪点，见 `artifacts/mip_report.json`。
