/* Early-Z / overdraw simulation.
 *
 * Models a per-pixel depth pipeline over a grid of "pixels" and a list of
 * screen-space quads, and counts fragment shader invocations under two
 * depth models:
 *
 *   EARLY_Z: depth test runs before shading; failing fragments are never
 *            shaded. Requires the quad to allow it: alpha-test (discard)
 *            or shader-written depth force the quad to run as LATE_Z.
 *   LATE_Z:  shading runs before the depth test; every rasterized fragment
 *            is shaded even if it is later killed by the test.
 *
 * Transparent (blended) quads never write depth, so they can be culled by
 * earlier opaque geometry but can never cull anything themselves.
 *
 * Each test case also computes the expected shaded-fragment count
 * analytically and checks the simulator against it.
 */
#include <stdio.h>
#include <string.h>
#include <math.h>

#define W 64
#define H 64
#define NPIX (W * H)

#define QF_BLEND        1  /* transparent: blends, no depth write        */
#define QF_DISCARD      2  /* alpha-test: kills fragments -> forces lateZ */
#define QF_SHADER_DEPTH 4  /* writes depth from shader -> forces lateZ    */

typedef struct {
    int x0, y0, x1, y1;  /* pixel rect [x0,x1) x [y0,y1) */
    float z;             /* constant depth, smaller = closer */
    unsigned flags;
    int discard_mod;     /* if QF_DISCARD: keep 1 of discard_mod fragments */
} Quad;

typedef struct {
    long shaded;         /* fragment shader invocations */
    long rasterized;     /* fragments produced */
    long depth_killed;   /* fragments removed by depth test (pre- or post-shade) */
    long discarded;      /* fragments killed by alpha test */
} Counters;

static int quad_forces_latez(const Quad *q) {
    return (q->flags & (QF_DISCARD | QF_SHADER_DEPTH)) != 0;
}

static void simulate(const Quad *quads, int n, Counters *out,
                     float *overdraw_map) {
    float zbuf[NPIX];
    long shaded_per_pix[NPIX];
    memset(out, 0, sizeof *out);
    for (int i = 0; i < NPIX; i++) { zbuf[i] = 1.0f; shaded_per_pix[i] = 0; }

    for (int qi = 0; qi < n; qi++) {
        const Quad *q = &quads[qi];
        int latez = quad_forces_latez(q);
        for (int y = q->y0; y < q->y1; y++) {
            for (int x = q->x0; x < q->x1; x++) {
                int idx = y * W + x;
                out->rasterized++;
                if (!latez && q->z >= zbuf[idx]) {
                    out->depth_killed++;      /* early-Z: culled pre-shading */
                    continue;
                }
                /* fragment is shaded */
                out->shaded++;
                shaded_per_pix[idx]++;
                if (latez && q->z >= zbuf[idx]) {
                    out->depth_killed++;      /* late-Z: shaded, then killed */
                    continue;
                }
                if ((q->flags & QF_DISCARD) &&
                    (x + y) % q->discard_mod != 0) {
                    out->discarded++;
                    continue;                 /* discard: no depth write */
                }
                if (!(q->flags & QF_BLEND))
                    zbuf[idx] = q->z;         /* blended quads: no depth write */
            }
        }
    }
    if (overdraw_map)
        for (int i = 0; i < NPIX; i++)
            overdraw_map[i] = (float)shaded_per_pix[i];
}

static int check(const char *name, long got, long expect) {
    int ok = got == expect;
    printf("  %-44s shaded=%5ld expect=%5ld  %s\n",
           name, got, expect, ok ? "PASS" : "FAIL");
    return ok;
}

static Quad fullscreen(float z, unsigned flags) {
    Quad q = {0, 0, W, H, z, flags, 2};
    return q;
}

