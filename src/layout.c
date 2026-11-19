#include "curl_noise.h"

#include <float.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

_Static_assert(sizeof(CNVec2) == 8, "CNVec2 ABI changed");
_Static_assert(sizeof(CNFlowParams) == 36, "CNFlowParams ABI changed");
_Static_assert(sizeof(CNExperimentConfig) == 52,
               "CNExperimentConfig ABI changed");
_Static_assert(sizeof(CNParticle) == 28, "CNParticle ABI changed");
_Static_assert(sizeof(CNFieldSample) == 28, "CNFieldSample ABI changed");
_Static_assert(sizeof(CNTrajectorySample) == 36,
               "CNTrajectorySample ABI changed");
_Static_assert(sizeof(CNLayout) == 96, "CNLayout ABI changed");
_Static_assert(_Alignof(CNVec2) == 4, "CNVec2 alignment changed");
_Static_assert(_Alignof(CNFlowParams) == 4, "CNFlowParams alignment changed");
_Static_assert(_Alignof(CNParticle) == 4, "CNParticle alignment changed");
_Static_assert(_Alignof(CNTrajectorySample) == 4,
               "CNTrajectorySample alignment changed");

CNFlowParams cn_flow_params_default(void) {
    CNFlowParams p;
    memset(&p, 0, sizeof(p));
    p.version = CN_ABI_VERSION;
    p.seed = 20261120u;
    p.octaves = 4u;
    p.modes_per_octave = 6u;
    p.frequency = 2.0f;
    p.lacunarity = 2.0f;
    p.gain = 0.58f;
    p.speed = 0.65f;
    p.box_size = 1.0f;
    return p;
}

CNExperimentConfig cn_experiment_config_default(void) {
    CNExperimentConfig c;
    memset(&c, 0, sizeof(c));
    c.version = CN_ABI_VERSION;
    c.seed = 20261120u;
    c.particle_count = 16384u;
    c.steps = 720u;
    c.trace_count = 96u;
    c.trace_every = 3u;
    c.frequency = 2.0f;
    c.lacunarity = 2.0f;
    c.gain = 0.58f;
    c.speed = 0.65f;
    c.dt = 0.005f;
    c.box_size = 1.0f;
    c.jitter = 0.85f;
    return c;
}

static uint32_t offset_u32(const void *base, const void *member) {
    return (uint32_t)((const unsigned char *)member -
                      (const unsigned char *)base);
}

CNLayout cn_abi_layout(void) {
    CNLayout out;
    uint16_t endian_probe = 1u;
    memset(&out, 0, sizeof(out));
    out.version = CN_ABI_VERSION;
    out.pointer_size = (uint32_t)sizeof(void *);
    out.flow_params_size = (uint32_t)sizeof(CNFlowParams);
    out.flow_params_align = (uint32_t)_Alignof(CNFlowParams);
    out.experiment_size = (uint32_t)sizeof(CNExperimentConfig);
    out.experiment_align = (uint32_t)_Alignof(CNExperimentConfig);
    out.particle_size = (uint32_t)sizeof(CNParticle);
    out.particle_align = (uint32_t)_Alignof(CNParticle);
    out.field_sample_size = (uint32_t)sizeof(CNFieldSample);
    out.field_sample_align = (uint32_t)_Alignof(CNFieldSample);
    out.trajectory_sample_size = (uint32_t)sizeof(CNTrajectorySample);
    out.trajectory_sample_align = (uint32_t)_Alignof(CNTrajectorySample);
    out.vec2_size = (uint32_t)sizeof(CNVec2);
    out.vec2_align = (uint32_t)_Alignof(CNVec2);
    out.particle_stride = (uint32_t)sizeof(CNParticle);
    out.field_sample_stride = (uint32_t)sizeof(CNFieldSample);
    out.trajectory_sample_stride = (uint32_t)sizeof(CNTrajectorySample);
    out.array_rank = 1u;
    out.array_order = 1u;
    out.struct_count = 6u;
    out.scalar_bits = (uint32_t)(sizeof(float) * CHAR_BIT);
    out.little_endian = (uint32_t)(*(const unsigned char *)&endian_probe);
    out.ieee754_float =
        (FLT_RADIX == 2 && FLT_MANT_DIG == 24 && FLT_MAX_EXP == 128) ? 1u : 0u;
    return out;
}

static int put_struct(FILE *f, const char *name, size_t size, size_t align) {
    return fprintf(f, "    \"%s\": {\"size\": %zu, \"align\": %zu, \"fields\": {",
                   name, size, align) < 0;
}

