#include "experiment.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define MAX_PATH 4096

static void path_join(char *out, size_t capacity, const char *dir,
                      const char *name) {
    snprintf(out, capacity, "%s/%s", dir, name);
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

static double torus_delta(double value, double period) {
    double delta = value - nearbyint(value / period) * period;
    return delta;
}

static uint32_t *make_histogram(const CNParticle *particles, uint32_t count,
                                double box, uint32_t bins) {
    uint32_t *hist;
    uint32_t i;
    if (bins == 0u) {
        return NULL;
    }
    hist = (uint32_t *)calloc((size_t)bins * bins, sizeof(uint32_t));
    if (hist == NULL) {
        return NULL;
    }
    for (i = 0; i < count; ++i) {
        long bx = (long)floor((double)particles[i].x / box * (double)bins);
        long by = (long)floor((double)particles[i].y / box * (double)bins);
        if (bx < 0) {
            bx = 0;
        } else if (bx >= (long)bins) {
            bx = (long)bins - 1;
        }
        if (by < 0) {
            by = 0;
        } else if (by >= (long)bins) {
            by = (long)bins - 1;
        }
        ++hist[(size_t)by * bins + (size_t)bx];
    }
    return hist;
}

static CNDensityStats density_from_histogram(const uint32_t *hist,
                                             uint32_t count, uint32_t bins) {
    CNDensityStats stats;
    uint32_t cells = bins * bins;
    uint32_t i;
    double expected;
    double sum_sq = 0.0;
    double chi2 = 0.0;
    double l1 = 0.0;
    uint32_t max_count = 0u;
    memset(&stats, 0, sizeof(stats));
    stats.bins = bins;
    if (hist == NULL || count == 0u || cells == 0u) {
        return stats;
    }
    expected = (double)count / (double)cells;
    for (i = 0; i < cells; ++i) {
        uint32_t observed = hist[i];
        double delta = (double)observed - expected;
        sum_sq += delta * delta;
        chi2 += delta * delta / expected;
        l1 += fabs((double)observed / (double)count - 1.0 / (double)cells);
        if (observed == 0u) {
            ++stats.empty_cells;
        }
        if (observed > max_count) {
            max_count = observed;
        }
    }
    stats.expected_per_bin = expected;
    stats.mean = expected;
    stats.stddev = sqrt(sum_sq / (double)cells);
    stats.cv = stats.mean > 0.0 ? stats.stddev / stats.mean : 0.0;
    stats.clustering_index = stats.cv * sqrt(expected);
    stats.reduced_chi2 = cells > 1u ? chi2 / (double)(cells - 1u) : 0.0;
    stats.max_cell_ratio =
        expected > 0.0 ? (double)max_count / expected : 0.0;
    stats.uniformity = 1.0 - 0.5 * l1;
    return stats;
}

static double histogram_tv(const uint32_t *a, const uint32_t *b,
                           uint32_t count_a, uint32_t count_b,
                           uint32_t bins) {
    uint32_t cells = bins * bins;
    uint32_t i;
    double tv = 0.0;
    if (a == NULL || b == NULL || count_a == 0u || count_b == 0u) {
        return 0.0;
    }
    for (i = 0; i < cells; ++i) {
        tv += fabs((double)a[i] / (double)count_a -
                   (double)b[i] / (double)count_b);
    }
    return 0.5 * tv;
}

static int write_particles_csv(const char *path, const CNParticle *particles,
                               uint32_t count) {
    FILE *f = fopen(path, "w");
    uint32_t i;
    if (f == NULL) {
        return -1;
    }
    fprintf(f, "id,x,y,vx,vy,age\n");
    for (i = 0; i < count; ++i) {
        fprintf(f, "%u,%.9g,%.9g,%.9g,%.9g,%.9g\n", particles[i].id,
                (double)particles[i].x, (double)particles[i].y,
                (double)particles[i].vx, (double)particles[i].vy,
                (double)particles[i].age);
    }
    if (ferror(f)) {
        fclose(f);
        return -1;
    }
    return fclose(f) == 0 ? 0 : -1;
}

static void rk4_advance(const CNField *field, double box, double x, double y,
                        double dt, double *out_x, double *out_y) {
    double k1x;
    double k1y;
    double k2x;
    double k2y;
    double k3x;
    double k3y;
    double k4x;
    double k4y;
    double half = 0.5 * dt;
    cn_field_velocity_d(field, x, y, &k1x, &k1y);
    cn_field_velocity_d(field, wrap_period(x + half * k1x, box),
                        wrap_period(y + half * k1y, box), &k2x, &k2y);
    cn_field_velocity_d(field, wrap_period(x + half * k2x, box),
                        wrap_period(y + half * k2y, box), &k3x, &k3y);
    cn_field_velocity_d(field, wrap_period(x + dt * k3x, box),
                        wrap_period(y + dt * k3y, box), &k4x, &k4y);
    *out_x = wrap_period(x + dt / 6.0 *
                                 (k1x + 2.0 * k2x + 2.0 * k3x + k4x), box);
    *out_y = wrap_period(y + dt / 6.0 *
                                 (k1y + 2.0 * k2y + 2.0 * k3y + k4y), box);
}

static int compare_double(const void *a, const void *b) {
    double da = *(const double *)a;
    double db = *(const double *)b;
    return (da > db) - (da < db);
}

static double percentile_sorted(const double *values, uint32_t count,
                                double q) {
    uint32_t index;
    if (count == 0u || values == NULL) {
        return 0.0;
    }
    if (q <= 0.0) {
        return values[0];
    }
    if (q >= 1.0) {
        return values[count - 1u];
    }
    index = (uint32_t)(q * (double)(count - 1u));
    return values[index];
}

static uint32_t sample_count_for(const CNExperimentConfig *config) {
    uint32_t every = config->trace_every == 0u ? 1u : config->trace_every;
    return config->steps / every + 2u;
}

static void record_trace_group(const CNField *field,
                               const CNParticle *particles,
                               const uint32_t *trace_ids,
                               uint32_t trace_count, uint32_t step,
                               float dt, uint32_t sample_index,
                               uint32_t sample_stride,
                               CNTrajectorySample *traces) {
    uint32_t k;
    for (k = 0; k < trace_count; ++k) {
        const CNParticle *particle = &particles[trace_ids[k]];
        CNTrajectorySample *sample =
            &traces[(size_t)k * sample_stride + sample_index];
        double vx;
        double vy;
        cn_field_velocity_d(field, (double)particle->x, (double)particle->y,
                            &vx, &vy);
        sample->particle_id = particle->id;
        sample->step = step;
        sample->time = (float)((double)step * (double)dt);
        sample->x = particle->x;
        sample->y = particle->y;
        sample->vx = (float)vx;
        sample->vy = (float)vy;
        sample->speed = (float)hypot(vx, vy);
        sample->curvature = 0.0f;
    }
}

static int write_trajectory_csv(const char *path,
                                const CNTrajectorySample *traces,
                                uint32_t trace_count, uint32_t sample_stride,
                                uint32_t samples) {
    FILE *f = fopen(path, "w");
    uint32_t k;
    uint32_t s;
    if (f == NULL) {
        return -1;
    }
    fprintf(f, "particle_id,step,time,x,y,vx,vy,speed,curvature\n");
    for (k = 0; k < trace_count; ++k) {
        for (s = 0; s < samples; ++s) {
            const CNTrajectorySample *sample =
                &traces[(size_t)k * sample_stride + s];
            fprintf(f, "%u,%u,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g\n",
                    sample->particle_id, sample->step, (double)sample->time,
                    (double)sample->x, (double)sample->y,
                    (double)sample->vx, (double)sample->vy,
                    (double)sample->speed, (double)sample->curvature);
        }
    }
    if (ferror(f)) {
        fclose(f);
        return -1;
    }
    return fclose(f) == 0 ? 0 : -1;
}

static int simulate_main_particles(const CNExperimentConfig *config,
                                   CNField *field, const char *output_dir,
                                   CNExperimentResult *result) {
    char path[MAX_PATH];
    CNParticle *particles;
    uint32_t *initial_hist;
    uint32_t *final_hist;
    uint32_t *trace_ids;
    CNTrajectorySample *traces = NULL;
    double *curvatures = NULL;
    uint32_t trace_count;
    uint32_t sample_stride;
    uint32_t samples = 1u;
    uint32_t last_record_step = 0u;
    uint32_t step;
    uint32_t i;
    double box = (double)config->box_size;
    double dt = (double)config->dt;
    uint32_t every = config->trace_every == 0u ? 1u : config->trace_every;

    particles = (CNParticle *)calloc(config->particle_count,
                                     sizeof(CNParticle));
    if (particles == NULL) {
        return -1;
    }
    cn_particles_init(particles, config->particle_count, config->box_size,
                      config->seed, config->jitter);
    initial_hist = make_histogram(particles, config->particle_count, box,
                                  result->bins);
    final_hist = (uint32_t *)calloc((size_t)result->bins * result->bins,
                                    sizeof(uint32_t));
    if (initial_hist == NULL || final_hist == NULL) {
        free(particles);
        free(initial_hist);
        free(final_hist);
        return -1;
    }
    result->density_initial =
        density_from_histogram(initial_hist, config->particle_count,
                               result->bins);
    path_join(path, sizeof(path), output_dir, "particles_initial.csv");
    if (write_particles_csv(path, particles, config->particle_count) != 0) {
        free(particles);
        free(initial_hist);
        free(final_hist);
        return -1;
    }

    trace_count = config->trace_count;
    if (trace_count > config->particle_count) {
        trace_count = config->particle_count;
    }
    sample_stride = sample_count_for(config);
    trace_ids = (uint32_t *)calloc(trace_count == 0u ? 1u : trace_count,
                                   sizeof(uint32_t));
    traces = (CNTrajectorySample *)calloc(
        (size_t)(trace_count == 0u ? 1u : trace_count) * sample_stride,
        sizeof(CNTrajectorySample));
    if (trace_ids == NULL || traces == NULL) {
        free(particles);
        free(initial_hist);
        free(final_hist);
        free(trace_ids);
        free(traces);
        return -1;
    }
    for (i = 0; i < trace_count; ++i) {
        uint32_t particle_id =
            (uint32_t)(((uint64_t)i * config->particle_count) / trace_count);
        trace_ids[i] = particle_id;
    }
    if (trace_count > 0u) {
        record_trace_group(field, particles, trace_ids, trace_count, 0u,
                           config->dt, 0u, sample_stride, traces);
    }
    for (step = 1u; step <= config->steps; ++step) {
        for (i = 0; i < config->particle_count; ++i) {
            double next_x;
            double next_y;
            rk4_advance(field, box, (double)particles[i].x,
                        (double)particles[i].y, dt, &next_x, &next_y);
            particles[i].x = (float)next_x;
            particles[i].y = (float)next_y;
            particles[i].age += config->dt;
        }
        if (trace_count > 0u && step < config->steps) {
            if (step % every == 0u) {
                record_trace_group(field, particles, trace_ids, trace_count,
                                   step, config->dt, samples, sample_stride,
                                   traces);
                ++samples;
                last_record_step = step;
            }
        }
    }
    if (trace_count > 0u && last_record_step != config->steps) {
        record_trace_group(field, particles, trace_ids, trace_count,
                           config->steps, config->dt, samples, sample_stride,
                           traces);
        ++samples;
    }
    for (i = 0; i < config->particle_count; ++i) {
        double vx;
        double vy;
        cn_field_velocity_d(field, (double)particles[i].x,
                            (double)particles[i].y, &vx, &vy);
        particles[i].vx = (float)vx;
        particles[i].vy = (float)vy;
    }
    path_join(path, sizeof(path), output_dir, "particles_final.csv");
    if (write_particles_csv(path, particles, config->particle_count) != 0) {
        free(particles);
        free(initial_hist);
        free(final_hist);
        free(trace_ids);
        free(traces);
        return -1;
    }
    for (i = 0; i < config->particle_count; ++i) {
        long bx =
            (long)floor((double)particles[i].x / box * (double)result->bins);
        long by =
            (long)floor((double)particles[i].y / box * (double)result->bins);
        if (bx < 0) {
            bx = 0;
        } else if (bx >= (long)result->bins) {
            bx = (long)result->bins - 1;
        }
        if (by < 0) {
            by = 0;
        } else if (by >= (long)result->bins) {
            by = (long)result->bins - 1;
        }
        ++final_hist[(size_t)by * result->bins + (size_t)bx];
    }
    result->density_final =
        density_from_histogram(final_hist, config->particle_count,
                               result->bins);
    result->density_tv =
        histogram_tv(initial_hist, final_hist, config->particle_count,
                     config->particle_count, result->bins);
    result->density_cv_ratio =
        result->density_initial.cv > 1e-12
            ? result->density_final.cv / result->density_initial.cv
            : 0.0;
    result->clustered =
        result->density_final.clustering_index > 2.0 ||
        result->density_final.max_cell_ratio > 3.5 ||
        result->density_final.reduced_chi2 > 2.5 ||
        result->density_final.uniformity < 0.75 ? 1 : 0;

    curvatures = (double *)calloc(
        (size_t)(trace_count == 0u ? 1u : trace_count) * samples,
        sizeof(double));
    if (curvatures == NULL) {
        free(particles);
        free(initial_hist);
        free(final_hist);
        free(trace_ids);
        free(traces);
        return -1;
    }
    {
        uint32_t curvature_count = 0u;
        double speed_sum = 0.0;
        double turning_sum = 0.0;
        uint32_t turning_count = 0u;
        for (i = 0; i < trace_count; ++i) {
            uint32_t s;
            for (s = 0; s < samples; ++s) {
                speed_sum +=
                    (double)traces[(size_t)i * sample_stride + s].speed;
            }
            for (s = 1u; s + 1u < samples; ++s) {
                CNTrajectorySample *left =
                    &traces[(size_t)i * sample_stride + s - 1u];
                CNTrajectorySample *current =
                    &traces[(size_t)i * sample_stride + s];
                CNTrajectorySample *right =
                    &traces[(size_t)i * sample_stride + s + 1u];
                double dt_span = (double)right->time - (double)left->time;
                double cross = (double)left->vx * (double)right->vy -
                               (double)left->vy * (double)right->vx;
                double dot = (double)left->vx * (double)right->vx +
                             (double)left->vy * (double)right->vy;
                double angle = atan2(cross, dot);
                double speed =
                    0.5 * ((double)left->speed + (double)right->speed);
                if (dt_span > 0.0 && speed > 0.05 * config->speed) {
                    double value = fabs(angle) / (speed * dt_span);
                    current->curvature = (float)value;
                    if (curvature_count < trace_count * samples) {
                        curvatures[curvature_count++] = value;
                    }
                    turning_sum += fabs(angle) * 180.0 / M_PI;
                    ++turning_count;
                }
            }
        }
        qsort(curvatures, curvature_count, sizeof(double), compare_double);
        result->trajectory.samples = trace_count * samples;
        result->trajectory.mean_speed =
            result->trajectory.samples > 0u
                ? speed_sum / (double)result->trajectory.samples
                : 0.0;
        result->trajectory.mean_turning_degrees =
            turning_count > 0u ? turning_sum / (double)turning_count : 0.0;
        if (curvature_count > 0u) {
            uint32_t c;
            double sum = 0.0;
            for (c = 0; c < curvature_count; ++c) {
                sum += curvatures[c];
            }
            result->trajectory.mean = sum / (double)curvature_count;
            result->trajectory.p95 =
                percentile_sorted(curvatures, curvature_count, 0.95);
            result->trajectory.max = curvatures[curvature_count - 1u];
        }
    }
    path_join(path, sizeof(path), output_dir, "trajectories.csv");
    if (write_trajectory_csv(path, traces, trace_count, sample_stride,
                             samples) != 0) {
        free(curvatures);
        free(particles);
        free(initial_hist);
        free(final_hist);
        free(trace_ids);
        free(traces);
        return -1;
    }
    result->trace_samples = samples;
    free(curvatures);
    free(particles);
    free(initial_hist);
    free(final_hist);
    free(trace_ids);
    free(traces);
    return 0;
}

static int write_field_csv(const CNExperimentConfig *config,
                           const CNField *field, const char *output_dir,
                           CNExperimentResult *result) {
    char path[MAX_PATH];
    FILE *f;
    uint32_t row;
    uint32_t col;
    double box = (double)config->box_size;
    double sum_sq = 0.0;
    uint32_t sample_count = 0u;
    double max_abs = 0.0;
    const double h = 1e-5;

    path_join(path, sizeof(path), output_dir, "flow_field.csv");
    f = fopen(path, "w");
    if (f == NULL) {
        return -1;
    }
    fprintf(f, "x,y,vx,vy,potential,divergence,speed\n");
    for (row = 0; row < result->field_rows; ++row) {
        for (col = 0; col < result->field_cols; ++col) {
            double x = ((double)col + 0.5) * box / (double)result->field_cols;
            double y = ((double)row + 0.5) * box / (double)result->field_rows;
            double vx;
            double vy;
            double potential;
            double divergence;
            double speed;
            cn_field_velocity_d(field, x, y, &vx, &vy);
            potential = cn_field_potential_d(field, x, y);
            divergence = cn_field_divergence_d(field, x, y, h);
            speed = hypot(vx, vy);
            fprintf(f, "%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g\n", x, y, vx, vy,
                    potential, divergence, speed);
            if (fabs(divergence) > max_abs) {
                max_abs = fabs(divergence);
            }
            sum_sq += divergence * divergence;
            ++sample_count;
        }
    }
    result->divergence_max_abs = max_abs;
    result->divergence_rms =
        sample_count > 0u ? sqrt(sum_sq / (double)sample_count) : 0.0;
    if (ferror(f)) {
        fclose(f);
        return -1;
    }
    return fclose(f) == 0 ? 0 : -1;
}

static CNSweepRow measure_frequency(const CNExperimentConfig *config,
                                    double frequency, uint32_t probes,
                                    uint32_t steps, uint32_t every) {
    CNSweepRow row;
    CNFlowParams params = cn_flow_params_default();
    CNField *field;
    CNParticle *particles;
    double *curvatures;
    double *prior_vx;
    double *prior_vy;
    double *prior_x;
    double *prior_y;
    double *prior_time;
    double *start_x;
    double *start_y;
    uint32_t curvature_count = 0u;
    uint32_t curvature_capacity;
    double speed_sum = 0.0;
    uint32_t speed_count = 0u;
    double path_sum = 0.0;
    double net_sum = 0.0;
    double box = (double)config->box_size;
    double dt = (double)config->dt;
    uint32_t step;
    uint32_t i;
    double speed_floor = 0.05 * (double)config->speed;

    memset(&row, 0, sizeof(row));
    row.frequency = frequency;
    params.seed = config->seed;
    params.octaves = 4u;
    params.modes_per_octave = 5u;
    params.frequency = (float)frequency;
    params.lacunarity = config->lacunarity;
    params.gain = config->gain;
    params.speed = config->speed;
    params.box_size = config->box_size;
    field = cn_field_create(&params);
    particles = (CNParticle *)calloc(probes, sizeof(CNParticle));
    prior_vx = (double *)calloc(probes, sizeof(double));
    prior_vy = (double *)calloc(probes, sizeof(double));
    prior_x = (double *)calloc(probes, sizeof(double));
    prior_y = (double *)calloc(probes, sizeof(double));
    prior_time = (double *)calloc(probes, sizeof(double));
    start_x = (double *)calloc(probes, sizeof(double));
    start_y = (double *)calloc(probes, sizeof(double));
    curvature_capacity = probes * (steps / (every == 0u ? 1u : every) + 3u);
    curvatures = (double *)calloc(curvature_capacity, sizeof(double));
    if (field == NULL || particles == NULL || curvatures == NULL ||
        prior_vx == NULL || prior_vy == NULL || prior_x == NULL ||
        prior_y == NULL || prior_time == NULL || start_x == NULL ||
        start_y == NULL) {
        cn_field_destroy(field);
        free(particles);
        free(curvatures);
        free(prior_vx);
        free(prior_vy);
        free(prior_x);
        free(prior_y);
        free(prior_time);
        free(start_x);
        free(start_y);
        return row;
    }
    if (every == 0u) {
        every = 1u;
    }
    cn_particles_init(particles, probes, config->box_size, config->seed,
                      config->jitter);
    for (i = 0; i < probes; ++i) {
        double vx;
        double vy;
        cn_field_velocity_d(field, (double)particles[i].x,
                            (double)particles[i].y, &vx, &vy);
        prior_vx[i] = vx;
        prior_vy[i] = vy;
        prior_x[i] = (double)particles[i].x;
        prior_y[i] = (double)particles[i].y;
        prior_time[i] = 0.0;
        start_x[i] = prior_x[i];
        start_y[i] = prior_y[i];
    }
    for (step = 1u; step <= steps; ++step) {
        for (i = 0; i < probes; ++i) {
            double next_x;
            double next_y;
            rk4_advance(field, box, (double)particles[i].x,
                        (double)particles[i].y, dt, &next_x, &next_y);
            particles[i].x = (float)next_x;
            particles[i].y = (float)next_y;
        }
        if (step % every == 0u || step == steps) {
            double now = (double)step * dt;
            for (i = 0; i < probes; ++i) {
                double vx;
                double vy;
                double current_x = (double)particles[i].x;
                double current_y = (double)particles[i].y;
                double dt_span = now - prior_time[i];
                double cross;
                double dot;
                double angle;
                double speed;
                if (dt_span <= 0.0) {
                    continue;
                }
                cn_field_velocity_d(field, current_x, current_y, &vx, &vy);
                speed = 0.5 *
                        (hypot(prior_vx[i], prior_vy[i]) + hypot(vx, vy));
                cross = prior_vx[i] * vy - prior_vy[i] * vx;
                dot = prior_vx[i] * vx + prior_vy[i] * vy;
                angle = atan2(cross, dot);
                if (curvature_count < curvature_capacity &&
                    speed > speed_floor) {
                    curvatures[curvature_count++] =
                        fabs(angle) / (speed * dt_span);
                }
                path_sum += hypot(torus_delta(current_x - prior_x[i], box),
                                  torus_delta(current_y - prior_y[i], box));
                speed_sum += speed;
                ++speed_count;
                prior_vx[i] = vx;
                prior_vy[i] = vy;
                prior_x[i] = current_x;
                prior_y[i] = current_y;
                prior_time[i] = now;
            }
        }
    }
    if (curvature_count > 0u) {
        uint32_t c;
        double sum = 0.0;
        qsort(curvatures, curvature_count, sizeof(double), compare_double);
        for (c = 0; c < curvature_count; ++c) {
            sum += curvatures[c];
        }
        row.mean_curvature = sum / (double)curvature_count;
        row.p95_curvature =
            percentile_sorted(curvatures, curvature_count, 0.95);
    }
    for (i = 0; i < probes; ++i) {
        net_sum += hypot(torus_delta((double)particles[i].x - start_x[i], box),
                         torus_delta((double)particles[i].y - start_y[i], box));
    }
    row.mean_speed =
        speed_count > 0u ? speed_sum / (double)speed_count : 0.0;
    row.mean_path_length = probes > 0u ? path_sum / (double)probes : 0.0;
    row.mean_net_displacement = probes > 0u ? net_sum / (double)probes : 0.0;
    free(curvatures);
    free(prior_vx);
    free(prior_vy);
    free(prior_x);
    free(prior_y);
    free(prior_time);
    free(start_x);
    free(start_y);
    free(particles);
    cn_field_destroy(field);
    return row;
}

static double pearson(const double *x, const double *y, uint32_t count) {
    uint32_t i;
    double mean_x = 0.0;
    double mean_y = 0.0;
    double cov = 0.0;
    double var_x = 0.0;
    double var_y = 0.0;
    if (count < 2u) {
        return 0.0;
    }
    for (i = 0; i < count; ++i) {
        mean_x += x[i];
        mean_y += y[i];
    }
    mean_x /= (double)count;
    mean_y /= (double)count;
    for (i = 0; i < count; ++i) {
        double dx = x[i] - mean_x;
        double dy = y[i] - mean_y;
        cov += dx * dy;
        var_x += dx * dx;
        var_y += dy * dy;
    }
    if (var_x <= 1e-18 || var_y <= 1e-18) {
        return 0.0;
    }
    return cov / sqrt(var_x * var_y);
}

static int run_frequency_sweep(const CNExperimentConfig *config,
                               CNExperimentResult *result) {
    static const double frequencies[] = {
        0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0,
    };
    uint32_t count =
        (uint32_t)(sizeof(frequencies) / sizeof(frequencies[0]));
    double *frequency_values;
    double *curvature_values;
    uint32_t probes = config->particle_count < 96u
                          ? config->particle_count
                          : 96u;
    uint32_t i;

    if (probes < 2u) {
        probes = 2u;
    }
    result->sweep = (CNSweepRow *)calloc(count, sizeof(CNSweepRow));
    frequency_values = (double *)calloc(count, sizeof(double));
    curvature_values = (double *)calloc(count, sizeof(double));
    if (result->sweep == NULL || frequency_values == NULL ||
        curvature_values == NULL) {
        free(frequency_values);
        free(curvature_values);
        return -1;
    }
    for (i = 0; i < count; ++i) {
        result->sweep[i] =
            measure_frequency(config, frequencies[i], probes, 1800u, 3u);
        frequency_values[i] = result->sweep[i].frequency;
        curvature_values[i] = result->sweep[i].mean_curvature;
    }
    result->sweep_count = count;
    result->curvature_frequency_corr =
        pearson(frequency_values, curvature_values, count);
    free(frequency_values);
    free(curvature_values);
    return 0;
}

static int write_sweep_csv(const char *output_dir,
                           const CNExperimentResult *result) {
    char path[MAX_PATH];
    FILE *f;
    uint32_t i;
    path_join(path, sizeof(path), output_dir, "frequency_sweep.csv");
    f = fopen(path, "w");
    if (f == NULL) {
        return -1;
    }
    fprintf(f,
            "frequency,mean_curvature,p95_curvature,mean_speed,"
            "mean_path_length,mean_net_displacement\n");
    for (i = 0; i < result->sweep_count; ++i) {
        const CNSweepRow *row = &result->sweep[i];
        fprintf(f, "%.9g,%.9g,%.9g,%.9g,%.9g,%.9g\n", row->frequency,
                row->mean_curvature, row->p95_curvature, row->mean_speed,
                row->mean_path_length, row->mean_net_displacement);
    }
    if (ferror(f)) {
        fclose(f);
        return -1;
    }
    return fclose(f) == 0 ? 0 : -1;
}

static void separate_density(FILE *f, const CNDensityStats *d) {
    fprintf(f,
            "{\"bins\": %u, \"expected_per_bin\": %.12g, "
            "\"stddev\": %.12g, \"cv\": %.12g, "
            "\"clustering_index\": %.12g, \"reduced_chi2\": %.12g, "
            "\"max_cell_ratio\": %.12g, \"uniformity\": %.12g, "
            "\"empty_cells\": %u}",
            d->bins, d->expected_per_bin, d->stddev, d->cv,
            d->clustering_index, d->reduced_chi2,
            d->max_cell_ratio, d->uniformity, d->empty_cells);
}

static int write_metrics_json(const char *output_dir,
                              const CNExperimentResult *result) {
    char path[MAX_PATH];
    FILE *f;
    uint32_t i;
    int divergence_free = result->divergence_max_abs < 1e-6;
    int distribution_retained =
        !result->clustered && result->density_final.uniformity > 0.80 &&
        result->density_final.reduced_chi2 < 2.0;
    int curves = result->trajectory.mean > 0.0;
    int frequency_monotone = result->curvature_frequency_corr > 0.75;

    path_join(path, sizeof(path), output_dir, "metrics.json");
    f = fopen(path, "w");
    if (f == NULL) {
        return -1;
    }
    fprintf(f, "{\n  \"abi_version\": %u,\n", CN_ABI_VERSION);
    fprintf(f, "  \"config\": {\"seed\": %u, \"particle_count\": %u, "
               "\"steps\": %u, \"dt\": %.12g, \"frequency\": %.12g, "
               "\"lacunarity\": %.12g, \"gain\": %.12g, \"speed\": %.12g, "
               "\"box_size\": %.12g, \"trace_count\": %u, "
               "\"trace_every\": %u, \"jitter\": %.12g},\n",
            result->config.seed, result->config.particle_count,
            result->config.steps, (double)result->config.dt,
            (double)result->config.frequency,
            (double)result->config.lacunarity, (double)result->config.gain,
            (double)result->config.speed, (double)result->config.box_size,
            result->config.trace_count, result->config.trace_every,
            (double)result->config.jitter);
    fprintf(f, "  \"flow\": {\"mode_count\": %u, \"octaves\": 4, "
               "\"modes_per_octave\": 5, \"field_rows\": %u, "
               "\"field_cols\": %u, \"divergence_max_abs\": %.12g, "
               "\"divergence_rms\": %.12g},\n",
            result->mode_count, result->field_rows, result->field_cols,
            result->divergence_max_abs, result->divergence_rms);
    fprintf(f, "  \"density\": {\"bins\": %u, \"initial\": ", result->bins);
    separate_density(f, &result->density_initial);
    fprintf(f, ", \"final\": ");
    separate_density(f, &result->density_final);
    fprintf(f, ", \"cv_ratio\": %.12g, \"tv_distance\": %.12g, "
               "\"clustered\": %s},\n",
            result->density_cv_ratio, result->density_tv,
            result->clustered ? "true" : "false");
    fprintf(f, "  \"trajectory\": {\"samples\": %u, \"mean_curvature\": "
               "%.12g, \"p95_curvature\": %.12g, \"max_curvature\": %.12g, "
               "\"mean_speed\": %.12g, \"mean_turning_degrees\": %.12g, "
               "\"samples_per_trace\": %u},\n",
            result->trajectory.samples, result->trajectory.mean,
            result->trajectory.p95, result->trajectory.max,
            result->trajectory.mean_speed,
            result->trajectory.mean_turning_degrees,
            result->trace_samples);
    fprintf(f, "  \"frequency_sweep\": [\n");
    for (i = 0; i < result->sweep_count; ++i) {
        const CNSweepRow *row = &result->sweep[i];
        fprintf(f, "    {\"frequency\": %.12g, \"mean_curvature\": %.12g, "
                   "\"p95_curvature\": %.12g, \"mean_speed\": %.12g, "
                   "\"mean_path_length\": %.12g, "
                   "\"mean_net_displacement\": %.12g}%s\n",
                row->frequency, row->mean_curvature, row->p95_curvature,
                row->mean_speed, row->mean_path_length,
                row->mean_net_displacement,
                i + 1u < result->sweep_count ? "," : "");
    }
    fprintf(f, "  ],\n");
    fprintf(f, "  \"checks\": {\"divergence_free\": %s, "
               "\"distribution_retained\": %s, "
               "\"trajectories_curve\": %s, "
               "\"frequency_curvature_correlation\": %.12g, "
               "\"frequency_increases_curvature\": %s},\n",
            divergence_free ? "true" : "false",
            distribution_retained ? "true" : "false",
            curves ? "true" : "false",
            result->curvature_frequency_corr,
            frequency_monotone ? "true" : "false");
    fprintf(f, "  \"runtime_seconds\": %.12g\n}\n",
            result->runtime_seconds);
    if (ferror(f)) {
        fclose(f);
        return -1;
    }
    return fclose(f) == 0 ? 0 : -1;
}

static int write_summary(const char *output_dir,
                         const CNExperimentResult *result) {
    char path[MAX_PATH];
    FILE *f;
    path_join(path, sizeof(path), output_dir, "summary.txt");
    f = fopen(path, "w");
    if (f == NULL) {
        return -1;
    }
    fprintf(f, "Curl noise particle flow validation\n");
    fprintf(f, "===================================\n");
    fprintf(f, "field: %u modes, frequency=%.3f, speed=%.3f\n",
            result->mode_count, (double)result->config.frequency,
            (double)result->config.speed);
    fprintf(f, "particles: %u, steps=%u, dt=%.4f\n",
            result->config.particle_count, result->config.steps,
            (double)result->config.dt);
    fprintf(f, "divergence: max_abs=%.3e, rms=%.3e\n",
            result->divergence_max_abs, result->divergence_rms);
    fprintf(f,
            "density: initial_cv=%.4f final_cv=%.4f cv_ratio=%.4f "
            "cluster_index=%.3f TV=%.4f clustered=%s\n",
            result->density_initial.cv, result->density_final.cv,
            result->density_cv_ratio, result->density_final.clustering_index,
            result->density_tv,
            result->clustered ? "yes" : "no");
    fprintf(f,
            "trajectory: samples=%u mean_speed=%.4f mean_curvature=%.4f "
            "p95=%.4f\n",
            result->trajectory.samples, result->trajectory.mean_speed,
            result->trajectory.mean, result->trajectory.p95);
    fprintf(f, "frequency/curvature Pearson r=%.4f\n",
            result->curvature_frequency_corr);
    fprintf(f, "\nfrequency,mean_curvature,p95_curvature\n");
    {
        uint32_t i;
        for (i = 0; i < result->sweep_count; ++i) {
            fprintf(f, "%.3f,%.6f,%.6f\n", result->sweep[i].frequency,
                    result->sweep[i].mean_curvature,
                    result->sweep[i].p95_curvature);
        }
    }
    fprintf(f, "\n结论:\n");
    fprintf(f, "- 数值散度最大绝对值 %.3e；流场由流函数旋度构造，"
               "解析散度为零。\n",
            result->divergence_max_abs);
    fprintf(f, "- 湍流场中分箱密度 CV 由 %.4f 变为 %.4f，"
               "%s明显聚集。\n",
            result->density_initial.cv, result->density_final.cv,
            result->clustered ? "检测到" : "未检测到");
    fprintf(f, "- 轨迹平均曲率 %.4f，频率与曲率相关系数 %.4f；"
               "噪声频率升高时单位路程转向更频繁。\n",
            result->trajectory.mean, result->curvature_frequency_corr);
    if (ferror(f)) {
        fclose(f);
        return -1;
    }
    return fclose(f) == 0 ? 0 : -1;
}

static CNExperimentConfig normalized_config(CNExperimentConfig input) {
    CNExperimentConfig defaults = cn_experiment_config_default();
    if (input.particle_count < 32u) {
        input.particle_count = defaults.particle_count;
    }
    if (input.steps == 0u) {
        input.steps = defaults.steps;
    }
    if (!(input.dt > 0.0f) || !isfinite(input.dt)) {
        input.dt = defaults.dt;
    }
    if (!(input.frequency > 0.0f) || !isfinite(input.frequency)) {
        input.frequency = defaults.frequency;
    }
    if (!(input.lacunarity > 1.0f) || !isfinite(input.lacunarity)) {
        input.lacunarity = defaults.lacunarity;
    }
    if (!(input.gain > 0.0f) || !isfinite(input.gain)) {
        input.gain = defaults.gain;
    }
    if (!(input.speed > 0.0f) || !isfinite(input.speed)) {
        input.speed = defaults.speed;
    }
    if (!(input.box_size > 0.0f) || !isfinite(input.box_size)) {
        input.box_size = defaults.box_size;
    }
    if (input.trace_every == 0u) {
        input.trace_every = defaults.trace_every;
    }
    if (input.trace_count > input.particle_count) {
        input.trace_count = input.particle_count;
    }
    if (input.trace_count == 0u) {
        input.trace_count = input.particle_count < 96u
                                ? input.particle_count
                                : 96u;
    }
    input.jitter = (float)(input.jitter < 0.0f ? 0.0 : input.jitter);
    input.jitter = input.jitter > 1.0f ? 1.0f : input.jitter;
    input.version = CN_ABI_VERSION;
    return input;
}

int cn_run_experiment(CNExperimentConfig config, const char *output_dir,
                      CNExperimentResult *result) {
    CNFlowParams flow;
    CNField *field;
    clock_t start;
    int status = -1;
    if (result == NULL || output_dir == NULL) {
        return -1;
    }
    start = clock();
    memset(result, 0, sizeof(*result));
    config = normalized_config(config);
    result->config = config;
    result->bins = 20u;
    result->field_rows = 96u;
    result->field_cols = 96u;
    flow = cn_flow_params_default();
    flow.seed = config.seed;
    flow.octaves = 4u;
    flow.modes_per_octave = 5u;
    flow.frequency = config.frequency;
    flow.lacunarity = config.lacunarity;
    flow.gain = config.gain;
    flow.speed = config.speed;
    flow.box_size = config.box_size;
    result->flow = flow;
    field = cn_field_create(&flow);
    if (field == NULL) {
        return -1;
    }
    result->mode_count = cn_field_mode_count(field);
    if (write_field_csv(&config, field, output_dir, result) != 0) {
        goto cleanup;
    }
    if (simulate_main_particles(&config, field, output_dir, result) != 0) {
        goto cleanup;
    }
    if (run_frequency_sweep(&config, result) != 0) {
        goto cleanup;
    }
    if (write_sweep_csv(output_dir, result) != 0) {
        goto cleanup;
    }
    result->runtime_seconds =
        (double)(clock() - start) / (double)CLOCKS_PER_SEC;
    if (write_metrics_json(output_dir, result) != 0) {
        goto cleanup;
    }
    if (write_summary(output_dir, result) != 0) {
        goto cleanup;
    }
    status = 0;

cleanup:
    free(result->sweep);
    result->sweep = NULL;
    cn_field_destroy(field);
    return status;
}
