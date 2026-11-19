#define _POSIX_C_SOURCE 199309L
#include "render.h"
#include <math.h>
#include <time.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

RenderSettings render_defaults(void) {
    RenderSettings rs;
    float elev = 28.0f * (float)M_PI / 180.0f;
    float azim = 35.0f * (float)M_PI / 180.0f;
    rs.sun_dir[0] = cosf(elev) * sinf(azim);
    rs.sun_dir[1] = cosf(elev) * cosf(azim);
    rs.sun_dir[2] = sinf(elev);
    rs.sun_color[0] = 1.00f; rs.sun_color[1] = 0.96f; rs.sun_color[2] = 0.88f;
    rs.ambient[0] = 0.42f; rs.ambient[1] = 0.50f; rs.ambient[2] = 0.62f;
    rs.hg_g = 0.55f;
    rs.primary_steps = 64;
    rs.light_steps = 6;
    rs.light_step_m = 80.0f;
    return rs;
}

static float hg_phase(float cos_theta, float g) {
    float g2 = g * g;
    float d = 1.0f + g2 - 2.0f * g * cos_theta;
    return (1.0f - g2) / (12.566371f * powf(d, 1.5f));
}

/* Optical depth from pos toward the sun, exiting the layer quickly. */
static float light_optical_depth(const CloudParams *p, const RenderSettings *rs,
                                 float x, float y, float z) {
    float tau = 0.0f;
    float step = rs->light_step_m;
    for (int i = 0; i < rs->light_steps; i++) {
        x += rs->sun_dir[0] * step;
        y += rs->sun_dir[1] * step;
        z += rs->sun_dir[2] * step;
        if (z > p->top_m) break;
        tau += cloud_density(p, x, y, z) * p->sigma * step;
    }
    return tau;
}

static void sky_background(const RenderSettings *rs, const float rd[3],
                           float out[3]) {
    float t = 0.5f * (rd[2] + 1.0f);
    out[0] = 0.30f + 0.25f * t;
    out[1] = 0.50f + 0.30f * t;
    out[2] = 0.85f + 0.15f * t;
    float cos_t = rd[0] * rs->sun_dir[0] + rd[1] * rs->sun_dir[1] +
                  rd[2] * rs->sun_dir[2];
    float glow = powf(cos_t > 0.0f ? cos_t : 0.0f, 350.0f) * 8.0f +
                 powf(cos_t > 0.0f ? cos_t : 0.0f, 16.0f) * 0.25f;
    out[0] += glow * rs->sun_color[0];
    out[1] += glow * rs->sun_color[1];
    out[2] += glow * rs->sun_color[2];
}

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1.0e6;
}

