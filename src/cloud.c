#include "cloud.h"
#include "noise.h"
#include <math.h>

CloudParams cloud_preset(CloudType type) {
    CloudParams p;
    p.type = type;
    p.seed = 0.0f;
    if (type == CLOUD_CUMULUS) {
        p.base_m = 800.0f;
        p.top_m = 2600.0f;
        p.coverage = 0.45f;
        p.noise_scale = 1.0f / 900.0f;
        p.detail_scale = 1.0f / 180.0f;
        p.sigma = 0.012f;
        p.octaves = 5;
    } else {
        p.base_m = 600.0f;
        p.top_m = 1400.0f;
        p.coverage = 0.80f;
        p.noise_scale = 1.0f / 2200.0f;
        p.detail_scale = 1.0f / 400.0f;
        p.sigma = 0.020f;
        p.octaves = 4;
    }
    return p;
}

static float clampf(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

static float smoothstep(float a, float b, float x) {
    float t = clampf((x - a) / (b - a), 0.0f, 1.0f);
    return t * t * (3.0f - 2.0f * t);
}

float cloud_height_falloff(const CloudParams *p, float h) {
    if (p->type == CLOUD_CUMULUS) {
        /* sharp base, rounded puffy top: ramp in low, taper near top */
        float in_ramp = smoothstep(0.0f, 0.18f, h);
        float out_ramp = 1.0f - smoothstep(0.55f, 1.0f, h);
        return in_ramp * out_ramp;
    }
    /* stratus: flat-topped layer, soft both edges */
    float in_ramp = smoothstep(0.0f, 0.25f, h);
    float out_ramp = 1.0f - smoothstep(0.75f, 1.0f, h);
    return in_ramp * out_ramp;
}

float cloud_density(const CloudParams *p, float x, float y, float z) {
    if (z < p->base_m || z > p->top_m) return 0.0f;
    float h = (z - p->base_m) / (p->top_m - p->base_m);
    float s = p->noise_scale;
    float base = fbm3(x * s + p->seed, y * s, z * s * 2.0f, p->octaves, 2.0f, 0.5f);
    /* coverage remap: shift threshold so `coverage` fraction stays cloudy */
    float d = base - (1.0f - p->coverage);
    if (d <= 0.0f) return 0.0f;
    d /= p->coverage;
    /* worley erosion on edges for cauliflower look */
    float w = worley3(x * p->detail_scale, y * p->detail_scale,
                      z * p->detail_scale * 2.0f);
    d = clampf(d - 0.35f * (1.0f - d) * (1.0f - w), 0.0f, 1.0f);
    return d * cloud_height_falloff(p, h);
}

CloudStats cloud_stats(const CloudParams *p, float region_m, int grid) {
    CloudStats st = {0, 0, 0, 0, 0, 0};
    float dz = 10.0f;
    int nz = (int)((p->top_m - p->base_m) / dz);
    for (int iy = 0; iy < grid; iy++) {
        for (int ix = 0; ix < grid; ix++) {
            float x = (ix + 0.5f) / grid * region_m - region_m * 0.5f;
            float y = (iy + 0.5f) / grid * region_m - region_m * 0.5f;
            float tau = 0.0f, first = -1.0f, last = -1.0f;
            for (int iz = 0; iz <= nz; iz++) {
                float z = p->base_m + iz * dz;
                float d = cloud_density(p, x, y, z);
                tau += d * p->sigma * dz;
                if (d > 0.02f) {
                    if (first < 0.0f) first = z;
                    last = z;
                }
            }
            st.columns++;
            if (tau > 0.1f) {
                st.cloudy++;
                st.tau_mean += tau;
                float th = (last > first) ? (last - first) : 0.0f;
                st.thickness_mean += th;
                if (th > st.thickness_max) st.thickness_max = th;
            }
        }
    }
    st.coverage = (float)st.cloudy / (float)st.columns;
    if (st.cloudy > 0) {
        st.thickness_mean /= st.cloudy;
        st.tau_mean /= st.cloudy;
    }
    return st;
}
