#include <stdio.h>
#include <stdlib.h>
#include "cloud.h"
#include "render.h"
#include "pngw.h"

static void print_profile(const CloudParams *p) {
    printf("  height profile (density at layer center, falloff-weighted):\n");
    for (int i = 0; i <= 10; i++) {
        float h = i / 10.0f;
        float z = p->base_m + h * (p->top_m - p->base_m);
        float d = cloud_density(p, 120.0f, 340.0f, z);
        printf("    h=%.1f z=%5.0fm falloff=%.3f density=%.3f\n",
               h, z, cloud_height_falloff(p, h), d);
    }
}

static void run_case(CloudType type, const char *name) {
    CloudParams p = cloud_preset(type);
    RenderSettings rs = render_defaults();
    printf("== %s ==\n", name);
    printf("  layer: %.0f-%.0f m, sigma=%.3f 1/m, coverage target=%.2f\n",
           p.base_m, p.top_m, p.sigma, p.coverage);

    CloudStats st = cloud_stats(&p, 12000.0f, 200);
    printf("  measured coverage: %.3f (%d/%d columns)\n",
           st.coverage, st.cloudy, st.columns);
    printf("  thickness: mean=%.0f m, max=%.0f m, mean column tau=%.2f\n",
           st.thickness_mean, st.thickness_max, st.tau_mean);
    print_profile(&p);

    int w = 480, h = 270;
    unsigned char *img = malloc((size_t)w * h * 3);

    double ms = render_sky(&p, &rs, img, w, h, 200.0f, 0.0f, 14.0f, 55.0f);
    char path[256];
    snprintf(path, sizeof path, "out/%s_sky.png", name);
    png_write(path, img, w, h, 3);
    printf("  sky render: %dx%d, %d primary + %d light steps -> %.1f ms (%s)\n",
           w, h, rs.primary_steps, rs.light_steps, ms, path);

    double ms2 = render_ground_shadow(&p, &rs, img, w, h, 12000.0f);
    snprintf(path, sizeof path, "out/%s_shadow.png", name);
    png_write(path, img, w, h, 3);
    printf("  ground shadow map: %.1f ms (%s)\n", ms2, path);

    free(img);
    printf("\n");
}

int main(void) {
    run_case(CLOUD_CUMULUS, "cumulus");
    run_case(CLOUD_STRATUS, "stratus");
    return 0;
}
