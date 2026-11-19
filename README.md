# Material Graph Editor & Shader Codegen

节点式材质图编辑与着色器代码生成工具：把节点连成有向图后输出 **GLSL 450**
与 **HLSL (SM 6.0)** 代码，内置类型推断、循环依赖拒绝、确定性拓扑排序、
死节点清理、CPU 预览解释器，以及基于 `glslangValidator` 的真实编译验证。

仅依赖 Python 3 标准库；编译器通过本地解包的 `glslangValidator` 调用，
无需 root。

## 管线

1. **建图/连线** — `Graph.add_node` / `Graph.connect`，连接时校验端口存在性、
   禁止自环与一个输入端口被重复驱动。
2. **循环依赖检测** — 迭代式 DFS 白/灰/黑染色，发现环即抛出 `CycleError`
   并给出环路径，下游所有阶段不再执行。
3. **死节点清理** — 从 `SurfaceOutput` 输出节点反向标记可达节点，
   不可达节点及其边被整体移除。
4. **拓扑排序** — Kahn 算法 + 最小堆字典序 tie-break，顺序完全确定，
   保证生成代码稳定可复现。
5. **类型推断** — 按拓扑序解析端口类型，支持标量向向量广播、同宽向量直通、
   标量基类（float/int/bool）一致性检查，类型冲突抛 `TypeInferenceError`。
6. **代码生成** — 同一发射上下文分别产出 GLSL 与 HLSL，自动处理
   `mix/lerp`、`fract/frac`、`mod/fmod`、向量构造器与 uniform/cbuffer 差异。
7. **预览与编译一致性** — CPU 解释器在采样点上求值；序列化拓扑重建图后
   再次求值必须数值一致；两份着色器均编译为 SPIR-V 并通过；重复生成逐字节相同。

## 目录结构

| 路径 | 职责 |
| --- | --- |
| `matgraph/types.py` | 类型系统、提升与强制转换规则 |
| `matgraph/registry.py` | 声明式节点规格注册 |
| `matgraph/nodes_builtins.py` | 常量、UV/Time/Normal、向量、Checker、输出节点 |
| `matgraph/nodes_math.py` | 算术、向量数学、插值、比较节点 |
| `matgraph/graph.py` | 图/节点/边数据结构与拓扑序列化 |
| `matgraph/analysis.py` | 环检测、拓扑排序、死节点清理 |
| `matgraph/inference.py` | 类型推断 |
| `matgraph/interpreter.py` | CPU 预览解释器与预览网格 |
| `matgraph/codegen.py` | GLSL / HLSL 代码生成 |
| `matgraph/compiler.py` | glslang 编译、SPIR-V 产出、一致性验证 |
| `matgraph/pipeline.py` | 端到端编排 |
| `demo/run_demo.py` | 完整演示，产物写入 `artifacts/` |
| `tests/` | 24 个单元/集成测试 |

## 运行

```bash
python3 -m unittest discover -s tests -v   # 全部测试（含真实编译）
python3 demo/run_demo.py                    # 端到端演示
```

演示产物：

- `artifacts/material.frag` — 生成的 GLSL 片段着色器；
- `artifacts/material.hlsl` — 生成的 HLSL 像素着色器；
- `artifacts/pipeline_report.json` — 拓扑、排序、死节点、推断类型、预览采样、
  编译与一致性验证报告；
- `artifacts/demo_output.txt` — 控制台完整输出。

## 最小用法

```python
from matgraph import Graph, run_pipeline

graph = Graph("example")
graph.add_node("uv", "UV")
graph.add_node("checker", "Checker", {"scale": 8.0})
graph.add_node("out", "SurfaceOutput")
graph.connect("checker", "rgb", "out", "base_color")

result = run_pipeline(graph)
print(result.topo_order)        # 确定性拓扑顺序
print(result.dead_nodes)        # 被清理的死节点
print(result.shaders["glsl"])   # GLSL 源码
print(result.shaders["hlsl"])   # HLSL 源码
print(result.verification["ok"])  # 双后端编译 + 一致性是否通过
```

## 验证口径

环境无 GPU，无法直接执行着色器，因此“预览与编译结果一致”按以下可证伪的
口径验证：

- 同一张推断后的图分别生成 GLSL 与 HLSL，二者均被 `glslangValidator`
  编译为 SPIR-V（真实编译器，非语法检查）；
- 图拓扑经 JSON 序列化/反序列化重建后，CPU 预览在全部采样点上数值一致，
  证明预览路径与编译路径消费同一份节点拓扑；
- 代码生成重复执行逐字节相同，保证稳定可复现。
