"""
车漆多层反射模拟
================
三层结构:
  顶层 清漆 (clear coat)  : 电介质 n=1.46, 镜面 Fresnel 反射 -> 白色高光
  中层 色漆 (color coat)  : 吸收层, Beer-Lambert 双程吸收 -> 车身颜色
  底层 金属 (metal base)  : 类铝光谱反射率

层间多次内反射用几何级数闭合求和, 保证 R + T + A = 1 (能量守恒).
输出:
  1. 各层反射率与总能量 (多观察角)
  2. 多层高光分离验证 (清漆白色高光 vs 色漆彩色高光)
  3. 不同观察角下的颜色 (sRGB) 与亮度曲线
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ---------------- 光谱采样 ----------------
WL = np.arange(380.0, 701.0, 10.0)          # 波长 nm
NWL = WL.size

# ---------------- 材料光学常数 ----------------
N_CLEAR = 1.46                               # 清漆折射率
D_COLOR = 15e-6                              # 色漆厚度 m

def metal_reflectance(wl_nm):
    """底层金属(类铝)光谱反射率, 0~1"""
    x = (wl_nm - 380.0) / 320.0
    return 0.86 + 0.06 * x                    # 铝在可见光约 0.86~0.92

def color_absorption(wl_nm):
    """色漆吸收系数 sigma(lambda) [1/m], 模拟金属红漆: 强吸收蓝绿, 透红"""
    sigma = np.full_like(wl_nm, 3.0e4)        # 基础吸收
    sigma += 2.2e5 * np.exp(-((wl_nm - 450.0) / 45.0) ** 2)   # 吸收蓝
    sigma += 1.6e5 * np.exp(-((wl_nm - 540.0) / 55.0) ** 2)   # 吸收绿
    sigma += 0.2e5 * np.exp(-((wl_nm - 640.0) / 60.0) ** 2)   # 少吸收红
    return sigma

SIGMA = color_absorption(WL)
R_METAL = metal_reflectance(WL)

# ---------------- Fresnel (非偏振, 电介质) ----------------
def fresnel_dielectric(cos_i, n1, n2):
    """返回 (R, cos_t); 处理全反射"""
    sin2_t = (n1 / n2) ** 2 * (1.0 - cos_i ** 2)
    cos_t = np.sqrt(np.maximum(1.0 - sin2_t, 0.0))
    rs = ((n1 * cos_i - n2 * cos_t) / (n1 * cos_i + n2 * cos_t)) ** 2
    rp = ((n1 * cos_t - n2 * cos_i) / (n1 * cos_t + n2 * cos_i)) ** 2
    return 0.5 * (rs + rp), cos_t

# ---------------- 三层能量守恒叠加 ----------------
def layer_stack(theta_deg):
    """
    给定入射角, 返回:
      R_clear : 清漆顶面 Fresnel 反射 (白色高光)
      R_body  : 色漆+金属底(含层间多次反射)的反射 (彩色)
      A_total : 总吸收
      R_total : 总反射率 (逐波长)
    能量守恒: R_total + A_total = 1 (逐波长)
    """
    cos_i = np.cos(np.radians(theta_deg))
    # 界面1: 空气 -> 清漆
    R1, cos_t = fresnel_dielectric(cos_i, 1.0, N_CLEAR)
    T1 = 1.0 - R1
    # 界面1内侧 (清漆 -> 空气), 用于多次内反射
    R1b, _ = fresnel_dielectric(cos_t, N_CLEAR, 1.0)
    # 色漆双程吸收 (Beer-Lambert)
    path = 2.0 * D_COLOR / cos_t
    trans = np.exp(-SIGMA * path)              # 双程透过率
    # 色漆+金属底 组合反射率 (从清漆底部向下看)
    R2 = R_METAL * trans
    # 多次内反射几何级数: R = R1 + T1*T1b*R2 / (1 - R1b*R2)
    T1b = 1.0 - R1b
    R_body = T1 * T1b * R2 / (1.0 - R1b * R2)
    R_total = R1 + R_body
    # 吸收 = 1 - 总反射 (无透射出基底, 金属底不透光)
    A_total = 1.0 - R_total
    R_clear = np.full(NWL, R1)
    return R_clear, R_body, A_total, R_total

# ---------------- CIE 1931 颜色匹配函数 (Wyman 解析拟合) ----------------
def _g(x, m, s1, s2):
    s = np.where(x < m, s1, s2)
    return np.exp(-0.5 * ((x - m) / s) ** 2)

def cie_xyz(wl):
    x = 1.056 * _g(wl, 599.8, 37.9, 31.0) + 0.362 * _g(wl, 442.0, 16.0, 26.7) \
        - 0.065 * _g(wl, 501.1, 20.4, 26.2)
    y = 0.821 * _g(wl, 568.8, 46.9, 40.5) + 0.286 * _g(wl, 530.9, 16.3, 31.1)
    z = 1.217 * _g(wl, 437.0, 11.8, 36.0) + 0.681 * _g(wl, 459.0, 26.0, 13.8)
    return np.stack([x, y, z], axis=-1)

CMF = cie_xyz(WL)                              # (NWL, 3)
XYZ_NORM = CMF[:, 1].sum()                     # 使等能白 Y=1

def spectrum_to_srgb(spec):
    """反射光谱(等能照明) -> 线性 sRGB (0~1, 未 gamma)"""
    xyz = spec @ CMF / XYZ_NORM
    M = np.array([[ 3.2406, -1.5372, -0.4986],
                  [-0.9689,  1.8758,  0.0415],
                  [ 0.0557, -0.2040,  1.0570]])
    rgb = xyz @ M.T
    return np.clip(rgb, 0.0, 1.0)

def gamma(rgb):
    return np.where(rgb <= 0.0031308, 12.92 * rgb,
                    1.055 * rgb ** (1 / 2.4) - 0.055)

# ---------------- 微表面高光瓣 (Beckmann) ----------------
def beckmann_lobe(theta_view_deg, theta_light_deg, roughness):
    """以镜面方向为中心的归一化高光瓣"""
    d = np.radians(theta_view_deg - theta_light_deg)
    m = max(roughness, 1e-3)
    return np.exp(-(np.tan(d) / m) ** 2) / (np.pi * m ** 2 * np.cos(d) ** 4 + 1e-12)

# ================= 1. 各层反射率与总能量 =================
def report_energy():
    angles = [0, 15, 30, 45, 60, 75, 85]
    print("=" * 78)
    print("【1】各层反射率与总能量 (550 nm 处 / 全谱平均)")
    print("=" * 78)
    hdr = f"{'观察角':>6} | {'清漆层R':>14} | {'色漆+金属R':>16} | {'总反射R':>14} | {'吸收A':>8} | {'R+A':>8}"
    print(hdr); print("-" * 78)
    i550 = int(np.argmin(np.abs(WL - 550)))
    worst = 0.0
    for th in angles:
        Rc, Rb, A, Rt = layer_stack(th)
        row = (f"{th:>5}° | {Rc[i550]:.4f}/{Rc.mean():.4f} | "
               f"{Rb[i550]:.4f}/{Rb.mean():.4f} | "
               f"{Rt[i550]:.4f}/{Rt.mean():.4f} | "
               f"{A.mean():.4f} | {(Rt + A).mean():.4f}")
        print(row)
        worst = max(worst, Rt.max())
    print("-" * 78)
    print(f"全角度全波长最大总反射率 = {worst:.6f}  ->  "
          f"{'能量守恒 OK (<=1)' if worst <= 1.0 + 1e-12 else '能量不守恒!'}")
    return angles

# ================= 2. 多层高光分离验证 =================
def report_highlight_separation():
    print()
    print("=" * 78)
    print("【2】多层高光分离验证 (光源 45°, 清漆窄白高光 vs 色漆宽彩色高光)")
    print("=" * 78)
    th_l = 45.0
    Rc, Rb, _, _ = layer_stack(th_l)
    views = np.linspace(20, 70, 251)
    # 物理加权: 清漆窄而强(镜面), 色漆宽而弱
    lobe_clear = Rc.mean() * beckmann_lobe(views, th_l, 0.02)
    lobe_body = Rb.mean() * beckmann_lobe(views, th_l, 0.18)
    lobe_clear /= lobe_clear.max()
    lobe_body /= lobe_body.max()
    amp_c, amp_b = Rc.mean(), Rb.mean()
    # 高光点处两层的颜色
    rgb_clear = gamma(spectrum_to_srgb(Rc * 1.0))     # 清漆高光光谱平直 -> 白
    rgb_body = gamma(spectrum_to_srgb(Rb / Rb.max())) # 色漆高光 -> 彩色
    chroma_c = rgb_clear.max() - rgb_clear.min()
    chroma_b = rgb_body.max() - rgb_body.min()
    print(f"清漆高光颜色 sRGB = ({rgb_clear[0]:.3f},{rgb_clear[1]:.3f},{rgb_clear[2]:.3f})"
          f"  彩度={chroma_c:.4f} -> 近白(光源色)")
    print(f"色漆高光颜色 sRGB = ({rgb_body[0]:.3f},{rgb_body[1]:.3f},{rgb_body[2]:.3f})"
          f"  彩度={chroma_b:.4f} -> 车身彩色")
    # 分离度: 高光点处白色分量占比 vs 偏峰处
    i_pk = int(np.argmax(lobe_clear))
    at_peak = amp_c * lobe_clear[i_pk] / (amp_c * lobe_clear[i_pk] + amp_b * lobe_body[i_pk])
    off = np.argmin(np.abs(views - (th_l + 12)))
    off_peak = amp_c * lobe_clear[off] / (amp_c * lobe_clear[off] + amp_b * lobe_body[off])
    print(f"镜面方向白色高光占比 {at_peak:.2%}, 偏峰 +12° 处降至 {off_peak:.2%}"
          f" -> 双层高光空间分离")
    return views, lobe_clear, lobe_body

# ================= 3. 观察角 -> 颜色与亮度 =================
def report_color_vs_angle():
    print()
    print("=" * 78)
    print("【3】不同观察角下的颜色与亮度 (等能照明, 亮度=CIE Y)")
    print("=" * 78)
    print(f"{'观察角':>6} | {'sRGB (gamma)':>22} | {'亮度Y':>8} | 色样")
    print("-" * 78)
    angles = np.arange(0, 86, 5)
    rgbs, lum = [], []
    for th in angles:
        _, _, _, Rt = layer_stack(th)
        rgb = gamma(spectrum_to_srgb(Rt))
        y = (Rt @ CMF[:, 1]) / XYZ_NORM
        rgbs.append(rgb); lum.append(y)
        if th % 15 == 0:
            bar = "#" + "".join(f"{int(round(c*255)):02X}" for c in rgb)
            print(f"{th:>5.0f}° | ({rgb[0]:.3f},{rgb[1]:.3f},{rgb[2]:.3f}) | {y:8.4f} | {bar}")
    print("-" * 78)
    print("趋势: 角度增大 -> 清漆 Fresnel 反射增强 -> 颜色变浅(偏白), 亮度上升")
    return angles, np.array(rgbs), np.array(lum)

# ================= 绘图 =================
def make_plots(angles, rgbs, lum, views, lc, lb):
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))

    ax = axes[0, 0]
    for th in [0, 30, 60, 80]:
        Rc, Rb, _, Rt = layer_stack(th)
        ax.plot(WL, Rt, label=f"total {th}°")
    Rc, Rb, _, _ = layer_stack(30)
    ax.plot(WL, Rc, "k--", lw=1, label="clear coat 30°")
    ax.plot(WL, Rb, "r--", lw=1, label="color+metal 30°")
    ax.axhline(1.0, color="gray", ls=":", lw=1)
    ax.set(xlabel="Wavelength (nm)", ylabel="Reflectance",
           title="(a) Layer & total reflectance spectra", ylim=(0, 1.05))
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    ax = axes[0, 1]
    ax.plot(views, lc, "k", label="clear-coat lobe (white)")
    ax.plot(views, lb, "r", label="color-coat lobe (body color)")
    ax.set(xlabel="View angle (deg)", ylabel="Normalized intensity",
           title="(b) Highlight separation (light at 45°)")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    ax = axes[1, 0]
    ax.imshow(rgbs[np.newaxis, :, :], aspect="auto",
              extent=[angles[0], angles[-1], 0, 1])
    ax.set(xlabel="View angle (deg)", yticks=[],
           title="(c) Paint color vs view angle")

    ax = axes[1, 1]
    ax.plot(angles, lum, "o-", color="darkred")
    ax.set(xlabel="View angle (deg)", ylabel="Luminance Y",
           title="(d) Brightness vs view angle")
    ax.grid(alpha=0.3)

    fig.suptitle("Automotive Paint Multi-Layer Reflection Simulation", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig("car_paint_result.png", dpi=130)
    print("\n图已保存: car_paint_result.png")

if __name__ == "__main__":
    report_energy()
    views, lc, lb = report_highlight_separation()
    angles, rgbs, lum = report_color_vs_angle()
    make_plots(angles, rgbs, lum, views, lc, lb)
