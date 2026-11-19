#include "noise.h"
#include <math.h>

static float hash3(int x, int y, int z) {
    unsigned h = (unsigned)(x * 374761393 + y * 668265263 + z * 2147483647);
    h = (h ^ (h >> 13)) * 1274126177u;
    h ^= h >> 16;
    return (float)(h & 0xFFFFFF) / (float)0xFFFFFF;
}

static float smooth(float t) { return t * t * (3.0f - 2.0f * t); }

float noise3(float x, float y, float z) {
    int xi = (int)floorf(x), yi = (int)floorf(y), zi = (int)floorf(z);
    float xf = x - xi, yf = y - yi, zf = z - zi;
    float u = smooth(xf), v = smooth(yf), w = smooth(zf);
    float c000 = hash3(xi, yi, zi),     c100 = hash3(xi + 1, yi, zi);
    float c010 = hash3(xi, yi + 1, zi), c110 = hash3(xi + 1, yi + 1, zi);
    float c001 = hash3(xi, yi, zi + 1), c101 = hash3(xi + 1, yi, zi + 1);
    float c011 = hash3(xi, yi + 1, zi + 1), c111 = hash3(xi + 1, yi + 1, zi + 1);
    float x00 = c000 + u * (c100 - c000);
    float x10 = c010 + u * (c110 - c010);
    float x01 = c001 + u * (c101 - c001);
    float x11 = c011 + u * (c111 - c011);
    float y0 = x00 + v * (x10 - x00);
    float y1 = x01 + v * (x11 - x01);
    return y0 + w * (y1 - y0);
}

float fbm3(float x, float y, float z, int octaves, float lacunarity, float gain) {
    float sum = 0.0f, amp = 0.5f, freq = 1.0f, norm = 0.0f;
    for (int i = 0; i < octaves; i++) {
        sum += amp * noise3(x * freq, y * freq, z * freq);
        norm += amp;
        amp *= gain;
        freq *= lacunarity;
    }
    return sum / norm;
}

/* Worley (cellular) noise, F1 distance, used to erode cloud edges. */
float worley3(float x, float y, float z) {
    int xi = (int)floorf(x), yi = (int)floorf(y), zi = (int)floorf(z);
    float best = 1e9f;
    for (int dx = -1; dx <= 1; dx++)
        for (int dy = -1; dy <= 1; dy++)
            for (int dz = -1; dz <= 1; dz++) {
                int cx = xi + dx, cy = yi + dy, cz = zi + dz;
                float px = cx + hash3(cx, cy, cz);
                float py = cy + hash3(cx + 57, cy, cz);
                float pz = cz + hash3(cx, cy, cz + 113);
                float ddx = px - x, ddy = py - y, ddz = pz - z;
                float d = ddx * ddx + ddy * ddy + ddz * ddz;
                if (d < best) best = d;
            }
    return sqrtf(best);
}
