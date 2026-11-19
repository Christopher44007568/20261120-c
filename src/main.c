#include "experiment.h"
#include "curl_noise.h"

#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static void usage(const char *program) {
    fprintf(stderr,
            "Usage: %s [options]\n"
            "  --out DIR             output directory (default: artifacts)\n"
            "  --particles N         particle count (default: 16384)\n"
            "  --steps N             integration steps (default: 720)\n"
            "  --dt SECONDS          RK4 time step (default: 0.005)\n"
            "  --frequency F         base noise cycles per box (default: 2)\n"
            "  --seed N              deterministic seed (default: 20261120)\n"
            "  --trace-count N       exported trajectories (default: 96)\n"
            "  --trace-every N       sample every N steps (default: 3)\n"
            "  --speed V             RMS flow speed (default: 0.65)\n"
            "  --gain G              octave amplitude falloff (default: 0.58)\n"
            "  --lacunarity L        octave frequency ratio (default: 2)\n"
            "  --jitter J            initial quasi-uniform jitter, 0..1 (default: 0.85)\n"
            "  --layout-json PATH    write the C ABI layout and exit\n"
            "  --help                show this help\n",
            program);
}

static int parse_u32(const char *text, uint32_t *out) {
    char *end = NULL;
    unsigned long value;
    errno = 0;
    value = strtoul(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' || value > 0xffffffffUL) {
        return -1;
    }
    *out = (uint32_t)value;
    return 0;
}

static int parse_float(const char *text, float *out) {
    char *end = NULL;
    double value;
    errno = 0;
    value = strtod(text, &end);
    if (errno != 0 || end == text || *end != '\0' || !isfinite(value)) {
        return -1;
    }
    *out = (float)value;
    return 0;
}

static int ensure_output_dir(const char *path) {
    if (mkdir(path, 0777) == 0) {
        return 0;
    }
    return errno == EEXIST ? 0 : -1;
}

int main(int argc, char **argv) {
    CNExperimentConfig config = cn_experiment_config_default();
    CNExperimentResult result;
    const char *output_dir = "artifacts";
    const char *layout_path = NULL;
    int i;

    for (i = 1; i < argc; ++i) {
        const char *arg = argv[i];
        const char *value = i + 1 < argc ? argv[i + 1] : NULL;
        if (strcmp(arg, "--help") == 0) {
            usage(argv[0]);
            return 0;
        }
        if (value == NULL) {
            fprintf(stderr, "missing value after %s\n", arg);
            usage(argv[0]);
            return 2;
        }
        if (strcmp(arg, "--out") == 0) {
            output_dir = value;
        } else if (strcmp(arg, "--layout-json") == 0) {
            layout_path = value;
        } else if (strcmp(arg, "--particles") == 0) {
            if (parse_u32(value, &config.particle_count) != 0) {
                goto bad_value;
            }
        } else if (strcmp(arg, "--steps") == 0) {
            if (parse_u32(value, &config.steps) != 0) {
                goto bad_value;
            }
        } else if (strcmp(arg, "--seed") == 0) {
            if (parse_u32(value, &config.seed) != 0) {
                goto bad_value;
            }
        } else if (strcmp(arg, "--trace-count") == 0) {
            if (parse_u32(value, &config.trace_count) != 0) {
                goto bad_value;
            }
        } else if (strcmp(arg, "--trace-every") == 0) {
            if (parse_u32(value, &config.trace_every) != 0) {
                goto bad_value;
            }
        } else if (strcmp(arg, "--dt") == 0) {
            if (parse_float(value, &config.dt) != 0) {
                goto bad_value;
            }
        } else if (strcmp(arg, "--frequency") == 0) {
            if (parse_float(value, &config.frequency) != 0) {
                goto bad_value;
            }
        } else if (strcmp(arg, "--speed") == 0) {
            if (parse_float(value, &config.speed) != 0) {
                goto bad_value;
            }
        } else if (strcmp(arg, "--gain") == 0) {
            if (parse_float(value, &config.gain) != 0) {
                goto bad_value;
            }
        } else if (strcmp(arg, "--lacunarity") == 0) {
            if (parse_float(value, &config.lacunarity) != 0) {
                goto bad_value;
            }
        } else if (strcmp(arg, "--jitter") == 0) {
            if (parse_float(value, &config.jitter) != 0) {
                goto bad_value;
            }
        } else {
            fprintf(stderr, "unknown option: %s\n", arg);
            usage(argv[0]);
            return 2;
        }
        ++i;
        continue;

bad_value:
        fprintf(stderr, "invalid value for %s: %s\n", arg, value);
        return 2;
    }

    if (layout_path != NULL) {
        if (cn_write_abi_json(layout_path) != 0) {
            fprintf(stderr, "cannot write ABI layout: %s\n", layout_path);
            return 1;
        }
        printf("wrote ABI layout: %s\n", layout_path);
        return 0;
    }
    if (ensure_output_dir(output_dir) != 0) {
        fprintf(stderr, "cannot create output directory: %s\n", output_dir);
        return 1;
    }
    if (cn_run_experiment(config, output_dir, &result) != 0) {
        fprintf(stderr, "experiment failed\n");
        return 1;
    }
    printf("curl-noise modes: %u\n", result.mode_count);
    printf("divergence max|div|: %.3e\n", result.divergence_max_abs);
    printf("density CV: %.4f -> %.4f (ratio %.3f, clustered=%s)\n",
           result.density_initial.cv, result.density_final.cv,
           result.density_cv_ratio, result.clustered ? "yes" : "no");
    printf("mean trajectory curvature: %.4f (frequency r=%.3f)\n",
           result.trajectory.mean, result.curvature_frequency_corr);
    printf("artifacts: %s\n", output_dir);
    return 0;
}
