#ifndef NOISE_H
#define NOISE_H

float noise3(float x, float y, float z);
float fbm3(float x, float y, float z, int octaves, float lacunarity, float gain);
float worley3(float x, float y, float z);

#endif
