#include <algorithm>
#include <barrier>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <numeric>
#include <sched.h>
#include <string>
#include <thread>
#include <vector>

struct Vec3 {
    float x, y, z;
    Vec3 operator+(const Vec3& o) const { return {x + o.x, y + o.y, z + o.z}; }
    Vec3 operator-(const Vec3& o) const { return {x - o.x, y - o.y, z - o.z}; }
    Vec3 operator*(float s) const { return {x * s, y * s, z * s}; }
};

static inline float dot(const Vec3& a, const Vec3& b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

static inline Vec3 cross(const Vec3& a, const Vec3& b) {
    return {a.y * b.z - a.z * b.y,
            a.z * b.x - a.x * b.z,
            a.x * b.y - a.y * b.x};
}

static inline Vec3 normalize(const Vec3& v) {
    float len = std::sqrt(dot(v, v));
    return {v.x / len, v.y / len, v.z / len};
}

struct AABB {
    Vec3 center;
    Vec3 half;
};

// Plane: normal . p + d = 0, normal points into the visible half-space.
struct Plane {
    Vec3 normal;
    float d;
};

struct Frustum {
    Plane planes[6]; // near, far, left, right, bottom, top
};

// Deterministic xorshift64* RNG so every run culls the exact same scene.
struct Rng {
    uint64_t state;
    explicit Rng(uint64_t seed) : state(seed ? seed : 0x9e3779b97f4a7c15ULL) {}
    uint64_t next() {
        uint64_t x = state;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        state = x;
        return x * 0x2545f4914f6cdd1dULL;
    }
    float uniform(float lo, float hi) {
        const uint32_t bits = static_cast<uint32_t>(next() >> 32);
        const float u = (bits >> 8) * (1.0f / 8388608.0f); // [0,1)
        return lo + u * (hi - lo);
    }
};

// Build a symmetric perspective frustum directly in world space.
static Frustum makeFrustum(const Vec3& eye, const Vec3& target, const Vec3& up,
                           float fovYRad, float aspect, float zNear, float zFar) {
    const Vec3 f = normalize(target - eye);
    const Vec3 r = normalize(cross(f, up));
    const Vec3 u = cross(r, f);
    const float nearH = std::tan(fovYRad * 0.5f) * zNear;
    const float nearW = nearH * aspect;
    const float farH = std::tan(fovYRad * 0.5f) * zFar;
    const float farW = farH * aspect;
    const Vec3 nearCenter = eye + f * zNear;
    const Vec3 farCenter = eye + f * zFar;

    // Eight frustum corners, ordered n/f then tl,tr,br,bl.
    const Vec3 ntl = nearCenter + u * nearH - r * nearW;
    const Vec3 ntr = nearCenter + u * nearH + r * nearW;
    const Vec3 nbr = nearCenter - u * nearH + r * nearW;
    const Vec3 nbl = nearCenter - u * nearH - r * nearW;
    const Vec3 ftl = farCenter + u * farH - r * farW;
    const Vec3 ftr = farCenter + u * farH + r * farW;
    const Vec3 fbr = farCenter - u * farH + r * farW;
    const Vec3 fbl = farCenter - u * farH - r * farW;

    auto plane = [&](const Vec3& a, const Vec3& b, const Vec3& c) {
        // Winding is chosen so the normal points into the frustum.
        const Vec3 n = normalize(cross(b - a, c - a));
        return Plane{n, -dot(n, a)};
    };
    Frustum fr{};
    fr.planes[0] = plane(ntr, nbl, ntl); // near, normal == -f (toward eye)
    fr.planes[1] = plane(ftl, fbr, ftr); // far,  normal == +f
    fr.planes[2] = plane(ntl, fbl, ftl); // left
    fr.planes[3] = plane(ftr, nbr, ntr); // right
    fr.planes[4] = plane(fbl, nbr, fbr); // bottom
    fr.planes[5] = plane(ntr, ftl, ftr); // top
    return fr;
}

static inline bool insidePlane(const Plane& p, const Vec3& v) {
    return dot(p.normal, v) + p.d >= 0.0f;
}

// Classic p-vertex / n-vertex AABB-vs-plane test, all six planes.
static bool visibleAabb(const Frustum& fr, const AABB& box) {
    for (const Plane& p : fr.planes) {
        const Vec3 pv = {
            p.normal.x >= 0.0f ? box.center.x + box.half.x : box.center.x - box.half.x,
            p.normal.y >= 0.0f ? box.center.y + box.half.y : box.center.y - box.half.y,
            p.normal.z >= 0.0f ? box.center.z + box.half.z : box.center.z - box.half.z,
        };
        if (!insidePlane(p, pv)) return false;
    }
    return true;
}

// Reference test: box is visible if at least one of its 8 corners is inside.
static bool visibleAabbReference(const Frustum& fr, const AABB& box) {
    const float sx[2] = {-1.0f, 1.0f};
    const float sy[2] = {-1.0f, 1.0f};
    const float sz[2] = {-1.0f, 1.0f};
    for (float ix : sx)
        for (float iy : sy)
            for (float iz : sz) {
                const Vec3 corner = {box.center.x + ix * box.half.x,
                                     box.center.y + iy * box.half.y,
                                     box.center.z + iz * box.half.z};
                bool ok = true;
                for (const Plane& p : fr.planes) {
                    if (!insidePlane(p, corner)) { ok = false; break; }
                }
                if (ok) return true;
            }
    return false;
}

static std::vector<AABB> makeScene(size_t count) {
    std::vector<AABB> boxes(count);
    Rng rng(0x12345678abcdef01ULL);
    for (size_t i = 0; i < count; ++i) {
        // Instances spread over a 4000-unit cube around the origin.
        boxes[i].center = {rng.uniform(-2000.0f, 2000.0f),
                           rng.uniform(-2000.0f, 2000.0f),
                           rng.uniform(-2000.0f, 2000.0f)};
        boxes[i].half = {rng.uniform(1.5f, 6.0f),
                         rng.uniform(1.5f, 6.0f),
                         rng.uniform(1.5f, 6.0f)};
    }
    return boxes;
}

struct Chunk {
    size_t begin;
    size_t end;
};

static std::vector<Chunk> splitChunks(size_t total, int threads) {
    std::vector<Chunk> chunks(static_cast<size_t>(threads));
    const size_t base = total / threads;
    const size_t extra = total % threads;
    size_t cursor = 0;
    for (int t = 0; t < threads; ++t) {
        const size_t len = base + (static_cast<size_t>(t) < extra ? 1 : 0);
        chunks[t] = {cursor, cursor + len};
        cursor += len;
    }
    return chunks;
}

// Persistent worker pool: threads are created once and reused across timed
// rounds, so per-round cost is only the cull work plus two barrier waits.
// Each worker keeps its own visible-id buffer, which is cleared (not freed)
// between rounds; results are concatenated with no lock on the hot loop.
class CullPool {
public:
    CullPool(int workers, const std::vector<AABB>& boxes, const Frustum& fr)
        : boxes_(boxes), fr_(fr), locals_(static_cast<size_t>(workers)),
          go_(static_cast<unsigned>(workers + 1)),
          done_(static_cast<unsigned>(workers + 1)) {
        threads_.reserve(workers);
        for (int t = 0; t < workers; ++t) {
            locals_[t].reserve(boxes.size() / workers / 3 + 16);
            threads_.emplace_back([this, t] { workerLoop(t); });
        }
    }

    ~CullPool() {
        {
            std::lock_guard<std::mutex> lk(mtx_);
            shutdown_ = true;
        }
        go_.arrive_and_wait();
        for (auto& th : threads_) th.join();
    }

    std::vector<std::vector<uint32_t>>
    run(const std::vector<Chunk>& chunks, std::vector<std::vector<uint32_t>> recycled) {
        chunks_ = &chunks;
        if (recycled.size() == locals_.size()) locals_ = std::move(recycled);
        go_.arrive_and_wait();   // release workers
        done_.arrive_and_wait(); // wait for every worker to finish
        std::vector<std::vector<uint32_t>> out(locals_.size());
        for (size_t i = 0; i < locals_.size(); ++i)
            out[i] = std::move(locals_[i]); // hand buffers out; capacity stays in `out`
        return out;
    }

private:
    void workerLoop(int id) {
        cpu_set_t set;
        CPU_ZERO(&set);
        CPU_SET(id, &set);
        sched_setaffinity(0, sizeof(set), &set); // best-effort pinning; ignore failure
        for (;;) {
            go_.arrive_and_wait();
            if (shutdown_) return;
            const Chunk c = (*chunks_)[static_cast<size_t>(id)];
            auto& local = locals_[id];
            local.clear(); // empty shells returned by mergeVisible are reused here
            for (size_t i = c.begin; i < c.end; ++i) {
                if (visibleAabb(fr_, boxes_[i]))
                    local.push_back(static_cast<uint32_t>(i));
            }
            done_.arrive_and_wait();
        }
    }

    const std::vector<AABB>& boxes_;
    const Frustum& fr_;
    std::vector<std::vector<uint32_t>> locals_;
    std::vector<std::thread> threads_;
    const std::vector<Chunk>* chunks_ = nullptr;
    std::barrier<> go_;
    std::barrier<> done_;
    std::mutex mtx_;
    bool shutdown_ = false;
};

static std::vector<uint32_t> mergeVisible(std::vector<std::vector<uint32_t>>&& locals) {
    size_t total = 0;
    for (auto& v : locals) total += v.size();
    std::vector<uint32_t> merged;
    merged.reserve(total);
    for (auto& v : locals) merged.insert(merged.end(), v.begin(), v.end());
    return merged;
}

using Clock = std::chrono::steady_clock;

int main(int argc, char** argv) {
    size_t instanceCount = 1'000'000;
    int repeats = 30;
    if (argc >= 2) instanceCount = std::stoull(argv[1]);
    if (argc >= 3) repeats = std::stoi(argv[2]);

    const int hwThreads = static_cast<int>(std::thread::hardware_concurrency());
    std::vector<int> threadCounts = {1, 2, 4, 6, 8, 10, 12, 16, 20};
    threadCounts.erase(std::remove_if(threadCounts.begin(), threadCounts.end(),
                                      [&](int n) { return n > hwThreads; }),
                       threadCounts.end());
    if (std::find(threadCounts.begin(), threadCounts.end(), hwThreads) == threadCounts.end())
        threadCounts.push_back(hwThreads);

    const Frustum fr = makeFrustum({0.0f, 0.0f, 900.0f}, {0.0f, 0.0f, 0.0f},
                                   {0.0f, 1.0f, 0.0f},
                                   60.0f * 3.14159265f / 180.0f, 16.0f / 9.0f,
                                   10.0f, 2600.0f);
    const std::vector<AABB> boxes = makeScene(instanceCount);

    // Correctness: the p-vertex plane test is a conservative cull, so it must
    // never drop an actually-visible box (false cull == 0); its few extra
    // "visible" boxes are the well-known conservative cases where every corner
    // is outside some plane but no single corner is inside all six.
    size_t refVisible = 0;
    for (const AABB& b : boxes)
        if (visibleAabbReference(fr, b)) ++refVisible;
    size_t fastVisible = 0;
    size_t falseCulls = 0;
    for (size_t i = 0; i < boxes.size(); ++i) {
        const bool fast = visibleAabb(fr, boxes[i]);
        const bool exact = visibleAabbReference(fr, boxes[i]);
        if (fast) ++fastVisible;
        if (exact && !fast) ++falseCulls; // a truly-visible box wrongly culled
    }
    std::cout << "Instances: " << instanceCount
              << " | hardware threads: " << hwThreads
              << " | false culls (must be 0): " << falseCulls << '\n';
    std::cout << "Visible instances (ground truth): " << refVisible << '\n';
    std::cout << "Conservative p-vertex visible: " << fastVisible
              << " (+" << (fastVisible - refVisible) << " conservative, "
              << (100.0 * (fastVisible - refVisible) / std::max<size_t>(1, refVisible))
              << "% over-estimate)\n";

    FILE* csv = std::fopen("artifacts/frustum_cull_benchmark.csv", "w");
    if (csv) std::fprintf(csv, "threads,avg_ms,min_ms,median_ms,visible,speedup_avg,speedup_min,eff_min\n");

    double serialMs = 0.0, serialMin = 0.0;
    std::cout << '\n' << std::left << std::setw(9) << "threads"
              << std::right << std::setw(12) << "avg(ms)" << std::setw(12) << "min(ms)"
              << std::setw(12) << "median(ms)" << std::setw(12) << "visible"
              << std::setw(11) << "sp(avg)" << std::setw(11) << "sp(min)"
              << std::setw(10) << "eff(min)" << '\n';

    for (int threads : threadCounts) {
        const auto chunks = splitChunks(boxes.size(), threads);
        CullPool pool(threads, boxes, fr);
        std::vector<double> samples;
        samples.reserve(repeats);
        size_t visibleCount = 0;
        volatile uint32_t sink = 0;
        // Warm-up round: touches pages, grows per-thread buffers, primes barriers.
        std::vector<std::vector<uint32_t>> recycled;
        {
            auto warm = pool.run(chunks, {});
            (void)mergeVisible(std::vector<std::vector<uint32_t>>(warm)); // copy ids only
            for (auto& v : warm) v.clear();      // keep capacity, drop contents
            recycled = std::move(warm);
        }
        for (int rep = 0; rep < repeats; ++rep) {
            const auto t0 = Clock::now();
            auto locals = pool.run(chunks, std::move(recycled));
            auto merged = mergeVisible(std::move(locals));
            const auto t1 = Clock::now();
            sink ^= merged.empty() ? 0u : merged.front();
            visibleCount = merged.size();
            samples.push_back(std::chrono::duration<double, std::milli>(t1 - t0).count());
            recycled = std::move(locals); // shells emptied by mergeVisible? ensure below
            for (auto& v : recycled) v.clear();
        }
        std::sort(samples.begin(), samples.end());
        const double avg = std::accumulate(samples.begin(), samples.end(), 0.0) / samples.size();
        const double mn = samples.front();
        const double med = samples[samples.size() / 2];
        if (threads == 1) { serialMs = avg; serialMin = mn; }
        const double speedAvg = serialMs / avg;
        const double speedMin = serialMin / mn;
        const double efficiency = speedMin / threads;
        if (visibleCount != fastVisible) {
            std::cout << "WARNING: thread=" << threads << " visible=" << visibleCount
                      << " differs from serial fast count " << fastVisible << '\n';
        }
        std::cout << std::left << std::setw(9) << threads
                  << std::right << std::fixed << std::setprecision(3)
                  << std::setw(12) << avg << std::setw(12) << mn << std::setw(12) << med
                  << std::setw(12) << visibleCount
                  << std::setw(11) << std::setprecision(2) << speedAvg
                  << std::setw(11) << std::setprecision(2) << speedMin
                  << std::setw(9) << std::setprecision(2) << efficiency << 'x' << '\n';
        if (csv) {
            std::fprintf(csv, "%d,%.4f,%.4f,%.4f,%zu,%.4f,%.4f,%.4f\n",
                         threads, avg, mn, med, visibleCount, speedAvg, speedMin, efficiency);
        }
    }
    if (csv) std::fclose(csv);
    std::cout << "\nCSV report: artifacts/frustum_cull_benchmark.csv\n";
    return 0;
}
