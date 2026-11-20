"""Scene setup: pinhole camera, ground-plane UVs (with optional UV seam), textures."""
import numpy as np


def make_checker(size=512, cells=32, c0=(0.05, 0.05, 0.05), c1=(0.95, 0.95, 0.95)):
    """RGB checkerboard texture, `cells` cells across each axis."""
    idx = np.arange(size)
    grid = (idx * cells // size) % 2
    mask = (grid[:, None] ^ grid[None, :]).astype(np.float32)
    tex = np.zeros((size, size, 3), np.float32)
    for i in range(3):
        tex[..., i] = c0[i] * (1 - mask) + c1[i] * mask
    return tex


def plane_uvs(W, H, cam_pos, pitch_deg, fov_deg, uv_scale, seam=None):
    """Perspective ray-plane (y=0) intersection -> per-pixel (u, v).
    seam: None, or ('offset', x_world, du) -> UV islands with a jump of `du`
    in u for world x >= x_world (mimics two UV islands meeting at a seam).
    Returns u, v, mask (True where the ray hits the plane in front)."""
    f = 0.5 * W / np.tan(np.radians(fov_deg) * 0.5)
    px, py = np.meshgrid(np.arange(W) + 0.5 - W / 2, np.arange(H) + 0.5 - H / 2)
    dirs = np.stack([px, -py, np.full_like(px, f)], -1)  # camera looks +z
    th = np.radians(pitch_deg)  # pitch down
    c, s = np.cos(th), np.sin(th)
    rot = np.array([[1, 0, 0], [0, c, -s], [0, s, c]], np.float64)
    dirs = dirs @ rot.T
    pos = np.array(cam_pos, np.float64)
    denom = dirs[..., 1]
    t = -pos[1] / np.where(np.abs(denom) < 1e-9, np.nan, denom)
    hit = t > 0
    p = pos + t[..., None] * dirs
    wx, wz = p[..., 0], p[..., 2]
    u = wx * uv_scale
    v = wz * uv_scale
    if seam is not None:
        _, x_seam, du = seam
        u = np.where(wx >= x_seam, u + du, u)
    return u.astype(np.float32), v.astype(np.float32), hit


def supersample_reference(chain, uv_fn, W, H, ss=4, deriv_uv_fn=None):
    """Ground truth: ss x ss supersampling, per-subpixel smooth derivatives.
    deriv_uv_fn: optional smooth UV mapping used only for the pixel footprint
    (the geometrically correct mip level, ignoring UV-seam discontinuities)."""
    from mipcore import central_derivatives, lambda_from_derivs, sample_trilinear
    u, v, hit = uv_fn(W * ss, H * ss)
    du, dv, _ = (deriv_uv_fn or uv_fn)(W * ss, H * ss)
    tex_w, tex_h = chain[0].shape[1], chain[0].shape[0]
    d = central_derivatives(du, dv)
    lam = lambda_from_derivs(*d, tex_w, tex_h)
    col = sample_trilinear(chain, u, v, lam)
    col = col.reshape(H, ss, W, ss, 3).mean(axis=(1, 3))
    hit = hit.reshape(H, ss, W, ss).any(axis=(1, 3))
    return col.astype(np.float32), hit
