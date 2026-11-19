#ifndef CLOUD_H
#define CLOUD_H

typedef enum { CLOUD_CUMULUS = 0, CLOUD_STRATUS = 1 } CloudType;

typedef struct {
    CloudType type;
    float base_m;        /* cloud layer bottom (m) */
    float top_m;         /* cloud layer top (m) */
    float coverage;      /* 0..1 target coverage */
    float noise_scale;   /* horizontal noise frequency (1/m) */
    float detail_scale;  /* erosion noise frequency (1/m) */
    float sigma;         /* extinction coefficient (1/m) at density 1 */
    int   octaves;
    float seed;
} CloudParams;

CloudParams cloud_preset(CloudType type);

/* Density in [0,1] at world position (x east, y north, z up, meters). */
float cloud_density(const CloudParams *p, float x, float y, float z);

/* Height falloff profile h in [0,1] -> multiplier in [0,1]. */
float cloud_height_falloff(const CloudParams *p, float h);

typedef struct {
    float coverage;       /* fraction of columns with tau > 0.1 */
    float thickness_mean; /* mean vertical thickness of cloudy columns (m) */
    float thickness_max;  /* max vertical thickness (m) */
    float tau_mean;       /* mean column optical depth over cloudy columns */
    int   columns;        /* sampled columns */
    int   cloudy;         /* columns with cloud */
} CloudStats;

/* Grid statistics over a square region centered on origin. */
CloudStats cloud_stats(const CloudParams *p, float region_m, int grid);

#endif
