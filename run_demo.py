"""Demo: ddx/ddy & mip bias on oblique textures; derivative jumps at UV seams;
clamping; mip-level heatmaps; aliasing/sparkle pixel metrics."""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from mipcore import (build_mip_chain, sample_trilinear, quad_derivatives,
                     central_derivatives, lambda_from_derivs, clamp_derivs)
from scenes import make_checker, plane_uvs, supersample_reference

OUT = "output"
os.makedirs(OUT, exist_ok=True)
W, H = 512, 384


def save_png(name, img):
    img = np.clip(img, 0, 1)
    Image.fromarray((img * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, name))


def save_heatmap(name, lam, hit, maxl):
    """Mip-level heatmap: turbo colormap over [0, maxl], miss pixels black."""
    t = np.clip(lam / max(maxl, 1), 0, 1)
    rgb = plt.get_cmap("turbo")(t)[..., :3].astype(np.float32)
    rgb[~hit] = 0.0
    save_png(name, rgb)


def luminance(c):
    return (c * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1)


def alias_mask(render, ref, hit, thresh=0.2):
    diff = np.abs(luminance(render) - luminance(ref))
    return (diff > thresh) & hit


def save_mask(name, mask, render):
    out = (render * 0.35).copy()
    out[mask] = np.array([1.0, 0.1, 0.1], np.float32)
    save_png(name, out)


def render(chain, u, v, derivs, bias=0.0):
    tw, th = chain[0].shape[1], chain[0].shape[0]
    lam = lambda_from_derivs(*derivs, tw, th, bias)
    return sample_trilinear(chain, u, v, lam), lam


def experiment_A():
    """Oblique plane: hardware quad derivatives vs manual per-pixel mip."""
    print("== A: oblique plane, hardware ddx/ddy vs manual mip ==")
    tex = make_checker(512, cells=32)
    chain = build_mip_chain(tex)
    maxl = len(chain) - 1
    uv_fn = lambda w, h: plane_uvs(w, h, (0, 1.2, 0), 25, 60, 0.15)
    u, v, hit = uv_fn(W, H)
    ref, _ = supersample_reference(chain, uv_fn, W, H)
    save_png("A_reference.png", np.where(hit[..., None], ref, 0))

    hw = quad_derivatives(u, v)
    img_hw, lam_hw = render(chain, u, v, hw)
    man = central_derivatives(u, v)
    img_man, lam_man = render(chain, u, v, man)

    save_png("A_render_hw.png", np.where(hit[..., None], img_hw, 0))
    save_png("A_render_manual.png", np.where(hit[..., None], img_man, 0))
    save_heatmap("A_heatmap_hw.png", lam_hw, hit, maxl)
    save_heatmap("A_heatmap_manual.png", lam_man, hit, maxl)

    m_hw = alias_mask(img_hw, ref, hit)
    m_man = alias_mask(img_man, ref, hit)
    save_mask("A_alias_hw.png", m_hw, img_hw)
    save_mask("A_alias_manual.png", m_man, img_man)
    print(f"  aliasing px  hardware-quad: {m_hw.sum():6d}   manual: {m_man.sum():6d}")
    return chain, uv_fn, ref, hit


def seam_scene(pitch, cam, uv_scale, tag):
    """High-frequency checker, two UV islands offset by 0.5 in u at x=0.
    Renders unclamped vs derivative-clamped, dumps heatmaps + sparkle masks."""
    print(f"== {tag}: seam scene pitch={pitch} ==")
    tex = make_checker(1024, cells=256)
    chain = build_mip_chain(tex)
    maxl = len(chain) - 1
    # seam inside a 2x2 quad (not on a quad boundary) so hardware ddx/ddy spikes
    seam = ("offset", 0.0056, 0.5)
    uv_fn = lambda w, h: plane_uvs(w, h, cam, pitch, 60, uv_scale, seam)
    geo_fn = lambda w, h: plane_uvs(w, h, cam, pitch, 60, uv_scale, None)
    u, v, hit = uv_fn(W, H)
    # ideal reference: sample the seamed UVs, but footprint from smooth geometry
    ref, _ = supersample_reference(chain, uv_fn, W, H, deriv_uv_fn=geo_fn)

    geo = central_derivatives(*geo_fn(W, H)[:2])
    hw = quad_derivatives(u, v)
    img_raw, lam_raw = render(chain, u, v, hw)
    cl = clamp_derivs(*hw, geo, factor=3.0)
    img_cl, lam_cl = render(chain, u, v, cl)

    save_png(f"{tag}_render_unclamped.png", np.where(hit[..., None], img_raw, 0))
    save_png(f"{tag}_render_clamped.png", np.where(hit[..., None], img_cl, 0))
    save_heatmap(f"{tag}_heatmap_unclamped.png", lam_raw, hit, maxl)
    save_heatmap(f"{tag}_heatmap_clamped.png", lam_cl, hit, maxl)

    m_raw = alias_mask(img_raw, ref, hit)
    m_cl = alias_mask(img_cl, ref, hit)
    save_mask(f"{tag}_sparkle_unclamped.png", m_raw, img_raw)
    save_mask(f"{tag}_sparkle_clamped.png", m_cl, img_cl)
    x_seam_px = W // 2
    band = np.zeros((H, W), bool)
    band[:, max(0, x_seam_px - 8):x_seam_px + 8] = True
    print(f"  sparkle px  unclamped: {m_raw.sum():6d} (seam band {(m_raw & band).sum():5d})"
          f"   clamped: {m_cl.sum():6d} (seam band {(m_cl & band).sum():5d})")
    print(f"  lambda at seam  unclamped max: {lam_raw[band & hit].max():.2f}"
          f"   clamped max: {lam_cl[band & hit].max():.2f}")


def experiment_D(chain, uv_fn, ref, hit):
    """Mip bias sweep on the oblique plane: sharpness vs aliasing."""
    print("== D: mip bias sweep (oblique plane) ==")
    u, v, _ = uv_fn(W, H)
    hw = quad_derivatives(u, v)
    biases = [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0]
    sharp, alias = [], []
    gy, gx = np.gradient(luminance(ref))
    band = hit & (np.abs(luminance(ref)) > 0)
    band &= np.indices((H, W))[0] < H // 2  # minified upper half
    for b in biases:
        img, _ = render(chain, u, v, hw, bias=b)
        iy, ix = np.gradient(luminance(img))
        sharp.append(float(np.mean(np.hypot(ix, iy)[band])))
        alias.append(int(alias_mask(img, ref, hit).sum()))
        print(f"  bias {b:+.1f}   sharpness {sharp[-1]:.4f}   aliasing px {alias[-1]}")
    fig, ax1 = plt.subplots(figsize=(6, 4))
    ax1.plot(biases, sharp, "o-", color="tab:blue", label="sharpness (grad mag)")
    ax1.set_xlabel("mip bias"); ax1.set_ylabel("sharpness", color="tab:blue")
    ax2 = ax1.twinx()
    ax2.plot(biases, alias, "s--", color="tab:red", label="aliasing px")
    ax2.set_ylabel("aliasing pixels", color="tab:red")
    ax1.axvline(0, color="gray", lw=0.5)
    fig.suptitle("Mip bias vs sharpness / aliasing (oblique checker)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "D_bias_sharpness.png"), dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    chain, uv_fn, ref, hit = experiment_A()
    seam_scene(pitch=90, cam=(0, 2.0, 0), uv_scale=0.26, tag="B")
    seam_scene(pitch=60, cam=(0, 1.5, 0), uv_scale=0.5, tag="C")
    experiment_D(chain, uv_fn, ref, hit)
