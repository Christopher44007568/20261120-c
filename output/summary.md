# ddx/ddy 与 mip 偏置演示结果

软件光栅化模拟 GPU 采样管线（`mipcore.py`）：2x2 quad 前向差分（硬件 ddx/ddy 语义）、
mip 链 + 三线性采样、λ = log2(最大 texel 足迹) + bias。场景见 `scenes.py`，实验见 `run_demo.py`。

## A. 斜角平面：硬件导数 vs 手动 mip 选择
- 硬件：每个 2x2 quad 共享一条前向差分；手动：逐像素中心差分（平滑 λ）。
- 走样像素（相对 4x4 超采样参考，阈值 0.2）：硬件 2816，手动 3884。
- 结论：quad 导数取 quad 内最大足迹，λ 系统性偏高约 0.5 级 → 略过模糊、走样更少；
  手动逐像素 λ 更锐利，但在 mip 过渡带（中距离）走样像素更多。
- 文件：`A_render_hw.png` / `A_render_manual.png`、`A_heatmap_hw.png` / `A_heatmap_manual.png`、
  `A_alias_hw.png` / `A_alias_manual.png`（红色 = 走样像素）。

## B. 高频棋盘（1024², 256 格）+ UV 接缝（正视）
- 两个 UV 岛在 x=0 处 u 偏移 0.5，跨越接缝的 quad 的 ddx(u) 跳变约 0.5 → λ 从 0.26 跳到 9.0。
- 未钳制：接缝处 mip 被打到最粗级，接缝带 638 个闪点像素（`B_sparkle_unclamped.png` 红线），
  热图 `B_heatmap_unclamped.png` 出现 λ=9 的红色竖线。
- 钳制（|d| > 3×几何参考导数时回退到几何值）：接缝 λ 回到 0.26，闪点 0，
  热图 `B_heatmap_clamped.png` 均匀。

## C. 高频棋盘 + UV 接缝（斜视 60°）
- 未钳制：接缝 λ 跳到 9.0，225 个闪点（223 在接缝带），热图红色接缝线延伸至中景。
- 钳制后：接缝 λ 回到几何值（最大 2.03，与周围一致），接缝带闪点 0，
  热图 `C_heatmap_clamped.png` 为平滑梯度，确认斜视下接缝无闪点。

## D. mip 偏置对清晰度的影响（斜角平面）
| bias | 清晰度(梯度幅值) | 走样像素 |
|------|------|------|
| -2.0 | 0.2003 | 15722 |
| -1.0 | 0.1739 | 2680 |
| -0.5 | 0.1582 |  994 |
|  0.0 | 0.1404 | 2816 |
| +0.5 | 0.1221 | 8906 |
| +1.0 | 0.1014 | 18706 |
| +2.0 | 0.0585 | 46596 |
- 清晰度随偏置单调下降；走样像素呈 U 形，在 bias ≈ -0.5 处最少
  （负偏置恰好补偿 quad 前向差分的系统性高估）。
- 曲线图：`D_bias_sharpness.png`。

复现：`PYTHONPATH=/home/hj/.local/lib/python3.14/site-packages python3 run_demo.py`
