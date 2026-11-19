#include "pngw.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned crc_table[256];
static int crc_ready = 0;

static void crc_init(void) {
    for (unsigned n = 0; n < 256; n++) {
        unsigned c = n;
        for (int k = 0; k < 8; k++)
            c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : (c >> 1);
        crc_table[n] = c;
    }
    crc_ready = 1;
}

static unsigned crc32_of(const unsigned char *buf, size_t len) {
    if (!crc_ready) crc_init();
    unsigned c = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++)
        c = crc_table[(c ^ buf[i]) & 0xFF] ^ (c >> 8);
    return c ^ 0xFFFFFFFFu;
}

static unsigned adler32_of(const unsigned char *buf, size_t len) {
    unsigned a = 1, b = 0;
    for (size_t i = 0; i < len; i++) {
        a = (a + buf[i]) % 65521u;
        b = (b + a) % 65521u;
    }
    return (b << 16) | a;
}

static void put_u32(FILE *f, unsigned v) {
    unsigned char b[4] = {(unsigned char)(v >> 24), (unsigned char)(v >> 16),
                          (unsigned char)(v >> 8), (unsigned char)v};
    fwrite(b, 1, 4, f);
}

static void write_chunk(FILE *f, const char *type,
                        const unsigned char *data, size_t len) {
    put_u32(f, (unsigned)len);
    fwrite(type, 1, 4, f);
    if (len) fwrite(data, 1, len, f);
    unsigned char *tmp = malloc(len + 4);
    memcpy(tmp, type, 4);
    if (len) memcpy(tmp + 4, data, len);
    put_u32(f, crc32_of(tmp, len + 4));
    free(tmp);
}

int png_write(const char *path, const unsigned char *pixels,
              int width, int height, int channels) {
    int color_type = (channels == 3) ? 2 : 0;
    if (channels != 3 && channels != 1) return -1;

    size_t stride = (size_t)width * channels;
    size_t raw_len = (stride + 1) * (size_t)height;
    unsigned char *raw = malloc(raw_len);
    for (int y = 0; y < height; y++) {
        raw[y * (stride + 1)] = 0; /* filter: none */
        memcpy(raw + y * (stride + 1) + 1, pixels + y * stride, stride);
    }

    /* zlib stream: 2-byte header + stored deflate blocks + adler32 */
    size_t nblocks = (raw_len + 65534) / 65535;
    size_t zlen = 2 + nblocks * 5 + raw_len + 4;
    unsigned char *z = malloc(zlen);
    size_t p = 0, off = 0;
    z[p++] = 0x78; z[p++] = 0x01;
    while (off < raw_len) {
        size_t n = raw_len - off;
        if (n > 65535) n = 65535;
        int last = (off + n == raw_len);
        z[p++] = (unsigned char)(last ? 1 : 0);
        z[p++] = (unsigned char)(n & 0xFF);
        z[p++] = (unsigned char)((n >> 8) & 0xFF);
        z[p++] = (unsigned char)(~n & 0xFF);
        z[p++] = (unsigned char)((~n >> 8) & 0xFF);
        memcpy(z + p, raw + off, n);
        p += n; off += n;
    }
    unsigned ad = adler32_of(raw, raw_len);
    z[p++] = (unsigned char)(ad >> 24);
    z[p++] = (unsigned char)(ad >> 16);
    z[p++] = (unsigned char)(ad >> 8);
    z[p++] = (unsigned char)ad;
    free(raw);

    FILE *f = fopen(path, "wb");
    if (!f) { free(z); return -1; }
    static const unsigned char sig[8] = {137, 80, 78, 71, 13, 10, 26, 10};
    fwrite(sig, 1, 8, f);
    unsigned char ihdr[13];
    ihdr[0] = (unsigned char)(width >> 24); ihdr[1] = (unsigned char)(width >> 16);
    ihdr[2] = (unsigned char)(width >> 8);  ihdr[3] = (unsigned char)width;
    ihdr[4] = (unsigned char)(height >> 24); ihdr[5] = (unsigned char)(height >> 16);
    ihdr[6] = (unsigned char)(height >> 8);  ihdr[7] = (unsigned char)height;
    ihdr[8] = 8;                 /* bit depth */
    ihdr[9] = (unsigned char)color_type;
    ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
    write_chunk(f, "IHDR", ihdr, 13);
    write_chunk(f, "IDAT", z, p);
    write_chunk(f, "IEND", NULL, 0);
    fclose(f);
    free(z);
    return 0;
}
