"""资源驻留管理：生命周期分层、回收缓存与惰性驱逐。

两种策略：
- naive：销毁即归还，无缓存无驱逐，池满直接分配失败；
- recycle：短生命周期资源进入按尺寸分桶的回收缓存，
  分配失败时先弃缓存、再驱逐失活的长生命周期资源，并按需压缩整理。
"""

from dataclasses import dataclass

from .allocator import MemoryPool

TRANSIENT = "transient"
PERSISTENT = "persistent"


@dataclass
class Resource:
    rid: str
    size: int
    lifecycle: str
    alloc_id: object = None
    resident: bool = True
    active: bool = True


class ResidencyManager:
    def __init__(self, capacity=256, heap_block_size=32, strategy="recycle",
                 max_cached_bytes=96, size_class=4):
        self.pool = MemoryPool(capacity, heap_block_size=heap_block_size)
        self.strategy = strategy
        self.max_cached_bytes = max_cached_bytes
        self.size_class = size_class
        self.resources = {}
        self.cache = {}          # size_class -> [alloc_id, ...]
        self.cached_bytes = 0
        self.cache_reuses = 0
        self.evictions = 0
        self.reupload_bytes = 0
        self.cache_drops = 0

    def _bucket(self, size):
        return ((size + self.size_class - 1) // self.size_class) * self.size_class

    def create_transient(self, rid, size):
        if self.strategy == "recycle":
            bucket = self._bucket(size)
            entries = self.cache.get(bucket)
            if entries:
                alloc_id = entries.pop()
                self.cached_bytes -= self.pool.allocations[alloc_id].size
                self.cache_reuses += 1
                self.resources[rid] = Resource(rid, size, TRANSIENT, alloc_id)
                return True
        alloc_id = self._allocate_with_residency(size)
        if alloc_id is None:
            return False
        self.resources[rid] = Resource(rid, size, TRANSIENT, alloc_id)
        return True

    def create_persistent(self, rid, size):
        alloc_id = self._allocate_with_residency(size)
        if alloc_id is None:
            return False
        self.resources[rid] = Resource(rid, size, PERSISTENT, alloc_id)
        return True

    def _allocate_with_residency(self, size):
        alloc_id = self.pool.allocate(size)
        if alloc_id is not None or self.strategy != "recycle":
            return alloc_id
        self._drop_cache_until(size)
        alloc_id = self.pool.allocate(size)
        if alloc_id is not None:
            return alloc_id
        self._evict_inactive_until(size)
        alloc_id = self.pool.allocate(size)
        if alloc_id is None:
            self.pool.compact()
            alloc_id = self.pool.allocate(size)
        return alloc_id

    def _drop_cache_until(self, size):
        """放弃缓存块直到底层池能容纳 size（合并后产生连续空闲）。"""
        for bucket in list(self.cache):
            while self.cache[bucket]:
                alloc_id = self.cache[bucket].pop()
                block = self.pool.allocations.get(alloc_id)
                if block is None:
                    continue
                self.cached_bytes -= block.size
                self.pool.free(alloc_id)
                self.cache_drops += 1
                if self.pool.external_fragmentation() == 0.0 or \
                        self.pool.stats()["largest_free"] >= size:
                    if not self.cache[bucket]:
                        del self.cache[bucket]
                    return
            del self.cache[bucket]

    def _evict_inactive_until(self, size):
        for res in list(self.resources.values()):
            if self.pool.stats()["largest_free"] >= size:
                return
            if res.lifecycle == PERSISTENT and not res.active and res.resident:
                self.pool.free(res.alloc_id)
                res.alloc_id = None
                res.resident = False
                self.evictions += 1

    def make_active(self, rid):
        """失活资源重新驻留，触发一次重新上传。"""
        res = self.resources[rid]
        res.active = True
        if res.resident:
            return True
        alloc_id = self._allocate_with_residency(res.size)
        if alloc_id is None:
            return False
        res.alloc_id = alloc_id
        res.resident = True
        self.reupload_bytes += res.size
        return True

    def make_inactive(self, rid):
        self.resources[rid].active = False

    def destroy(self, rid):
        res = self.resources.pop(rid)
        if not res.resident:
            return
        if self.strategy == "recycle" and res.lifecycle == TRANSIENT and \
                self.cached_bytes + res.size <= self.max_cached_bytes:
            bucket = self._bucket(res.size)
            self.cache.setdefault(bucket, []).append(res.alloc_id)
            self.cached_bytes += res.size
        else:
            self.pool.free(res.alloc_id)

    def maybe_compact(self, frag_threshold=0.4):
        if self.pool.external_fragmentation() >= frag_threshold:
            return self.pool.compact()
        return 0

    def stats(self):
        stats = self.pool.stats()
        stats.update({
            "strategy": self.strategy,
            "cached_bytes": self.cached_bytes,
            "cache_entries": sum(len(v) for v in self.cache.values()),
            "cache_reuses": self.cache_reuses,
            "cache_drops": self.cache_drops,
            "evictions": self.evictions,
            "reupload_bytes": self.reupload_bytes,
        })
        return stats
