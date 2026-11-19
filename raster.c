#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>

#define W 640
#define H 480
#define FOCAL 420.0
#define CX (W * 0.5)
#define CY (H * 0.5)

/* ---------- geometry ---------- */

typedef struct { double x, y, z; } Vec3;

typedef struct {
    double sx, sy;   /* screen space (pixels, y down) */
    double u, v;     /* texture coords */
    double w;        /* homogeneous w (= view z for pinhole) */
} Vert;

static Vec3 project_back(double sx, double sy) {
    Vec3 d = { (sx - CX) / FOCAL, -(sy - CY) / FOCAL, 1.0 };
    return d;
}

static Vert project(Vec3 p, double u, double v) {
    Vert r;
    r.sx = FOCAL * p.x / p.z + CX;
    r.sy = -FOCAL * p.y / p.z + CY;
    r.u = u; r.v = v; r.w = p.z;
    return r;
}

/* ---------- image ---------- */

static uint8_t g_img[W * H * 3];

static void img_clear(uint8_t r, uint8_t g, uint8_t b) {
    for (int i = 0; i < W * H; i++) {
        g_img[i * 3 + 0] = r; g_img[i * 3 + 1] = g; g_img[i * 3 + 2] = b;
    }
}

static void img_put(int x, int y, uint8_t r, uint8_t g, uint8_t b) {
    if (x < 0 || x >= W || y < 0 || y >= H) return;
    uint8_t *p = g_img + (y * W + x) * 3;
    p[0] = r; p[1] = g; p[2] = b;
}

static int img_save(const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) { perror(path); return -1; }
    fprintf(f, "P6\n%d %d\n255\n", W, H);
    fwrite(g_img, 1, W * H * 3, f);
    fclose(f);
    return 0;
}

/* ---------- checkerboard texture ---------- */

static void checker(double u, double v, uint8_t *r, uint8_t *g, uint8_t *b) {
    int iu = (int)floor(u * 8.0), iv = (int)floor(v * 8.0);
    if (((iu ^ iv) & 1) == 0) { *r = 235; *g = 235; *b = 235; }
    else                      { *r = 40;  *g = 60;  *b = 140; }
}

/* ---------- quad definition (rectangle in 3D) ---------- */

typedef struct {
    Vec3 p00;   /* u=0,v=0 corner */
    Vec3 eu;    /* u edge (u: 0->1) */
    Vec3 ev;    /* v edge (v: 0->1) */
    Vec3 n;     /* plane normal (not normalized) */
} Quad;

static Quad make_quad(Vec3 p00, Vec3 eu, Vec3 ev) {
    Quad q; q.p00 = p00; q.eu = eu; q.ev = ev;
    q.n.x = eu.y * ev.z - eu.z * ev.y;
    q.n.y = eu.z * ev.x - eu.x * ev.z;
    q.n.z = eu.x * ev.y - eu.y * ev.x;
    return q;
}

/* exact u,v,z for a pixel center via ray/plane intersection; 0 if outside */
static int quad_ground_truth(const Quad *q, double sx, double sy,
                             double *out_u, double *out_v, double *out_z) {
    Vec3 d = project_back(sx, sy);
    double dn = d.x * q->n.x + d.y * q->n.y + d.z * q->n.z;
    if (fabs(dn) < 1e-12) return 0;
    double pn = q->p00.x * q->n.x + q->p00.y * q->n.y + q->p00.z * q->n.z;
    double t = pn / dn;
    if (t <= 0.0) return 0;
    Vec3 p = { d.x * t - q->p00.x, d.y * t - q->p00.y, d.z * t - q->p00.z };
    /* solve p = u*eu + v*ev via 2x2 on the dominant plane */
    double a11 = q->eu.x * q->eu.x + q->eu.y * q->eu.y + q->eu.z * q->eu.z;
    double a12 = q->eu.x * q->ev.x + q->eu.y * q->ev.y + q->eu.z * q->ev.z;
    double a22 = q->ev.x * q->ev.x + q->ev.y * q->ev.y + q->ev.z * q->ev.z;
    double b1  = p.x * q->eu.x + p.y * q->eu.y + p.z * q->eu.z;
    double b2  = p.x * q->ev.x + p.y * q->ev.y + p.z * q->ev.z;
    double det = a11 * a22 - a12 * a12;
    double u = (b1 * a22 - b2 * a12) / det;
    double v = (a11 * b2 - a12 * b1) / det;
    if (u < 0.0 || u > 1.0 || v < 0.0 || v > 1.0) return 0;
    *out_u = u; *out_v = v; *out_z = t * d.z;
    return 1;
}

