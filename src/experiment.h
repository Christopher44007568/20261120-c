#ifndef CURL_NOISE_EXPERIMENT_H
#define CURL_NOISE_EXPERIMENT_H

#include "curl_noise.h"

typedef struct {
    uint32_t bins;
    double expected_per_bin;
    double mean;
    double stddev;
    double cv;
    double clustering_index;
    double reduced_chi2;
    double max_cell_ratio;
    double uniformity;
    uint32_t empty_cells;
} CNDensityStats;

typedef struct {
    double mean;
    double p95;
    double max;
    double mean_speed;
    double mean_turning_degrees;
    uint32_t samples;
} CNTrajectoryStats;

typedef struct {
    double frequency;
    double mean_curvature;
    double p95_curvature;
    double mean_speed;
    double mean_path_length;
    double mean_net_displacement;
} CNSweepRow;

typedef struct {
    CNExperimentConfig config;
    CNFlowParams flow;
    uint32_t mode_count;
    uint32_t bins;
    uint32_t field_rows;
    uint32_t field_cols;
    uint32_t trace_samples;
    double divergence_max_abs;
    double divergence_rms;
    CNDensityStats density_initial;
    CNDensityStats density_final;
    double density_cv_ratio;
    double density_tv;
    int clustered;
    CNTrajectoryStats trajectory;
    CNSweepRow *sweep;
    uint32_t sweep_count;
    double curvature_frequency_corr;
    double runtime_seconds;
} CNExperimentResult;

int cn_run_experiment(CNExperimentConfig config, const char *output_dir,
                      CNExperimentResult *result);

#endif
