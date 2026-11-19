#ifndef PNGW_H
#define PNGW_H

/* Minimal PNG writer (8-bit RGB/gray, uncompressed deflate blocks). */
int png_write(const char *path, const unsigned char *pixels,
              int width, int height, int channels);

#endif