/* ---------- per-pixel output buffers ---------- */

static double  g_out_u[W * H], g_out_v[W * H], g_out_z[W * H];
static uint8_t g_mask[W * H];

static void clear_outputs(void) {
    memset(g_mask, 0, sizeof(g_mask));
}

/* ---------- floating point rasterizer ---------- */

typedef enum { INTERP_LINEAR, INTERP_PERSPECTIVE } InterpMode;

static double edge_f(double x0, double y0, double x1, double y1, double px, double py) {
    return (px - x0) * (y1 - y0) - (py - y0) * (x1 - x0);
}

/* top-left fill rule (works for both winding-normalized triangles) */
static int is_top_left(double dx, double dy) {
    return (dy > 0.0) || (dy == 0.0 && dx < 0.0);
}

/*
 * Rasterize one triangle (float). Attributes written to g_out_*.
 * INTERP_LINEAR: screen-space linear u,v,z.
 * INTERP_PERSPECTIVE: perspective-correct u,v and z (=1/lerp(1/w)).
 */
static void raster_tri_float(const Vert *vin, InterpMode mode) {
    Vert v[3] = { vin[0], vin[1], vin[2] };
    double area = edge_f(v[0].sx, v[0].sy, v[1].sx, v[1].sy, v[2].sx, v[2].sy);
    if (area == 0.0) return;
    if (area < 0.0) { Vert t = v[1]; v[1] = v[2]; v[2] = t; area = -area; }

    double au[3], av[3], az[3];
    for (int i = 0; i < 3; i++) {
        if (mode == INTERP_PERSPECTIVE) {
            au[i] = v[i].u / v[i].w;
            av[i] = v[i].v / v[i].w;
            az[i] = 1.0 / v[i].w;
        } else {
            au[i] = v[i].u;
            av[i] = v[i].v;
            az[i] = v[i].w;
        }
    }

    int x0 = (int)floor(fmin(v[0].sx, fmin(v[1].sx, v[2].sx)));
    int x1 = (int)ceil (fmax(v[0].sx, fmax(v[1].sx, v[2].sx)));
    int y0 = (int)floor(fmin(v[0].sy, fmin(v[1].sy, v[2].sy)));
    int y1 = (int)ceil (fmax(v[0].sy, fmax(v[1].sy, v[2].sy)));
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > W) x1 = W;
    if (y1 > H) y1 = H;

    for (int y = y0; y < y1; y++) {
        for (int x = x0; x < x1; x++) {
            double px = x + 0.5, py = y + 0.5;
            double e0 = edge_f(v[1].sx, v[1].sy, v[2].sx, v[2].sy, px, py);
            double e1 = edge_f(v[2].sx, v[2].sy, v[0].sx, v[0].sy, px, py);
            double e2 = edge_f(v[0].sx, v[0].sy, v[1].sx, v[1].sy, px, py);
            if (e0 < 0 || e1 < 0 || e2 < 0) continue;
            if (e0 == 0.0 && !is_top_left(v[2].sx - v[1].sx, v[2].sy - v[1].sy)) continue;
            if (e1 == 0.0 && !is_top_left(v[0].sx - v[2].sx, v[0].sy - v[2].sy)) continue;
            if (e2 == 0.0 && !is_top_left(v[1].sx - v[0].sx, v[1].sy - v[0].sy)) continue;

            double l0 = e0 / area, l1 = e1 / area, l2 = e2 / area;
            double a_u = l0 * au[0] + l1 * au[1] + l2 * au[2];
            double a_v = l0 * av[0] + l1 * av[1] + l2 * av[2];
            double a_z = l0 * az[0] + l1 * az[1] + l2 * az[2];
            int idx = y * W + x;
            if (mode == INTERP_PERSPECTIVE) {
                double iw = a_z;
                g_out_u[idx] = a_u / iw;
                g_out_v[idx] = a_v / iw;
                g_out_z[idx] = 1.0 / iw;
            } else {
                g_out_u[idx] = a_u;
                g_out_v[idx] = a_v;
                g_out_z[idx] = a_z;
            }
            g_mask[idx] = 1;
        }
    }
}