int cn_write_abi_json(const char *path) {
    FILE *f;
    CNLayout layout;
    CNVec2 v2;
    CNFlowParams fp;
    CNExperimentConfig ec;
    CNParticle particle;
    CNFieldSample sample;
    CNTrajectorySample trace;

    if (path == NULL) {
        return -1;
    }
    f = fopen(path, "w");
    if (f == NULL) {
        return -1;
    }
    layout = cn_abi_layout();
    memset(&v2, 0, sizeof(v2));
    memset(&fp, 0, sizeof(fp));
    memset(&ec, 0, sizeof(ec));
    memset(&particle, 0, sizeof(particle));
    memset(&sample, 0, sizeof(sample));
    memset(&trace, 0, sizeof(trace));

    fprintf(f, "{\n  \"schema\": \"curl-noise-abi\",\n");
    fprintf(f, "  \"abi_version\": %u,\n", layout.version);
    fprintf(f, "  \"pointer_size\": %u,\n", layout.pointer_size);
    fprintf(f, "  \"scalar_bits\": %u,\n", layout.scalar_bits);
    fprintf(f, "  \"little_endian\": %u,\n", layout.little_endian);
    fprintf(f, "  \"ieee754_float\": %u,\n", layout.ieee754_float);
    fprintf(f, "  \"structs\": {\n");
    put_struct(f, "CNVec2", sizeof(CNVec2), _Alignof(CNVec2));
    fprintf(f, "\"x\": %u, \"y\": %u}},\n",
            offset_u32(&v2, &v2.x), offset_u32(&v2, &v2.y));
    put_struct(f, "CNFlowParams", sizeof(CNFlowParams), _Alignof(CNFlowParams));
    fprintf(f, "\"version\": %u, \"seed\": %u, \"octaves\": %u, "
               "\"modes_per_octave\": %u, \"frequency\": %u, "
               "\"lacunarity\": %u, \"gain\": %u, \"speed\": %u, "
               "\"box_size\": %u}},\n",
            offset_u32(&fp, &fp.version), offset_u32(&fp, &fp.seed),
            offset_u32(&fp, &fp.octaves),
            offset_u32(&fp, &fp.modes_per_octave),
            offset_u32(&fp, &fp.frequency), offset_u32(&fp, &fp.lacunarity),
            offset_u32(&fp, &fp.gain), offset_u32(&fp, &fp.speed),
            offset_u32(&fp, &fp.box_size));
    put_struct(f, "CNExperimentConfig", sizeof(CNExperimentConfig),
               _Alignof(CNExperimentConfig));
    fprintf(f, "\"version\": %u, \"seed\": %u, \"particle_count\": %u, "
               "\"steps\": %u, \"trace_count\": %u, \"trace_every\": %u, "
               "\"frequency\": %u, \"lacunarity\": %u, \"gain\": %u, "
               "\"speed\": %u, \"dt\": %u, \"box_size\": %u, "
               "\"jitter\": %u}},\n",
            offset_u32(&ec, &ec.version), offset_u32(&ec, &ec.seed),
            offset_u32(&ec, &ec.particle_count), offset_u32(&ec, &ec.steps),
            offset_u32(&ec, &ec.trace_count), offset_u32(&ec, &ec.trace_every),
            offset_u32(&ec, &ec.frequency), offset_u32(&ec, &ec.lacunarity),
            offset_u32(&ec, &ec.gain), offset_u32(&ec, &ec.speed),
            offset_u32(&ec, &ec.dt), offset_u32(&ec, &ec.box_size),
            offset_u32(&ec, &ec.jitter));
    put_struct(f, "CNParticle", sizeof(CNParticle), _Alignof(CNParticle));
    fprintf(f, "\"id\": %u, \"flags\": %u, \"x\": %u, \"y\": %u, "
               "\"vx\": %u, \"vy\": %u, \"age\": %u}},\n",
            offset_u32(&particle, &particle.id),
            offset_u32(&particle, &particle.flags),
            offset_u32(&particle, &particle.x),
            offset_u32(&particle, &particle.y),
            offset_u32(&particle, &particle.vx),
            offset_u32(&particle, &particle.vy),
            offset_u32(&particle, &particle.age));
    put_struct(f, "CNFieldSample", sizeof(CNFieldSample),
               _Alignof(CNFieldSample));
    fprintf(f, "\"x\": %u, \"y\": %u, \"vx\": %u, \"vy\": %u, "
               "\"potential\": %u, \"divergence\": %u, \"speed\": %u}},\n",
            offset_u32(&sample, &sample.x), offset_u32(&sample, &sample.y),
            offset_u32(&sample, &sample.vx), offset_u32(&sample, &sample.vy),
            offset_u32(&sample, &sample.potential),
            offset_u32(&sample, &sample.divergence),
            offset_u32(&sample, &sample.speed));
    put_struct(f, "CNTrajectorySample", sizeof(CNTrajectorySample),
               _Alignof(CNTrajectorySample));
    fprintf(f, "\"particle_id\": %u, \"step\": %u, \"time\": %u, "
               "\"x\": %u, \"y\": %u, \"vx\": %u, \"vy\": %u, "
               "\"speed\": %u, \"curvature\": %u}}\n",
            offset_u32(&trace, &trace.particle_id),
            offset_u32(&trace, &trace.step), offset_u32(&trace, &trace.time),
            offset_u32(&trace, &trace.x), offset_u32(&trace, &trace.y),
            offset_u32(&trace, &trace.vx), offset_u32(&trace, &trace.vy),
            offset_u32(&trace, &trace.speed),
            offset_u32(&trace, &trace.curvature));
    fprintf(f, "  },\n  \"arrays\": {\n");
    fprintf(f, "    \"particles\": {\"element\": \"CNParticle\", "
               "\"stride\": %u, \"rank\": 1, \"order\": \"c_contiguous\", "
               "\"index\": \"i\"},\n", layout.particle_stride);
    fprintf(f, "    \"flow_samples\": {\"element\": \"CNFieldSample\", "
               "\"stride\": %u, \"rank\": 2, \"order\": \"c_contiguous\", "
               "\"index\": \"row * cols + col\"},\n",
            layout.field_sample_stride);
    fprintf(f, "    \"trajectory_samples\": "
               "{\"element\": \"CNTrajectorySample\", \"stride\": %u, "
               "\"rank\": 2, \"order\": \"c_contiguous\", "
               "\"index\": \"trace * samples_per_trace + sample\"}\n",
            layout.trajectory_sample_stride);
    fprintf(f, "  }\n}\n");
    if (ferror(f)) {
        fclose(f);
        return -1;
    }
    return fclose(f) == 0 ? 0 : -1;
}
