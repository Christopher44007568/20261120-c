"""Minimal radix-2 iterative FFT (stdlib only, no numpy)."""

import cmath
import math


def _next_pow2(n):
    p = 1
    while p < n:
        p <<= 1
    return p


def fft(samples, inverse=False):
    n = len(samples)
    if n & (n - 1):
        raise ValueError("fft length must be a power of two")
    out = [complex(v) for v in samples]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            out[i], out[j] = out[j], out[i]
    length = 2
    sign = 1.0 if inverse else -1.0
    while length <= n:
        half = length >> 1
        wlen = cmath.exp(sign * 2j * math.pi / length)
        for start in range(0, n, length):
            w = 1.0 + 0j
            for k in range(half):
                u = out[start + k]
                v = w * out[start + k + half]
                out[start + k] = u + v
                out[start + k + half] = u - v
                w *= wlen
        length <<= 1
    if inverse:
        out = [v / n for v in out]
    return out


def ifft(samples):
    return fft(samples, inverse=True)


def magnitude_spectrum(samples):
    padded = samples + [0.0] * (_next_pow2(len(samples)) - len(samples))
    spectrum = fft(padded)
    half = len(spectrum) // 2
    return [abs(v) ** 2 / len(spectrum) ** 2 for v in spectrum[:half + 1]]