static void raster_quad_float(const Quad *q, InterpMode mode) {
    Vert c00 = project(q->p00, 0, 0);
    Vec3 p10 = { q->p00.x + q->eu.x, q->p00.y + q->eu.y, q->p00.z + q->eu.z };
    Vec3 p01 = { q->p00.x + q->ev.x, q->p00.y + q->ev.y, q->p00.z + q->ev.z };
    Vec3 p11 = { p10.x + q->ev.x, p10.y + q->ev.y, p10.z + q->ev.z };
    Vert c10 = project(p10, 1, 0);
    Vert c01 = project(p01, 0, 1);
    Vert c11 = project(p11, 1, 1);
    Vert t0[3] = { c00, c10, c11 };
    Vert t1[3] = { c00, c11, c01 };
    raster_tri_float(t0, mode);
    raster_tri_float(t1, mode);
}

/* ---------- error statistics ---------- */

typedef struct {
    long n;
    double max_err, mean_err, rms_err;
    int max_x, max_y;
} ErrStats;

/* compare g_out_* against ground truth of q over covered pixels */
static void err_stats_vs_gt(const Quad *q, int which, ErrStats *st) {
    memset(st, 0, sizeof(*st));
    double sum = 0.0, sum2 = 0.0;
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            int idx = y * W + x;
            if (!g_mask[idx]) continue;
            double gu, gv, gz;
            if (!quad_ground_truth(q, x + 0.5, y + 0.5, &gu, &gv, &gz)) continue;
            double got = (which == 0) ? g_out_u[idx] : (which == 1) ? g_out_v[idx] : g_out_z[idx];
            double ref = (which == 0) ? gu : (which == 1) ? gv : gz;
            double e = fabs(got - ref);
            sum += e; sum2 += e * e; st->n++;
            if (e > st->max_err) { st->max_err = e; st->max_x = x; st->max_y = y; }
        }
    }
    if (st->n) {
        st->mean_err = sum / st->n;
        st->rms_err = sqrt(sum2 / st->n);
    }
}

static void print_stats(const char *name, const ErrStats *st) {
    printf("  %-14s n=%-7ld max=%.6e @(%d,%d)  mean=%.6e  rms=%.6e\n",
           name, st->n, st->max_err, st->max_x, st->max_y, st->mean_err, st->rms_err);
}

/* render current g_out_* as textured image */
static void render_texture_image(void) {
    img_clear(18, 18, 22);
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int idx = y * W + x;
            if (!g_mask[idx]) continue;
            uint8_t r, g, b;
            checker(g_out_u[idx], g_out_v[idx], &r, &g, &b);
            img_put(x, y, r, g, b);
        }
}

/* render depth as grayscale (near = bright) */
static void render_depth_image(double zmin, double zmax) {
    img_clear(0, 0, 0);
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int idx = y * W + x;
            if (!g_mask[idx]) continue;
            double t = (g_out_z[idx] - zmin) / (zmax - zmin);
            if (t < 0) t = 0;
            if (t > 1) t = 1;
            uint8_t c = (uint8_t)((1.0 - t) * 255.0);
            img_put(x, y, c, c, c);
        }
}