int main(void) {
    int all_ok = 1;
    Counters c;

    printf("== A: 3 fullscreen opaque quads, front-to-back, early-Z ==\n");
    {
        Quad qs[3] = {fullscreen(0.5f, 0), fullscreen(0.6f, 0),
                      fullscreen(0.7f, 0)};
        simulate(qs, 3, &c, NULL);
        /* first quad shades all pixels; the other two are fully culled */
        all_ok &= check("overdraw=1.0 (ideal)", c.shaded, NPIX);
    }

    printf("== B: same quads back-to-front: early-Z cannot help ==\n");
    {
        Quad qs[3] = {fullscreen(0.7f, 0), fullscreen(0.6f, 0),
                      fullscreen(0.5f, 0)};
        simulate(qs, 3, &c, NULL);
        all_ok &= check("overdraw=3.0 (draw order boundary)", c.shaded,
                        3L * NPIX);
    }

    printf("== C: opaque floor + 4 transparent layers ==\n");
    {
        Quad qs[5] = {fullscreen(0.9f, 0),
                      fullscreen(0.5f, QF_BLEND), fullscreen(0.4f, QF_BLEND),
                      fullscreen(0.3f, QF_BLEND), fullscreen(0.2f, QF_BLEND)};
        simulate(qs, 5, &c, NULL);
        /* transparent quads never write depth: nothing culls them,
           early-Z is effectively disabled inside the transparent pass */
        all_ok &= check("overdraw=5.0 (no depth writes)", c.shaded,
                        5L * NPIX);
    }

    printf("== D: transparent quad behind opaque wall ==\n");
    {
        /* wall covers left half at z=0.3, drawn first; transparent
           fullscreen quad at z=0.6 behind it */
        Quad wall = {0, 0, W / 2, H, 0.3f, 0, 2};
        Quad qs[2] = {wall, fullscreen(0.6f, QF_BLEND)};
        simulate(qs, 2, &c, NULL);
        /* wall shades NPIX/2; transparent culled where wall is closer */
        all_ok &= check("early-Z culls behind opaque", c.shaded,
                        NPIX / 2 + NPIX / 2);
    }

    printf("== E: alpha-test quad behind wall (discard forces late-Z) ==\n");
    {
        Quad wall = {0, 0, W / 2, H, 0.3f, 0, 2};
        Quad fence = fullscreen(0.6f, QF_DISCARD);
        Quad qs[2] = {wall, fence};
        simulate(qs, 2, &c, NULL);
        /* fence is shaded on EVERY pixel although half fails the depth
           test: discard disables early-Z, this is the classic boundary */
        all_ok &= check("late-Z shades occluded half too", c.shaded,
                        NPIX / 2 + NPIX);
    }

    printf("== F: shader-depth quad forces late-Z ==\n");
    {
        Quad wall = {0, 0, W / 2, H, 0.3f, 0, 2};
        Quad q = fullscreen(0.6f, QF_SHADER_DEPTH);
        Quad qs[2] = {wall, q};
        simulate(qs, 2, &c, NULL);
        all_ok &= check("SV_Depth disables early-Z", c.shaded,
                        NPIX / 2 + NPIX);
    }

    printf("== G: overdraw heatmap of mixed scene ==\n");
    {
        float map[NPIX];
        Quad ground = fullscreen(0.9f, 0);
        Quad wall = {0, 0, W / 2, H, 0.3f, 0, 2};
        Quad win = {W / 4, H / 4, 3 * W / 4, 3 * H / 4, 0.5f, QF_BLEND, 2};
        Quad part = {W / 8, H / 8, 5 * W / 8, 5 * H / 8, 0.4f, QF_BLEND, 2};
        Quad qs[4] = {ground, wall, win, part};
        simulate(qs, 4, &c, map);
        /* analytic per-pixel expectation:
           ground shades everywhere (drawn first); wall adds 1 on left half;
           window/particle are BEHIND the wall (z=0.5/0.4 vs 0.3), so on the
           left half early-Z culls them; on the right half they add 1 each
           where their rects cover the pixel. */
        long expect = 0;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                long e = 1;                 /* ground */
                if (x < W / 2) e += 1;      /* wall (ground behind it was
                                               already shaded: order cost) */
                if (x >= W / 2 && x < 3 * W / 4 && y >= H / 4 && y < 3 * H / 4)
                    e++;    /* window */
                if (x >= W / 2 && x < 5 * W / 8 && y >= H / 8 && y < 5 * H / 8)
                    e++;    /* particle */
                expect += e;
            }
        all_ok &= check("mixed-scene total matches analytic", c.shaded, expect);
        double od = (double)c.shaded / NPIX;
        printf("  overdraw factor = %.2fx  (shaded=%ld, pixels=%d)\n",
               od, c.shaded, NPIX);
        /* dump a coarse 16x16 overdraw map */
        printf("  overdraw map (shaded fragments per 4x4 block avg):\n");
        for (int by = 0; by < H; by += 4) {
            printf("    ");
            for (int bx = 0; bx < W; bx += 4) {
                float s = 0;
                for (int y = by; y < by + 4; y++)
                    for (int x = bx; x < bx + 4; x++) s += map[y * W + x];
                printf("%3.1f ", s / 16.0f);
            }
            printf("\n");
        }
    }

    printf("\n%s\n", all_ok ? "ALL CHECKS PASS" : "SOME CHECKS FAILED");
    return all_ok ? 0 : 1;
}
