import unittest

from gpupool.allocator import MemoryPool


class AllocatorTest(unittest.TestCase):
    def test_growth_is_heap_block_aligned(self):
        pool = MemoryPool(capacity=128, heap_block_size=32)
        pool.allocate(10)
        self.assertEqual(pool.heap_blocks, 1)
        self.assertEqual(pool.committed, 32)
        pool.allocate(30)
        self.assertEqual(pool.heap_blocks, 2)

    def test_free_coalesces_adjacent_segments(self):
        pool = MemoryPool(capacity=128)
        a = pool.allocate(8)
        b = pool.allocate(8)
        c = pool.allocate(8)
        pool.free(b)
        pool.free(a)
        self.assertEqual(pool.free_segments[0], (0, 16))
        self.assertEqual(pool.free_segments[0][1], 16)
        pool.free(c)
        self.assertEqual(len(pool.free_segments), 1)
        self.assertEqual(pool.free_segments[0][1], pool.committed)

    def test_compaction_packs_live_blocks(self):
        pool = MemoryPool(capacity=128, heap_block_size=16)
        ids = [pool.allocate(8) for _ in range(6)]
        pool.free(ids[1])
        pool.free(ids[3])
        frag_before = pool.external_fragmentation()
        moved = pool.compact()
        self.assertGreater(moved, 0)
        self.assertEqual(pool.external_fragmentation(), 0.0)
        self.assertLessEqual(pool.committed, 48)
        self.assertGreater(frag_before, 0.0)
        offsets = sorted(block.offset for block in pool.allocations.values())
        self.assertEqual(offsets, [0, 8, 16, 24])

    def test_capacity_failure_is_counted(self):
        pool = MemoryPool(capacity=32, heap_block_size=32)
        self.assertIsNotNone(pool.allocate(30))
        self.assertIsNone(pool.allocate(8))
        self.assertEqual(pool.failed_requests, 1)

    def test_best_fit_reuses_smallest_matching_segment(self):
        pool = MemoryPool(capacity=128)
        pool.allocate(16)
        big = pool.allocate(32)
        pool.allocate(8)
        small = pool.allocate(8)
        pool.free(big)
        pool.free(small)
        new_id = pool.allocate(8)
        self.assertEqual(len(pool.allocations), 3)
        self.assertEqual(pool.allocations[new_id].size, 8)
        self.assertEqual(pool.allocations[new_id].offset, 24)
        self.assertEqual(pool.free_segments, [(32, 32)])


if __name__ == "__main__":
    unittest.main()
