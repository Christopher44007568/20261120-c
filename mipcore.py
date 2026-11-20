"""Software simulation of GPU texture sampling: ddx/ddy, mip selection, bias, clamping."""
import numpy as np


def build_mip_chain(tex):
    """Box-filter mip chain down to 1x1. tex: (H,W,C) float32 in [0,1]."""
    chain = [tex.astype(np.float32)]
    while chain[-1].shape[0] > 1 and chain[-1].shape[1] > 1:
        t = chain[-1]
        t2 = 0.25 * (t[0::2, 0::2] + t[1::2, 0::2] + t[0::2, 1::2] + t[1::2, 1::2])
        chain.append(t2.astype(np.float32))
    return chain


def sample_bilinear(tex, u, v):
    """Wrap-mode bilinear sampling. u,v: (...,) arrays in [0,1). Returns (...,C)."""
    h, w = tex.shape[:2]
    x = (np.mod(u, 1.0)) * w - 0.5
    y = (np.mod(v, 1.0)) * h - 0.5
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx = (x - x0)[..., None].astype(np.float32)
    fy = (y - y0)[..., None].astype(np.float32)
    x0w = np.mod(x0, w); x1w = np.mod(x0 + 1, w)
    y0w = np.mod(y0, h); y1w = np.mod(y0 + 1, h)
    c00 = tex[y0w, x0w]; c10 = tex[y0w, x1w]
    c01 = tex[y1w, x0w]; c11 = tex[y1w, x1w]
    top = c00 * (1 - fx) + c10 * fx
    bot = c01 * (1 - fx) + c11 * fx
    return top * (1 - fy) + bot * fy


def sample_trilinear(chain, u, v, lam):
    """Per-pixel trilinear sample at mip level lam (float). u,v,lam: (H,W)."""
    maxl = len(chain) - 1
    lam = np.clip(lam, 0.0, float(maxl)).astype(np.float32)
    l0 = np.minimum(np.floor(lam).astype(np.int64), maxl - 1)
    frac = (lam - l0)[..., None]
    out = np.zeros(u.shape + (chain[0].shape[2],), dtype=np.float32)
    for L in range(maxl):
        m = l0 == L
        if not m.any():
            continue
        a = sample_bilinear(chain[L], u[m], v[m])
        b = sample_bilinear(chain[L + 1], u[m], v[m])
        out[m] = a * (1 - frac[m]) + b * frac[m]
    m = l0 == maxl
    if m.any():
        out[m] = sample_bilinear(chain[maxl], u[m], v[m])
    return out


def quad_derivatives(u, v):
    """Hardware-style derivatives: one forward difference per 2x2 pixel quad,
    broadcast to all 4 pixels of the quad (this is what real GPUs do)."""
    H, W = u.shape
    uq = u.reshape(H // 2, 2, W // 2, 2)
    vq = v.reshape(H // 2, 2, W // 2, 2)
    ddx_u = uq[:, 0, :, 1] - uq[:, 0, :, 0]
    ddx_v = vq[:, 0, :, 1] - vq[:, 0, :, 0]
    ddy_u = uq[:, 1, :, 0] - uq[:, 0, :, 0]
    ddy_v = vq[:, 1, :, 0] - vq[:, 0, :, 0]
    rep = lambda a: np.repeat(np.repeat(a, 2, axis=0), 2, axis=1)
    return rep(ddx_u), rep(ddx_v), rep(ddy_u), rep(ddy_v)


def central_derivatives(u, v):
    """Smooth per-pixel 'manual' derivatives via central differences."""
    ddx_u = 0.5 * (np.roll(u, -1, 1) - np.roll(u, 1, 1))
    ddx_v = 0.5 * (np.roll(v, -1, 1) - np.roll(v, 1, 1))
    ddy_u = 0.5 * (np.roll(u, -1, 0) - np.roll(u, 1, 0))
    ddy_v = 0.5 * (np.roll(v, -1, 0) - np.roll(v, 1, 0))
    return ddx_u, ddx_v, ddy_u, ddy_v


def lambda_from_derivs(ddx_u, ddx_v, ddy_u, ddy_v, tex_w, tex_h, bias=0.0):
    """GPU mip level: lambda = log2(max footprint in texels) + bias."""
    s = np.maximum.reduce([
        np.abs(ddx_u) * tex_w, np.abs(ddx_v) * tex_h,
        np.abs(ddy_u) * tex_w, np.abs(ddy_v) * tex_h,
    ])
    s = np.maximum(s, 1e-6)
    return np.log2(s) + np.float32(bias)


def clamp_derivs(ddx_u, ddx_v, ddy_u, ddy_v, ref, factor=3.0):
    """Clamp derivative jumps: any component whose magnitude exceeds
    factor * |geometric reference| is pulled back to the reference value.
    ref = (r_ddx_u, r_ddx_v, r_ddy_u, r_ddy_v) from a smooth mapping."""
    out = []
    for d, r in zip((ddx_u, ddx_v, ddy_u, ddy_v), ref):
        lim = np.abs(r) * factor + 1e-6
        spike = np.abs(d) > lim
        out.append(np.where(spike, r, d))
    return tuple(out)