/* heatmap of |error| vs ground truth for u (log scale, red) */
static void render_err_heatmap(const Quad *q, int which, double scale) {
    img_clear(0, 0, 0);
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int idx = y * W + x;
            if (!g_mask[idx]) continue;
            double gu, gv, gz;
            if (!quad_ground_truth(q, x + 0.5, y + 0.5, &gu, &gv, &gz)) continue;
            double got = (which == 0) ? g_out_u[idx] : (which == 1) ? g_out_v[idx] : g_out_z[idx];
            double ref = (which == 0) ? gu : (which == 1) ? gv : gz;
            double e = fabs(got - ref) * scale;
            if (e > 1.0) e = 1.0;
            img_put(x, y, (uint8_t)(e * 255), 0, (uint8_t)((1.0 - e) * 80));
        }
}

/* ---------- scenes ---------- */

/* ---------- fixed-point rasterizer (28.4 coords, 16.16 attributes) ---------- */

#define SUB_BITS 4
#define SUB_ONE  (1 << SUB_BITS)          /* subpixel grid: 1/16 pixel */
#define ATTR_BITS 24
#define ATTR_ONE (1LL << ATTR_BITS)       /* 8.24 fixed attributes */

static double  g_fx_u[W * H], g_fx_v[W * H], g_fx_z[W * H];
static uint8_t g_fx_mask[W * H];

typedef struct {
    int64_t sx, sy;     /* 28.4 fixed screen coords */
    int64_t au, av, iw; /* 16.16 fixed: u/w, v/w, 1/w */
} FxVert;

static int64_t fx_edge(int64_t x0, int64_t y0, int64_t x1, int64_t y1,
                       int64_t px, int64_t py) {
    return (px - x0) * (y1 - y0) - (py - y0) * (x1 - x0);
}

static int fx_top_left(int64_t dx, int64_t dy) {
    return (dy > 0) || (dy == 0 && dx < 0);
}

/* rounding division for signed numerator, positive denominator */
static int64_t fx_div_round(__int128 num, int64_t den) {
    if (num >= 0) return (int64_t)((num + den / 2) / den);
    return (int64_t)(-((-num + den / 2) / den));
}

static void raster_tri_fixed(const Vert *vin) {
    FxVert v[3];
    for (int i = 0; i < 3; i++) {
        v[i].sx = llround(vin[i].sx * SUB_ONE);
        v[i].sy = llround(vin[i].sy * SUB_ONE);
        v[i].au = llround(vin[i].u / vin[i].w * ATTR_ONE);
        v[i].av = llround(vin[i].v / vin[i].w * ATTR_ONE);
        v[i].iw = llround(1.0 / vin[i].w * ATTR_ONE);
    }
    int64_t area = fx_edge(v[0].sx, v[0].sy, v[1].sx, v[1].sy, v[2].sx, v[2].sy);
    if (area == 0) return;
    if (area < 0) { FxVert t = v[1]; v[1] = v[2]; v[2] = t; area = -area; }

    int64_t mx0 = v[0].sx, mx1 = v[0].sx, my0 = v[0].sy, my1 = v[0].sy;
    for (int i = 1; i < 3; i++) {
        if (v[i].sx < mx0) mx0 = v[i].sx;
        if (v[i].sx > mx1) mx1 = v[i].sx;
        if (v[i].sy < my0) my0 = v[i].sy;
        if (v[i].sy > my1) my1 = v[i].sy;
    }
    int x0 = (int)(mx0 >> SUB_BITS), x1 = (int)((mx1 + SUB_ONE - 1) >> SUB_BITS);
    int y0 = (int)(my0 >> SUB_BITS), y1 = (int)((my1 + SUB_ONE - 1) >> SUB_BITS);
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > W) x1 = W;
    if (y1 > H) y1 = H;

    for (int y = y0; y < y1; y++) {
        for (int x = x0; x < x1; x++) {
            int64_t px = ((int64_t)x << SUB_BITS) + SUB_ONE / 2;
            int64_t py = ((int64_t)y << SUB_BITS) + SUB_ONE / 2;
            int64_t e0 = fx_edge(v[1].sx, v[1].sy, v[2].sx, v[2].sy, px, py);
            int64_t e1 = fx_edge(v[2].sx, v[2].sy, v[0].sx, v[0].sy, px, py);
            int64_t e2 = fx_edge(v[0].sx, v[0].sy, v[1].sx, v[1].sy, px, py);
            if (e0 < 0 || e1 < 0 || e2 < 0) continue;
            if (e0 == 0 && !fx_top_left(v[2].sx - v[1].sx, v[2].sy - v[1].sy)) continue;
            if (e1 == 0 && !fx_top_left(v[0].sx - v[2].sx, v[0].sy - v[2].sy)) continue;
            if (e2 == 0 && !fx_top_left(v[1].sx - v[0].sx, v[1].sy - v[0].sy)) continue;

            __int128 nu = (__int128)v[0].au * e0 + (__int128)v[1].au * e1 + (__int128)v[2].au * e2;
            __int128 nv = (__int128)v[0].av * e0 + (__int128)v[1].av * e1 + (__int128)v[2].av * e2;
            __int128 nw = (__int128)v[0].iw * e0 + (__int128)v[1].iw * e1 + (__int128)v[2].iw * e2;
            int64_t au = fx_div_round(nu, area);   /* 16.16 */
            int64_t av = fx_div_round(nv, area);
            int64_t iw = fx_div_round(nw, area);
            if (iw <= 0) continue;
            /* u = (u/w)/(1/w), z = 1/(1/w), both in 16.16 with rounding */
            int64_t fu = (au * ATTR_ONE + iw / 2) / iw;
            int64_t fv = (av * ATTR_ONE + iw / 2) / iw;
            int64_t fz = (ATTR_ONE * ATTR_ONE + iw / 2) / iw;
            int idx = y * W + x;
            g_fx_u[idx] = (double)fu / ATTR_ONE;
            g_fx_v[idx] = (double)fv / ATTR_ONE;
            g_fx_z[idx] = (double)fz / ATTR_ONE;
            g_fx_mask[idx] = 1;
        }
    }
}

