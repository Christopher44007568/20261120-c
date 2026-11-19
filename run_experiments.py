"""端到端实验入口：跑内存池对照实验并输出中文报告。"""

import json
import os

from gpupool.workload import compare_strategies, stability_run, pressure_run, \
    fragmentation_demo, churn_frag_curve
from floorplan.layout import FloorPlan, Room, WALL, ROOM, CORRIDOR, \
    generate_floor_plan, check_layout


def pct(value):
    return f"{value * 100:.1f}%"


def print_strategy_table(results):
    header = (
        f"{'策略':<18}{'分配块数':>8}{'空闲段':>8}{'堆块数':>8}"
        f"{'碎片率':>10}{'峰值提交':>10}{'稳态提交':>10}{'失败':>6}"
    )
    print(header)
    print("-" * len(header))
    for name, stats in results.items():
        print(
            f"{name:<18}{stats['active_blocks']:>8}{stats['free_segments']:>8}"
            f"{stats['heap_blocks']:>8}{pct(stats['final_frag']):>10}"
            f"{stats['peak_committed']:>9}MB{stats['steady_committed']:>9}MB"
            f"{stats['failures']:>6}"
        )


def run_gpu_experiments():
    print("=" * 78)
    print("一、GPU 内存池：频繁创建/销毁资源的三策略对照（容量 256MB，40 tick）")
    print("=" * 78)
    events, results = compare_strategies(capacity=256, ticks=40)
    print(f"回放事件总数: {len(events)}")
    print_strategy_table(results)

    naive = results["naive"]
    recycle = results["recycle"]
    compact = results["recycle_compact"]
    print("\n关键结论:")
    print(f"- 驻留回收命中 {recycle['cache_reuses']} 次，"
          f"失活资源驱逐 {recycle['evictions']} 次，"
          f"重上传 {recycle['reupload_bytes']}MB")
    print(f"- 碎片整理搬运 {compact['bytes_moved']}MB，"
          f"整理 {compact['compactions']} 轮；"
          f"碎片率 {pct(naive['final_frag'])} -> "
          f"{pct(compact['final_frag'])}")
    print(f"- 显存峰值(高水位): naive {naive['peak_committed']}MB / "
          f"recycle {recycle['peak_committed']}MB / "
          f"recycle+compact {compact['peak_committed']}MB；"
          f"整理后稳态仅 {compact['steady_committed']}MB")
    print("- 说明：回收缓存以占用池内空闲换取分配零增长，峰值差异在碎片专项中隔离验证")

    print("\n" + "=" * 78)
    print("二、内存池稳定性：200 tick 高频增删（种子固定可复现）")
    print("=" * 78)
    stable = stability_run(ticks=200)
    print(f"存活分配块数: {stable['active_blocks']}，空闲段: {stable['free_segments']}，"
          f"堆块数: {stable['heap_blocks']}")
    print(f"最终碎片率: {pct(stable['final_frag'])}，"
          f"平均碎片率: {pct(stable['mean_frag'])}，"
          f"峰值碎片率: {pct(stable['max_frag'])}")
    print(f"显存峰值: {stable['peak_committed']}MB / 容量 256MB，"
          f"分配失败: {stable['failures']}")
    curve = churn_frag_curve()
    print("碎片率随增删轮次变化（每 20 tick 整理后采样）:")
    for point in curve:
        print(f"  tick {point['tick']:>3}: 碎片率 {pct(point['frag']):>7}，"
              f"堆块 {point['heap_blocks']}，存活块 {point['active_blocks']}，"
              f"提交 {point['committed']}MB")

    print("\n" + "=" * 78)
    print("三、碎片整理专项：交错孔洞 + 大块申请（容量 192MB）")
    print("=" * 78)
    demo = fragmentation_demo(capacity=192)
    print_strategy_table(demo)
    print(f"整理后最终碎片率 {pct(demo['recycle_compact']['final_frag'])}，"
          f"搬运 {demo['recycle_compact']['bytes_moved']}MB")
    print(f"整理使平均驻留 {demo['naive']['mean_committed']:.1f}MB -> "
          f"{demo['recycle_compact']['mean_committed']:.1f}MB，"
          f"峰值 {demo['naive']['peak_committed']}MB -> "
          f"{demo['recycle_compact']['peak_committed']}MB，稳态 "
          f"{demo['naive']['steady_committed']}MB -> "
          f"{demo['recycle_compact']['steady_committed']}MB\n")

    print("=" * 78)
    print("四、容量压力测试：160MB 下验证驻留策略减少分配失败")
    print("=" * 78)
    pressure = pressure_run(ticks=30, capacity=160)
    for name, stats in pressure.items():
        print(f"{name:<18} 失败 {stats['failures']:>3} 次，"
              f"峰值 {stats['peak_committed']}MB，"
              f"碎片率 {pct(stats['final_frag'])}，"
              f"驱逐 {stats['evictions']} 次")
    return {"main": results, "stability": stable, "churn_curve": curve,
            "pressure": pressure,
            "frag_demo": demo,
            "event_count": len(events)}


def run_floorplan():
    print("\n" + "=" * 78)
    print("五、房间布局：面积、碰撞数与走道连通性（走道 BFS 连通验证）")
    print("=" * 78)
    specs = [
        ("R1", 4, 5), ("R2", 5, 4), ("R3", 4, 6), ("R4", 3, 5),
        ("R5", 5, 6), ("R6", 4, 4),
    ]
    plan = generate_floor_plan(specs)
    report = check_layout(plan)
    for room_id, area in report["room_areas"].items():
        print(f"{room_id} 面积: {area} 格")
    print(f"房间总面积: {report['total_area']} 格，碰撞数: {report['collisions']}")
    print(f"走道连通: {'是' if report['connected'] else '否'}，"
          f"可达房间 {len(report['reachable'])}/{report['rooms']}")

    blocked = FloorPlan(plan.height, plan.width)
    blocked.carve_room(Room("X1", 0, 1, 3, 3))
    blocked.carve_room(Room("X2", plan.height - 3, plan.width - 4, 3, 3))
    blocked_report = check_layout(blocked)
    print(f"负面对照(无走道): 连通={blocked_report['connected']}，"
          f"碰撞数={blocked_report['collisions']}")
    return {"plan": report, "negative_control": blocked_report}


def main():
    gpu_report = run_gpu_experiments()
    floor_report = run_floorplan()
    out_dir = os.path.join(os.path.dirname(__file__), "artifacts")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "experiment_report.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"gpu": gpu_report, "floorplan": floor_report},
                  handle, ensure_ascii=False, indent=2)
    print(f"\n机器可读结果已写入 artifacts/experiment_report.json")


if __name__ == "__main__":
    main()