double render_sky(const CloudParams *p, const RenderSettings *rs,
                  unsigned char *img, int w, int h, float cam_z,
                  float yaw_deg, float pitch_deg, float fov_deg) {
    double t0 = now_ms();
    float yaw = yaw_deg * (float)M_PI / 180.0f;
    float pitch = pitch_deg * (float)M_PI / 180.0f;
    float fwd[3] = {cosf(pitch) * sinf(yaw), cosf(pitch) * cosf(yaw), sinf(pitch)};
    float right[3] = {cosf(yaw), -sinf(yaw), 0.0f};
    float up[3] = {-sinf(pitch) * sinf(yaw), -sinf(pitch) * cosf(yaw), cosf(pitch)};
    float tanf2 = tanf(fov_deg * 0.5f * (float)M_PI / 180.0f);
    float aspect = (float)w / (float)h;

    for (int py = 0; py < h; py++) {
        for (int px = 0; px < w; px++) {
            float sx = ((px + 0.5f) / w * 2.0f - 1.0f) * tanf2 * aspect;
            float sy = (1.0f - (py + 0.5f) / h * 2.0f) * tanf2;
            float rd[3] = {
                fwd[0] + sx * right[0] + sy * up[0],
                fwd[1] + sx * right[1] + sy * up[1],
                fwd[2] + sx * right[2] + sy * up[2]};
            float inv = 1.0f / sqrtf(rd[0]*rd[0] + rd[1]*rd[1] + rd[2]*rd[2]);
            rd[0] *= inv; rd[1] *= inv; rd[2] *= inv;

            float col[3];
            sky_background(rs, rd, col);

            /* intersect ray with layer slab [base, top] */
            if (fabsf(rd[2]) > 1e-5f) {
                float tA = (p->base_m - cam_z) / rd[2];
                float tB = (p->top_m - cam_z) / rd[2];
                float t0s = fminf(tA, tB), t1s = fmaxf(tA, tB);
                if (t1s > 0.0f && t1s > t0s) {
                    t0s = fmaxf(t0s, 0.0f);
                    float seg = (t1s - t0s) / rs->primary_steps;
                    float T = 1.0f;
                    float acc[3] = {0, 0, 0};
                    float cos_t = rd[0]*rs->sun_dir[0] + rd[1]*rs->sun_dir[1] +
                                  rd[2]*rs->sun_dir[2];
                    float phase = hg_phase(cos_t, rs->hg_g) * 12.566371f;
                    for (int i = 0; i < rs->primary_steps && T > 0.02f; i++) {
                        float t = t0s + (i + 0.5f) * seg;
                        float x = rd[0] * t, y = rd[1] * t, z = cam_z + rd[2] * t;
                        float d = cloud_density(p, x, y, z);
                        if (d <= 0.0f) continue;
                        float tau_l = light_optical_depth(p, rs, x, y, z);
                        float Tl = expf(-tau_l);
                        /* powder-like edge brightening + strong sun term */
                        float sun_e = 2.6f * phase * Tl;
                        float amb_e = 0.35f + 0.45f * (z - p->base_m) /
                                      (p->top_m - p->base_m);
                        float s = d * p->sigma * seg;
                        acc[0] += T * s * (rs->sun_color[0] * sun_e +
                                           rs->ambient[0] * amb_e);
                        acc[1] += T * s * (rs->sun_color[1] * sun_e +
                                           rs->ambient[1] * amb_e);
                        acc[2] += T * s * (rs->sun_color[2] * sun_e +
                                           rs->ambient[2] * amb_e);
                        T *= expf(-d * p->sigma * seg);
                    }
                    col[0] = col[0] * T + acc[0];
                    col[1] = col[1] * T + acc[1];
                    col[2] = col[2] * T + acc[2];
                }
            }
            unsigned char *pix = img + ((size_t)py * w + px) * 3;
            for (int c = 0; c < 3; c++) {
                float v = col[c] / (1.0f + col[c]);      /* Reinhard */
                v = powf(v < 0 ? 0 : v, 1.0f / 2.2f);    /* gamma */
                pix[c] = (unsigned char)(v * 255.0f + 0.5f);
            }
        }
    }
    return now_ms() - t0;
}

double render_ground_shadow(const CloudParams *p, const RenderSettings *rs,
                            unsigned char *img, int w, int h, float region_m) {
    double t0 = now_ms();
    for (int py = 0; py < h; py++) {
        for (int px = 0; px < w; px++) {
            float x = (px + 0.5f) / w * region_m - region_m * 0.5f;
            float y = (py + 0.5f) / h * region_m - region_m * 0.5f;
            /* march from ground (z=0) toward the sun through the layer */
            float tau = 0.0f;
            float step = 60.0f;
            float sx = x, sy = y, sz = 0.0f;
            for (int i = 0; i < 200 && sz < p->top_m; i++) {
                sx += rs->sun_dir[0] * step;
                sy += rs->sun_dir[1] * step;
                sz += rs->sun_dir[2] * step;
                tau += cloud_density(p, sx, sy, sz) * p->sigma * step;
            }
            float Tl = expf(-tau);
            /* ground albedo lit by sun * transmittance + ambient */
            float ndotl = rs->sun_dir[2];
            float lum = 0.25f + 0.9f * ndotl * Tl;
            unsigned char *pix = img + ((size_t)py * w + px) * 3;
            pix[0] = (unsigned char)(fminf(lum * 0.55f, 1.0f) * 255.0f);
            pix[1] = (unsigned char)(fminf(lum * 0.70f, 1.0f) * 255.0f);
            pix[2] = (unsigned char)(fminf(lum * 0.45f, 1.0f) * 255.0f);
        }
    }
    return now_ms() - t0;
}
