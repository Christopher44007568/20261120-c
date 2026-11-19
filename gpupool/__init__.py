"""GPU 内存池模拟：分配器、资源驻留与碎片整理实验。"""

from .allocator import MemoryPool
from .residency import ResidencyManager

__all__ = ["MemoryPool", "ResidencyManager"]
