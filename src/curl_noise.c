#define _GNU_SOURCE

#include "curl_noise.h"

#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

typedef struct {
    double kx;
    double ky;
    double phase;
    double amplitude;
    double inv_k;
} CNMode;

struct CNField {
    CNFlowParams params;
    CNMode modes[CN_MAX_MODES];
    uint32_t mode_count;
    double amplitude_scale;
};

static uint32_t rng_next(uint32_t *state) {
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

static double rng_unit(uint32_t *state) {
    return (double)(rng_next(state) >> 8) * (1.0 / 16777216.0);
}

static double clamp_d(double value, double lo, double hi) {
    if (value < lo) {
        return lo;
    }
    if (value > hi) {
        return hi;
    }
    return value;
}

static uint32_t clamp_u32(uint32_t value, uint32_t lo, uint32_t hi) {
    if (value < lo) {
        return lo;
    }
    if (value > hi) {
        return hi;
    }
    return value;
}

static CNFlowParams sanitize_params(const CNFlowParams *input) {
    CNFlowParams p = input == NULL ? cn_flow_params_default() : *input;
    p.version = CN_ABI_VERSION;
    p.octaves = clamp_u32(p.octaves, 1u, CN_MAX_OCTAVES);
    p.modes_per_octave = clamp_u32(p.modes_per_octave, 1u,
                                   CN_MODES_PER_OCTAVE);
    p.frequency = (float)clamp_d((double)p.frequency, 0.25, 32.0);
    p.lacunarity = (float)clamp_d((double)p.lacunarity, 1.05, 4.0);
    p.gain = (float)clamp_d((double)p.gain, 0.0, 1.0);
    p.speed = (float)clamp_d((double)p.speed, 0.001, 32.0);
    p.box_size = (float)clamp_d((double)p.box_size, 0.01, 1000.0);
    if (p.seed == 0u) {
        p.seed = 0x9e3779b9u;
    }
    return p;
}

static int mode_is_duplicate(const CNMode *modes, uint32_t count, double kx,
                             double ky) {
    uint32_t i;
    for (i = 0; i < count; ++i) {
        if (fabs(modes[i].kx - kx) < 1e-12 &&
            fabs(modes[i].ky - ky) < 1e-12) {
            return 1;
        }
    }
    return 0;
}

static void build_modes(CNField *field) {
    uint32_t state = field->params.seed;
    uint32_t octave;
    double variance = 0.0;
    const double two_pi = 2.0 * M_PI;
    const double box = (double)field->params.box_size;

    field->mode_count = 0u;
    for (octave = 0; octave < field->params.octaves; ++octave) {
        uint32_t mode_index;
        double base = (double)field->params.frequency *
                      pow((double)field->params.lacunarity, (double)octave);
        double octave_amplitude = pow((double)field->params.gain,
                                      (double)octave);
        for (mode_index = 0; mode_index < field->params.modes_per_octave;
             ++mode_index) {
            double angle = two_pi * rng_unit(&state);
            double radial = 0.82 + 0.36 * rng_unit(&state);
            double nx = nearbyint(base * radial * cos(angle));
            double ny = nearbyint(base * radial * sin(angle));
            double norm;
            double amp;
            CNMode *mode;

            if (nx == 0.0 && ny == 0.0) {
                nx = cos(angle) >= 0.0 ? 1.0 : -1.0;
            }
            if (mode_is_duplicate(field->modes, field->mode_count,
                                  nx, ny)) {
                ny += ny >= 0.0 ? 1.0 : -1.0;
            }
            norm = hypot(nx, ny);
            amp = octave_amplitude * (0.78 + 0.44 * rng_unit(&state));
            mode = &field->modes[field->mode_count++];
            mode->kx = two_pi * nx / box;
            mode->ky = two_pi * ny / box;
            mode->phase = two_pi * rng_unit(&state);
            mode->amplitude = amp;
            mode->inv_k = 1.0 / (two_pi * norm / box);
            variance += 0.5 * amp * amp;
        }
    }
    field->amplitude_scale =
        variance > 0.0 ? (double)field->params.speed / sqrt(variance) : 0.0;
}

static inline void sin_cos(double angle, double *sine, double *cosine) {
#if defined(__GNUC__) && !defined(__clang__)
    sincos(angle, sine, cosine);
#else
    *sine = sin(angle);
    *cosine = cos(angle);
#endif
}

static void evaluate_raw(const CNField *field, double x, double y,
                         double *vx, double *vy, double *potential,
                         double *curl) {
    uint32_t i;
    double sum_x = 0.0;
    double sum_y = 0.0;
    double sum_psi = 0.0;
    double sum_curl = 0.0;
    for (i = 0; i < field->mode_count; ++i) {
        const CNMode *mode = &field->modes[i];
        double angle = mode->kx * x + mode->ky * y + mode->phase;
        double sine;
        double cosine;
        sin_cos(angle, &sine, &cosine);
        sum_x -= mode->amplitude * mode->ky * mode->inv_k * cosine;
        sum_y += mode->amplitude * mode->kx * mode->inv_k * cosine;
        sum_psi -= mode->amplitude * mode->inv_k * sine;
        sum_curl -= mode->amplitude *
                    (mode->kx * mode->kx + mode->ky * mode->ky) *
                    mode->inv_k * sine;
    }
    if (vx != NULL) {
        *vx = sum_x * field->amplitude_scale;
    }
    if (vy != NULL) {
        *vy = sum_y * field->amplitude_scale;
    }
    if (potential != NULL) {
        *potential = sum_psi * field->amplitude_scale;
    }
    if (curl != NULL) {
        *curl = sum_curl * field->amplitude_scale;
    }
}

CNField *cn_field_create(const CNFlowParams *params) {
    CNField *field = (CNField *)calloc(1u, sizeof(*field));
    if (field == NULL) {
        return NULL;
    }
    field->params = sanitize_params(params);
    build_modes(field);
    return field;
}

void cn_field_destroy(CNField *field) {
    free(field);
}

uint32_t cn_field_mode_count(const CNField *field) {
    return field == NULL ? 0u : field->mode_count;
}

void cn_field_velocity_d(const CNField *field, double x, double y,
                         double *vx, double *vy) {
    if (field == NULL) {
        if (vx != NULL) {
            *vx = 0.0;
        }
        if (vy != NULL) {
            *vy = 0.0;
        }
        return;
    }
    evaluate_raw(field, x, y, vx, vy, NULL, NULL);
}

CNVec2 cn_field_velocity(const CNField *field, CNVec2 position) {
    CNVec2 velocity;
    double vx;
    double vy;
    cn_field_velocity_d(field, (double)position.x, (double)position.y,
                        &vx, &vy);
    velocity.x = (float)vx;
    velocity.y = (float)vy;
    return velocity;
}

double cn_field_potential_d(const CNField *field, double x, double y) {
    double value = 0.0;
    if (field != NULL) {
        evaluate_raw(field, x, y, NULL, NULL, &value, NULL);
    }
    return value;
}

double cn_field_curl_d(const CNField *field, double x, double y) {
    double value = 0.0;
    if (field != NULL) {
        evaluate_raw(field, x, y, NULL, NULL, NULL, &value);
    }
    return value;
}

double cn_field_divergence_d(const CNField *field, double x, double y,
                             double h) {
    double vx_plus;
    double vy_plus;
    double vx_minus;
    double vy_minus;
    if (field == NULL || !(h > 0.0) || !isfinite(h)) {
        return 0.0;
    }
    cn_field_velocity_d(field, x + h, y, &vx_plus, &vy_plus);
    cn_field_velocity_d(field, x - h, y, &vx_minus, &vy_minus);
    {
        double dvx_dx = (vx_plus - vx_minus) / (2.0 * h);
        double vy_at_plus;
        double vy_at_minus;
        cn_field_velocity_d(field, x, y + h, NULL, &vy_at_plus);
        cn_field_velocity_d(field, x, y - h, NULL, &vy_at_minus);
        return dvx_dx + (vy_at_plus - vy_at_minus) / (2.0 * h);
    }
}

static double wrap_period(double value, double period) {
    double wrapped = fmod(value, period);
    if (wrapped < 0.0) {
        wrapped += period;
    }
    if (wrapped >= period) {
        wrapped -= period;
    }
    return wrapped;
}

void cn_particles_init(CNParticle *particles, uint32_t count, float box_size,
                       uint32_t seed, float jitter) {
    uint32_t i;
    uint32_t state = seed == 0u ? 0x85ebca6bu : seed;
    double box = box_size > 0.0f ? (double)box_size : 1.0;
    double spacing = sqrt(box * box / (double)(count == 0u ? 1u : count));
    double jitter_amount = clamp_d((double)jitter, 0.0, 1.0);
    const double alpha = 0.7548776662466927;
    const double beta = 0.5698402909980532;

    for (i = 0; i < count; ++i) {
        double base_x = fmod(0.5 + alpha * (double)i, 1.0) * box;
        double base_y = fmod(0.5 + beta * (double)i, 1.0) * box;
        double dx = (rng_unit(&state) - 0.5) * jitter_amount * spacing;
        double dy = (rng_unit(&state) - 0.5) * jitter_amount * spacing;
        particles[i].id = i;
        particles[i].flags = 0u;
        particles[i].x = (float)wrap_period(base_x + dx, box);
        particles[i].y = (float)wrap_period(base_y + dy, box);
        particles[i].vx = 0.0f;
        particles[i].vy = 0.0f;
        particles[i].age = 0.0f;
    }
}

void cn_particle_advect(const CNField *field, CNParticle *particles,
                        uint32_t count, float dt, uint32_t steps) {
    uint32_t step;
    uint32_t i;
    double box;
    double h;
    if (field == NULL || particles == NULL || count == 0u ||
        !(dt > 0.0f) || !isfinite(dt)) {
        return;
    }
    box = (double)field->params.box_size;
    h = 0.5 * (double)dt;
    for (step = 0; step < steps; ++step) {
        for (i = 0; i < count; ++i) {
            double x0 = (double)particles[i].x;
            double y0 = (double)particles[i].y;
            double k1x;
            double k1y;
            double k2x;
            double k2y;
            double k3x;
            double k3y;
            double k4x;
            double k4y;

            cn_field_velocity_d(field, x0, y0, &k1x, &k1y);
            cn_field_velocity_d(field, wrap_period(x0 + h * k1x, box),
                                wrap_period(y0 + h * k1y, box),
                                &k2x, &k2y);
            cn_field_velocity_d(field, wrap_period(x0 + h * k2x, box),
                                wrap_period(y0 + h * k2y, box),
                                &k3x, &k3y);
            cn_field_velocity_d(field, wrap_period(x0 + (double)dt * k3x, box),
                                wrap_period(y0 + (double)dt * k3y, box),
                                &k4x, &k4y);
            particles[i].x =
                (float)wrap_period(x0 + (double)dt / 6.0 *
                                           (k1x + 2.0 * k2x + 2.0 * k3x + k4x),
                                   box);
            particles[i].y =
                (float)wrap_period(y0 + (double)dt / 6.0 *
                                           (k1y + 2.0 * k2y + 2.0 * k3y + k4y),
                                   box);
            particles[i].age += dt;
        }
    }
    for (i = 0; i < count; ++i) {
        double vx;
        double vy;
        cn_field_velocity_d(field, (double)particles[i].x,
                            (double)particles[i].y, &vx, &vy);
        particles[i].vx = (float)vx;
        particles[i].vy = (float)vy;
    }
}
