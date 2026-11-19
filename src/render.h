#ifndef RENDER_H
#define RENDER_H
#include "cloud.h"

typedef struct {
    float sun_dir[3];     /* normalized, points toward the sun */
    float sun_color[3];
    float ambient[3];
    float hg_g;           /* Henyey-Greenstein asymmetry */
    int   primary_steps;
    int   light_steps;
    float light_step_m;
} RenderSettings;

RenderSettings render_defaults(void);

/* Sky view: perspective camera looking at the cloud layer. */
double render_sky(const CloudParams *p, const RenderSettings *rs,
                  unsigned char *img, int w, int h, float cam_z,
                  float yaw_deg, float pitch_deg, float fov_deg);

/* Top-down sun transmittance map: shows cloud shadows on the ground. */
double render_ground_shadow(const CloudParams *p, const RenderSettings *rs,
                            unsigned char *img, int w, int h, float region_m);

#endif