static void raster_quad_fixed(const Quad *q) {
    Vert c00 = project(q->p00, 0, 0);
    Vec3 p10 = { q->p00.x + q->eu.x, q->p00.y + q->eu.y, q->p00.z + q->eu.z };
    Vec3 p01 = { q->p00.x + q->ev.x, q->p00.y + q->ev.y, q->p00.z + q->ev.z };
    Vec3 p11 = { p10.x + q->ev.x, p10.y + q->ev.y, p10.z + q->ev.z };
    Vert c10 = project(p10, 1, 0);
    Vert c01 = project(p01, 0, 1);
    Vert c11 = project(p11, 1, 1);
    Vert t0[3] = { c00, c10, c11 };
    Vert t1[3] = { c00, c11, c01 };
    memset(g_fx_mask, 0, sizeof(g_fx_mask));
    raster_tri_fixed(t0);
    raster_tri_fixed(t1);
}

/* ---------- fixed vs float comparison ---------- */

/* attribute error of fixed vs float-perspective over commonly covered pixels */
static void cmp_fixed_float(const char *tag) {
    long both = 0, f_only = 0, x_only = 0;
    double mu = 0, mv = 0, mz = 0, mrz = 0, su = 0, sv = 0, sz = 0;
    int mu_x = -1, mu_y = -1, mz_x = -1, mz_y = -1;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int idx = y * W + x;
            int fm = g_mask[idx], xm = g_fx_mask[idx];
            if (fm && !xm) f_only++;
            if (xm && !fm) x_only++;
            if (!fm || !xm) continue;
            both++;
            double du = fabs(g_fx_u[idx] - g_out_u[idx]);
            double dv = fabs(g_fx_v[idx] - g_out_v[idx]);
            double dz = fabs(g_fx_z[idx] - g_out_z[idx]);
            su += du; sv += dv; sz += dz;
            if (du > mu) { mu = du; mu_x = x; mu_y = y; }
            if (dv > mv) mv = dv;
            if (dz > mz) { mz = dz; mz_x = x; mz_y = y; }
            double rz = dz / g_out_z[idx];
            if (rz > mrz) mrz = rz;
        }
    printf("[%s] coverage: both=%ld float-only=%ld fixed-only=%ld (xor=%ld)\n",
           tag, both, f_only, x_only, f_only + x_only);
    printf("[%s] attr err:  u max=%.3e @(%d,%d) mean=%.3e\n", tag, mu, mu_x, mu_y,
           both ? su / both : 0.0);
    printf("[%s]            v max=%.3e mean=%.3e\n", tag, mv, both ? sv / both : 0.0);
    printf("[%s]            z max=%.3e @(%d,%d) mean=%.3e  max-rel=%.3e\n",
           tag, mz, mz_x, mz_y, both ? sz / both : 0.0, mrz);
}

