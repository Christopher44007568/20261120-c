#ifndef CURL_NOISE_H
#define CURL_NOISE_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32) && defined(CURLNOISE_BUILD)
#define CN_API __declspec(dllexport)
#elif defined(_WIN32)
#define CN_API __declspec(dllimport)
#else
#define CN_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define CN_ABI_VERSION 1u
#define CN_MAX_OCTAVES 8u
#define CN_MODES_PER_OCTAVE 6u
#define CN_MAX_MODES (CN_MAX_OCTAVES * CN_MODES_PER_OCTAVE)

typedef struct {
    float x;
    float y;
} CNVec2;

typedef struct {
    uint32_t version;
    uint32_t seed;
    uint32_t octaves;
    uint32_t modes_per_octave;
    float frequency;
    float lacunarity;
    float gain;
    float speed;
    float box_size;
} CNFlowParams;

typedef struct {
    uint32_t version;
    uint32_t seed;
    uint32_t particle_count;
    uint32_t steps;
    uint32_t trace_count;
    uint32_t trace_every;
    float frequency;
    float lacunarity;
    float gain;
    float speed;
    float dt;
    float box_size;
    float jitter;
} CNExperimentConfig;

typedef struct {
    uint32_t id;
    uint32_t flags;
    float x;
    float y;
    float vx;
    float vy;
    float age;
} CNParticle;

typedef struct {
    float x;
    float y;
    float vx;
    float vy;
    float potential;
    float divergence;
    float speed;
} CNFieldSample;

typedef struct {
    uint32_t particle_id;
    uint32_t step;
    float time;
    float x;
    float y;
    float vx;
    float vy;
    float speed;
    float curvature;
} CNTrajectorySample;

typedef struct {
    uint32_t version;
    uint32_t pointer_size;
    uint32_t flow_params_size;
    uint32_t flow_params_align;
    uint32_t experiment_size;
    uint32_t experiment_align;
    uint32_t particle_size;
    uint32_t particle_align;
    uint32_t field_sample_size;
    uint32_t field_sample_align;
    uint32_t trajectory_sample_size;
    uint32_t trajectory_sample_align;
    uint32_t vec2_size;
    uint32_t vec2_align;
    uint32_t particle_stride;
    uint32_t field_sample_stride;
    uint32_t trajectory_sample_stride;
    uint32_t array_rank;
    uint32_t array_order;
    uint32_t struct_count;
    uint32_t scalar_bits;
    uint32_t little_endian;
    uint32_t ieee754_float;
    uint32_t reserved;
} CNLayout;

typedef struct CNField CNField;

CN_API CNFlowParams cn_flow_params_default(void);
CN_API CNExperimentConfig cn_experiment_config_default(void);
CN_API CNLayout cn_abi_layout(void);
CN_API int cn_write_abi_json(const char *path);

CN_API CNField *cn_field_create(const CNFlowParams *params);
CN_API void cn_field_destroy(CNField *field);
CN_API uint32_t cn_field_mode_count(const CNField *field);
CN_API CNVec2 cn_field_velocity(const CNField *field, CNVec2 position);
CN_API void cn_field_velocity_d(const CNField *field, double x, double y,
                                double *vx, double *vy);
CN_API double cn_field_potential_d(const CNField *field, double x, double y);
CN_API double cn_field_curl_d(const CNField *field, double x, double y);
CN_API double cn_field_divergence_d(const CNField *field, double x, double y,
                                    double h);

CN_API void cn_particles_init(CNParticle *particles, uint32_t count,
                              float box_size, uint32_t seed, float jitter);
CN_API void cn_particle_advect(const CNField *field, CNParticle *particles,
                               uint32_t count, float dt, uint32_t steps);

#ifdef __cplusplus
}
#endif

#endif
