"""确定性工作负载与实验驱动。

同一份事件序列在 naive / recycle / recycle+compact 三种策略下回放，
保证对照实验只受驻留策略与碎片整理影响。
"""

import random

from .residency import ResidencyManager, TRANSIENT, PERSISTENT


def build_workload(ticks=40, seed=20261120, transient_per_tick=5,
                   persistent_count=8, persistent_size=12):
    """生成事件流：先铺长生命周期纹理/缓冲，再做高频增删与失活/重驻。"""
    rng = random.Random(seed)
    events = []
    for index in range(persistent_count):
        events.append(("create_p", f"p{index}", persistent_size))
    live_transients = []
    serial = 0
    for tick in range(ticks):
        for index in range(persistent_count):
            events.append(("phase", tick))
            break
        for index in range(persistent_count):
            rid = f"p{index}"
            if rng.random() < 0.12:
                events.append(("inactive", rid))
            elif rng.random() < 0.10:
                events.append(("active", rid))
        for _ in range(transient_per_tick):
            size = rng.choice((2, 4, 6, 8, 10, 12, 16, 20))
            if live_transients and rng.random() < 0.7:
                victim = live_transients.pop(rng.randrange(len(live_transients)))
                events.append(("destroy_t", victim))
            rid = f"t{serial}"
            serial += 1
            events.append(("create_t", rid, size))
            live_transients.append(rid)
        for rid in list(live_transients):
            if rng.random() < 0.25:
                live_transients.remove(rid)
                events.append(("destroy_t", rid))
    for rid in list(live_transients):
        events.append(("destroy_t", rid))
    return events


def run_experiment(events, capacity=256, strategy="recycle",
                   compaction=False, compact_every=10, frag_threshold=0.4,
                   heap_block_size=32, compact_on_phase=False):
    manager = ResidencyManager(capacity=capacity, strategy=strategy,
                               heap_block_size=heap_block_size)
    ticks = 0
    frag_samples = []
    peak_samples = []
    failures = 0

    def sample():
        stats = manager.stats()
        frag_samples.append(stats["external_frag"])
        peak_samples.append(stats["committed"])

    for event in events:
        kind = event[0]
        if kind == "phase":
            ticks += 1
            if compaction and compact_on_phase:
                manager.pool.compact()
            if compaction and ticks % compact_every == 0:
                manager.maybe_compact(frag_threshold)
            sample()
        elif kind == "create_t":
            if not manager.create_transient(event[1], event[2]):
                failures += 1
        elif kind == "destroy_t":
            if event[1] in manager.resources:
                manager.destroy(event[1])
        elif kind == "create_p":
            if not manager.create_persistent(event[1], event[2]):
                failures += 1
        elif kind == "inactive":
            if event[1] in manager.resources:
                manager.make_inactive(event[1])
        elif kind == "active":
            if event[1] in manager.resources:
                manager.make_active(event[1])
    if compaction:
        manager.pool.compact()
        frag_samples[-1] = manager.pool.external_fragmentation()
        peak_samples[-1] = manager.pool.committed
    stats = manager.stats()
    stats.update({
        "ticks": ticks,
        "failures": failures,
        "final_frag": frag_samples[-1] if frag_samples else 0.0,
        "mean_frag": sum(frag_samples) / len(frag_samples) if frag_samples else 0.0,
        "max_frag": max(frag_samples, default=0.0),
        "mean_committed": sum(peak_samples) / len(peak_samples) if peak_samples else 0.0,
        "steady_committed": manager.pool.committed,
    })
    return stats


def compare_strategies(capacity=256, ticks=40, **kwargs):
    events = build_workload(ticks=ticks, **kwargs)
    results = {
        "naive": run_experiment(events, capacity, strategy="naive"),
        "recycle": run_experiment(events, capacity, strategy="recycle"),
        "recycle_compact": run_experiment(
            events, capacity, strategy="recycle", compaction=True),
    }
    return events, results


def stability_run(ticks=200, capacity=256, seed=777):
    events = build_workload(ticks=ticks, seed=seed)
    return run_experiment(events, capacity, strategy="recycle", compaction=True)


def churn_frag_curve(ticks=120, capacity=256, seed=777, sample_every=20):
    """每隔 sample_every 个 tick 采样碎片率与堆块数，验证内存池不发散。"""
    rng_events = build_workload(ticks=ticks, seed=seed)
    manager = ResidencyManager(capacity=capacity, strategy="recycle")
    curve = []
    tick = 0
    for event in rng_events:
        kind = event[0]
        if kind == "phase":
            tick += 1
            if tick % sample_every == 0:
                manager.pool.compact()
                stats = manager.stats()
                curve.append({
                    "tick": tick,
                    "frag": stats["external_frag"],
                    "heap_blocks": stats["heap_blocks"],
                    "active_blocks": stats["active_blocks"],
                    "committed": stats["committed"],
                })
        elif kind == "create_t":
            manager.create_transient(event[1], event[2])
        elif kind == "destroy_t" and event[1] in manager.resources:
            manager.destroy(event[1])
        elif kind == "create_p":
            manager.create_persistent(event[1], event[2])
    return curve


def pressure_run(ticks=30, capacity=160):
    events = build_workload(ticks=ticks, seed=4242, transient_per_tick=8)
    return {
        "naive": run_experiment(events, capacity, strategy="naive"),
        "recycle_compact": run_experiment(
            events, capacity, strategy="recycle", compaction=True),
    }


def fragmentation_demo(capacity=192, heap_block_size=16):
    """交错分配/释放制造孔洞，再用大块申请暴露碎片代价。

    无整理：孔洞无法承载大块 -> 继续向高地址增长 -> 峰值抬高；
    整理后：孔洞被压实，大块复用低地址 -> 峰值与失败数同时下降。
    """
    events = []
    for index in range(8):
        events.append(("create_p", f"a{index}", 8))
    events.append(("phase", 1))
    for index in range(0, 8, 2):
        events.append(("destroy_t", f"a{index}"))
    events.append(("phase", 2))
    for index in range(2):
        events.append(("create_t", f"big{index}", 16))
    events.append(("phase", 3))
    for index in range(1, 8, 2):
        events.append(("destroy_t", f"a{index}"))
    for index in range(2):
        events.append(("destroy_t", f"big{index}"))
    return {
        "naive": run_experiment(events, capacity, strategy="naive",
                                heap_block_size=heap_block_size),
        "recycle": run_experiment(events, capacity, strategy="recycle",
                                  heap_block_size=heap_block_size),
        "recycle_compact": run_experiment(
            events, capacity, strategy="recycle", compaction=True,
            compact_every=1, heap_block_size=heap_block_size,
            compact_on_phase=True),
    }