/*
 * Gap check: an interior pixel (pixel center inside the quad by ground truth,
 * with all 8 neighbors also inside, i.e. >=1px away from the outer boundary)
 * must be covered by the fixed-point rasterizer. Vertex snapping to the 1/16px
 * grid can only shift coverage by <1px at the outer boundary, never inside.
 */
static long gap_check(const Quad *q, const uint8_t *mask, const char *tag) {
    static uint8_t inside[W * H];
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            double u, v, z;
            inside[y * W + x] = quad_ground_truth(q, x + 0.5, y + 0.5, &u, &v, &z) ? 1 : 0;
        }
    long gaps = 0;
    int first_x = -1, first_y = -1;
    for (int y = 1; y < H - 1; y++)
        for (int x = 1; x < W - 1; x++) {
            int idx = y * W + x;
            if (!inside[idx] || mask[idx]) continue;
            int interior = 1;
            for (int dy = -1; dy <= 1 && interior; dy++)
                for (int dx = -1; dx <= 1; dx++)
                    if (!inside[(y + dy) * W + (x + dx)]) { interior = 0; break; }
            if (interior) {
                if (gaps == 0) { first_x = x; first_y = y; }
                gaps++;
            }
        }
    printf("[%s] interior gaps (uncovered pixels >=1px inside quad): %ld",
           tag, gaps);
    if (gaps) printf("  first @(%d,%d)", first_x, first_y);
    printf("\n");
    return gaps;
}

/* visualize coverage difference: red=float only, green=fixed only, white=both */
static void render_coverage_diff(void) {
    img_clear(0, 0, 0);
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int idx = y * W + x;
            if (g_mask[idx] && g_fx_mask[idx]) img_put(x, y, 60, 60, 60);
            else if (g_mask[idx])              img_put(x, y, 255, 0, 0);
            else if (g_fx_mask[idx])           img_put(x, y, 0, 255, 0);
        }
}

static void render_fixed_texture(void) {
    img_clear(18, 18, 22);
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int idx = y * W + x;
            if (!g_fx_mask[idx]) continue;
            uint8_t r, g, b;
            checker(g_fx_u[idx], g_fx_v[idx], &r, &g, &b);
            img_put(x, y, r, g, b);
        }
}

/* big perspective-distorted floor rectangle */
static Quad scene_floor(void) {
    return make_quad((Vec3){ -4.0, -1.0, 2.0 },
                     (Vec3){  8.0,  0.0, 0.0 },
                     (Vec3){  0.0,  0.0, 18.0 });
}

/* extreme perspective: near plane at z=1.05, far edge at z=60 (w ratio ~57x) */
static Quad scene_extreme(void) {
    return make_quad((Vec3){ -2.0, -1.0,  1.05 },
                     (Vec3){  4.0,  0.0,  0.0  },
                     (Vec3){  0.0,  0.0, 58.95 });
}

