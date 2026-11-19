"""内存池底层分配器。

模拟 GPU 显存堆：容量按 heap_block_size 对齐逐块提交，
内部用有序空闲段表管理，支持 best-fit 分配、相邻段合并与压缩整理。
单位统一为 MiB（整数），指标计算与真实字节分配器等价。
"""

from dataclasses import dataclass


@dataclass
class AllocBlock:
    offset: int
    size: int


class MemoryPool:
    def __init__(self, capacity, heap_block_size=32, min_split=1):
        self.capacity = capacity
        self.heap_block_size = heap_block_size
        self.min_split = min_split
        self.allocations = {}          # alloc_id -> AllocBlock
        self.free_segments = []        # [(offset, size)]，按 offset 有序
        self.committed = 0
        self.peak_committed = 0
        self.resident_bytes = 0
        self.peak_resident = 0
        self.total_alloc_requests = 0
        self.failed_requests = 0
        self.compaction_events = 0
        self.bytes_moved = 0
        self._next_id = 1

    @property
    def heap_blocks(self):
        return self.committed // self.heap_block_size

    @property
    def free_bytes(self):
        return self.committed - self.resident_bytes

    def _insert_free(self, offset, size):
        """插入空闲段并与相邻段合并。"""
        segments = self.free_segments
        index = 0
        while index < len(segments) and segments[index][0] < offset:
            index += 1
        merged = []
        for seg in segments[:index]:
            merged.append(seg)
        for seg in [(offset, size)] + segments[index:]:
            if merged and merged[-1][0] + merged[-1][1] == seg[0]:
                prev_off, prev_size = merged.pop()
                seg = (prev_off, prev_size + seg[1])
            merged.append(seg)
        self.free_segments = merged

    def allocate(self, size):
        """best-fit 分配；失败返回 None。"""
        self.total_alloc_requests += 1
        best = -1
        for index, (_, seg_size) in enumerate(self.free_segments):
            if seg_size >= size and (best == -1 or seg_size < self.free_segments[best][1]):
                best = index
        if best >= 0:
            offset, seg_size = self.free_segments.pop(best)
            if seg_size - size >= self.min_split:
                self._insert_free(offset + size, seg_size - size)
        else:
            offset = self._grow(size)
            if offset is None:
                self.failed_requests += 1
                return None
        alloc_id = self._next_id
        self._next_id += 1
        self.allocations[alloc_id] = AllocBlock(offset, size)
        self.resident_bytes += size
        self.peak_resident = max(self.peak_resident, self.resident_bytes)
        return alloc_id

    def _grow(self, size):
        old_committed = self.committed
        needed = old_committed + size
        if needed > self.capacity:
            return None
        blocks = (needed - old_committed + self.heap_block_size - 1) // self.heap_block_size
        new_committed = min(self.capacity, old_committed + blocks * self.heap_block_size)
        offset = old_committed
        remainder = new_committed - offset - size
        self.committed = new_committed
        self.peak_committed = max(self.peak_committed, new_committed)
        if remainder > 0:
            self._insert_free(offset + size, remainder)
        return offset

    def free(self, alloc_id):
        block = self.allocations.pop(alloc_id)
        self.resident_bytes -= block.size
        self._insert_free(block.offset, block.size)

    def compact(self, trim=True):
        """把存活块搬到低地址，空闲空间合并为尾部单段，可归还整堆块。"""
        live = sorted(self.allocations.items(), key=lambda item: item[1].offset)
        cursor = 0
        moved = 0
        for _, block in live:
            if block.offset != cursor:
                moved += block.size
                block.offset = cursor
            cursor += block.size
        self.bytes_moved += moved
        if moved or len(self.free_segments) != 1:
            self.compaction_events += 1
        new_committed = cursor
        if trim:
            block = self.heap_block_size
            aligned = ((cursor + block - 1) // block) * block
            new_committed = min(self.committed, aligned)
        self.committed = new_committed
        tail = self.committed - cursor
        self.free_segments = [(cursor, tail)] if tail > 0 else []
        return moved

    def external_fragmentation(self):
        """外部碎片率 = 1 - 最大空闲段 / 总空闲字节；无空闲时记 0。"""
        if self.free_bytes <= 0:
            return 0.0
        largest = max((size for _, size in self.free_segments), default=0)
        return 1.0 - largest / self.free_bytes

    def stats(self):
        return {
            "active_blocks": len(self.allocations),
            "free_segments": len(self.free_segments),
            "free_bytes": self.free_bytes,
            "largest_free": max((s for _, s in self.free_segments), default=0),
            "external_frag": self.external_fragmentation(),
            "committed": self.committed,
            "heap_blocks": self.heap_blocks,
            "resident": self.resident_bytes,
            "peak_resident": self.peak_resident,
            "peak_committed": self.peak_committed,
            "compactions": self.compaction_events,
            "bytes_moved": self.bytes_moved,
            "failed_requests": self.failed_requests,
        }
