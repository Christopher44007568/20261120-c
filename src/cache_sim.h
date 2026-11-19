#pragma once
#include <cstdint>
#include <vector>

// Set-associative LRU cache simulator over 64-bit byte addresses.
// Used to model BVH node / triangle fetch locality during traversal.
class CacheSim {
public:
  CacheSim(uint32_t sizeBytes, uint32_t lineBytes, uint32_t ways)
      : lineBytes_(lineBytes),
        sets_(sizeBytes / lineBytes / ways),
        ways_(ways),
        tags_(sets_ * ways, kInvalid),
        age_(sets_ * ways, 0),
        clock_(0),
        hits_(0),
        misses_(0) {}

  void access(uint64_t addr) {
    uint64_t line = addr / lineBytes_;
    uint64_t set = line % sets_;
    uint64_t tag = line / sets_;
    uint64_t base = set * ways_;
    ++clock_;
    for (uint32_t w = 0; w < ways_; ++w) {
      if (tags_[base + w] == tag) {
        age_[base + w] = clock_;
        ++hits_;
        return;
      }
    }
    // miss: evict LRU way
    uint32_t victim = 0;
    uint64_t oldest = ~0ull;
    for (uint32_t w = 0; w < ways_; ++w) {
      if (tags_[base + w] == kInvalid) { victim = w; break; }
      if (age_[base + w] < oldest) { oldest = age_[base + w]; victim = w; }
    }
    tags_[base + victim] = tag;
    age_[base + victim] = clock_;
    ++misses_;
  }

  uint64_t hits() const { return hits_; }
  uint64_t misses() const { return misses_; }
  uint64_t bytesFetched() const { return misses_ * lineBytes_; }

private:
  static constexpr uint64_t kInvalid = ~0ull;
  uint32_t lineBytes_, sets_, ways_;
  std::vector<uint64_t> tags_;
  std::vector<uint64_t> age_;
  uint64_t clock_;
  uint64_t hits_, misses_;
};