/* fixed-point results vs analytic ground truth */
static void err_stats_fx_vs_gt(const Quad *q, int which, ErrStats *st) {
    memset(st, 0, sizeof(*st));
    double sum = 0.0, sum2 = 0.0;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int idx = y * W + x;
            if (!g_fx_mask[idx]) continue;
            double gu, gv, gz;
            if (!quad_ground_truth(q, x + 0.5, y + 0.5, &gu, &gv, &gz)) continue;
            double got = (which == 0) ? g_fx_u[idx] : (which == 1) ? g_fx_v[idx] : g_fx_z[idx];
            double ref = (which == 0) ? gu : (which == 1) ? gv : gz;
            double e = fabs(got - ref);
            sum += e; sum2 += e * e; st->n++;
            if (e > st->max_err) { st->max_err = e; st->max_x = x; st->max_y = y; }
        }
    if (st->n) {
        st->mean_err = sum / st->n;
        st->rms_err = sqrt(sum2 / st->n);
    }
}

int main(void) {
    ErrStats su, sv, sz;
    Quad floor_q = scene_floor();

    printf("=== 1. Linear vs perspective-correct interpolation (float) ===\n");

    clear_outputs();
    raster_quad_float(&floor_q, INTERP_LINEAR);
    render_texture_image();            img_save("artifacts/tex_linear.ppm");
    render_depth_image(2.0, 20.0);     img_save("artifacts/depth_linear.ppm");
    printf("[linear interpolation]\n");
    err_stats_vs_gt(&floor_q, 0, &su); print_stats("u error", &su);
    err_stats_vs_gt(&floor_q, 1, &sv); print_stats("v error", &sv);
    err_stats_vs_gt(&floor_q, 2, &sz); print_stats("z error", &sz);
    render_err_heatmap(&floor_q, 1, 40.0); img_save("artifacts/err_linear_v.ppm");

    clear_outputs();
    raster_quad_float(&floor_q, INTERP_PERSPECTIVE);
    render_texture_image();            img_save("artifacts/tex_persp.ppm");
    render_depth_image(2.0, 20.0);     img_save("artifacts/depth_persp.ppm");
    printf("[perspective-correct interpolation]\n");
    err_stats_vs_gt(&floor_q, 0, &su); print_stats("u error", &su);
    err_stats_vs_gt(&floor_q, 1, &sv); print_stats("v error", &sv);
    err_stats_vs_gt(&floor_q, 2, &sz); print_stats("z error", &sz);
    render_err_heatmap(&floor_q, 1, 40.0); img_save("artifacts/err_persp_v.ppm");

    printf("\n=== 2. Fixed-point (28.4 coords, 8.24 attrs) vs float ===\n");
    raster_quad_fixed(&floor_q);
    render_fixed_texture();       img_save("artifacts/tex_fixed.ppm");
    render_coverage_diff();       img_save("artifacts/coverage_diff.ppm");
    cmp_fixed_float("floor");
    gap_check(&floor_q, g_mask,    "float/floor");
    gap_check(&floor_q, g_fx_mask, "fixed/floor");
    printf("[fixed-point vs ground truth]\n");
    err_stats_fx_vs_gt(&floor_q, 0, &su); print_stats("u error", &su);
    err_stats_fx_vs_gt(&floor_q, 1, &sv); print_stats("v error", &sv);
    err_stats_fx_vs_gt(&floor_q, 2, &sz); print_stats("z error", &sz);

    printf("\n=== 3. Extreme perspective rectangle (z: 1.05 -> 60) ===\n");
    Quad ext_q = scene_extreme();
    clear_outputs();
    raster_quad_float(&ext_q, INTERP_PERSPECTIVE);
    raster_quad_fixed(&ext_q);
    render_texture_image();       img_save("artifacts/tex_extreme_float.ppm");
    render_fixed_texture();       img_save("artifacts/tex_extreme_fixed.ppm");
    render_coverage_diff();       img_save("artifacts/coverage_extreme.ppm");
    cmp_fixed_float("extreme");
    gap_check(&ext_q, g_fx_mask, "fixed/extreme");
    printf("[float vs ground truth, extreme]\n");
    err_stats_vs_gt(&ext_q, 2, &sz); print_stats("z error", &sz);
    printf("[fixed vs ground truth, extreme]\n");
    err_stats_fx_vs_gt(&ext_q, 2, &sz); print_stats("z error", &sz);

    return 0;
}
