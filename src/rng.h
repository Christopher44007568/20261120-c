#pragma once

#include <cstdint>

class Rng {
public:
    explicit Rng(std::uint64_t seed) : state_(seed ? seed : 0x9e3779b97f4a7c15ULL) {}

    std::uint64_t nextU64() {
        state_ ^= state_ >> 12;
        state_ ^= state_ << 25;
        state_ ^= state_ >> 27;
        return state_ * 0x2545f4914f6cdd1dULL;
    }

    double next() {
        return static_cast<double>(nextU64() >> 11) * (1.0 / 9007199254740992.0);
    }

private:
    std::uint64_t state_;
};

inline std::uint64_t hashSeed(std::uint64_t a, std::uint64_t b, std::uint64_t c = 0) {
    std::uint64_t h = a + 0x9e3779b97f4a7c15ULL;
    h = (h ^ (h >> 30)) * 0xbf58476d1ce4e5b9ULL;
    h ^= b + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
    h = (h ^ (h >> 27)) * 0x94d049bb133111ebULL;
    h ^= c + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
    return h ^ (h >> 31);
}

