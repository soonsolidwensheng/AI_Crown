# CutMesh Python

将 CutMesh 网格切割库封装为 Python 可 `import` 的扩展模块，已预编译
**Python 3.8** 与 **Python 3.11** 两个 ABI 版本。

## 基础功能

- 读取 STL 网格（`Mesh.read_stl`）
- 读取 `.asc` 轮廓点（`MeshLibCutMesh.read_contour_from_asc`）
- 加载网格到切割器（`MeshLibCutMesh.load_from_mesh`）
- 按轮廓切割网格（`MeshLibCutMesh.segment_by_contour`），可输出多个子网格
- 写出 STL（`Mesh.write_stl`）

## 目录结构

```
dist/
├── README.md          本说明
├── test_cutmesh.py    顶层示例脚本 + 三个程序化接口 (run_cutmesh_test / run_api_test / run_api_demo)
├── example/           演示输入
│   ├── input_mesh.stl
│   └── input_curve.asc
├── py311/             Python 3.11 版本
│   ├── cutmesh.cpython-311-x86_64-linux-gnu.so
│   └── libs/          运行时第三方 .so
└── py38/              Python 3.8 版本
    ├── cutmesh.cpython-38-x86_64-linux-gnu.so
    └── libs/          运行时第三方 .so
```

## 环境前提

| 项 | 要求 |
|---|---|
| 操作系统 | Linux x86_64 |
| glibc | ≥ 2.39（`libmlCutMesh.so` 依赖 `GLIBC_2.38`） |
| Python | `py311/` 需 3.11.x；`py38/` 需 3.8.x（ABI 标签须匹配） |
| numpy | 必须（3.11 任意版本；3.8 需 `numpy<1.25`） |
| 构建/编译器 | **不需要**（已预编译） |

查看本机 glibc：`ldd --version`

## 快速开始

```bash
# 1) 切换到匹配版本的 Python 虚拟环境 (示例用 3.8)
source .venv38/bin/activate

# 2) 安装 numpy (若尚未安装; 3.8 需 <1.25)
pip install "numpy<1.25"

# 3) 运行 (用 --lib_path 指定 .so 所在目录)
python test_cutmesh.py --lib_path ./py38
```

输出（默认写到 `test_cutmesh.py` 同级的 `output/` 目录）：

```
vertices: 70992
faces:    141980
contour points: 74
cutter faces: 141980
segmentByContour => True  res.size = 2
output dir: .../output
writeStl[0] .../output/0.stl => True  verts=919 faces=1556
writeStl[1] .../output/1.stl => True  verts=70633 faces=140984
```

## 命令行参数

```
python test_cutmesh.py --lib_path ./py38 [--input example/] [--out my_output/]
    [--test_cutmesh] [--test_api] [--test_demo]

python test_cutmesh.py --lib_path ./py311 --test_cutmesh
python test_cutmesh.py --lib_path ./py311 --test_api
python test_cutmesh.py --lib_path ./py311 --test_demo
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--lib_path` | `./py311` | `cutmesh.so` 所在目录（含同目录 `libs/`） |
| `--input` | `example/` | 输入文件目录（含 `input_mesh.stl` / `input_curve.asc`） |
| `--out` | `output/` | 输出 STL 目录（相对当前工作目录或脚本同级） |
| `--test_cutmesh` | 关 | 运行完整切割流程（`run_cutmesh_test`），输出 STL |
| `--test_api` | 关 | 运行 API 断言自测（`run_api_test`），20 项接口检查 |
| `--test_demo` | 关 | 运行 API 用法演示（`run_api_demo`），打印各接口详细用法 |

> 不带任何 `--test_*` 参数时默认执行完整切割流程。三个 `--test_*` 可单独或组合使用。

## 程序化调用

`test_cutmesh.py` 导出三个函数，可从外部脚本调用：

```python
from test_cutmesh import run_cutmesh_test, run_api_test, run_api_demo

r = run_cutmesh_test(lib_path="./py38", verbose=False)
print(r["ok"], len(r["output_meshes"]))

# 返回 dict 字段:
#   ok            bool              整体是否成功
#   input_mesh    cutmesh.Mesh      输入网格
#   contour_points list             轮廓点
#   cutter_faces  int               切割器面数
#   segment_ok    bool              切割是否成功
#   output_meshes [cutmesh.Mesh...] 切出的子网格列表
#   output_dir    str | None        实际写出目录
#   error         str | None        错误信息

# run_api_test: API 断言自测 (20 项), 返回 (ok, passed, failed, fails)
ok, npass, nfail, fails = run_api_test(lib_path="./py38")
print("API 自测: %d passed, %d failed" % (npass, nfail))

# run_api_demo: API 用法演示 (14 节, 讲解式打印), 返回 (ok, info)
# 演示产物保留在 output/_demo_*.stl / _demo_save.mrmesh
ok, info = run_api_demo(lib_path="./py38")
print("API 演示:", "OK" if ok else info.get("error"))
```

也可直接使用 `cutmesh` 模块 API：

```python
import sys; sys.path.insert(0, "py38")
import cutmesh

mesh = cutmesh.Mesh()
mesh.read_stl("example/input_mesh.stl")
points = cutmesh.MeshLibCutMesh.read_contour_from_asc("example/input_curve.asc")

cutter = cutmesh.MeshLibCutMesh()
cutter.load_from_mesh(mesh)
ok, meshes = cutter.segment_by_contour(points)
for i, m in enumerate(meshes):
    m.write_stl("output/%d.stl" % i)
```

## API 参考

`cutmesh` 模块暴露两个类与若干方法。

### class `cutmesh.Mesh`

表示一个三角网格。

| 成员 | 签名 | 参数 | 返回值 | 说明 |
|---|---|---|---|---|
| 构造 | `Mesh()` | 无 | `cutmesh.Mesh` | 创建空网格 |
| `vertices` | 属性，`list[Vector3f]` | — | `list[Vector3f]`（读写） | 顶点位置数组（每项 3 个 float） |
| `faces` | 属性，`list[Vector3i]` | — | `list[Vector3i]`（读写） | 三角面数组（每项 3 个顶点索引） |
| `read_stl` | `read_stl(file_name) -> bool` | `file_name`: STL 文件路径 | `bool`：`True` 读取成功，`False` 失败 | 读取 STL 并填充 `vertices`/`faces` |
| `write_stl` | `write_stl(file_name, use_binary=True) -> bool` | `file_name`: 输出 STL 路径；`use_binary`: 是否二进制（默认 `True`，`False` 为 ASCII） | `bool`：`True` 写出成功 | 写出网格到 STL 文件 |

示例：
```python
m = cutmesh.Mesh()
m.read_stl("in.stl")
print(len(m.vertices), len(m.faces))
m.write_stl("out.stl", use_binary=True)
```

### class `cutmesh.MeshLibCutMesh`

切割器，加载网格后按轮廓或源/汇面进行分割。

| 方法 | 签名 | 参数 | 返回值 | 说明 |
|---|---|---|---|---|
| 构造 | `MeshLibCutMesh()` | 无 | `cutmesh.MeshLibCutMesh` | 构造空切割器 |
| `load_from_mesh` | `load_from_mesh(mesh) -> bool` | `mesh`: `cutmesh.Mesh`，待加载网格 | `bool`：`True` 加载成功 | 将网格加载到切割器内部 |
| `load_from_file` | `load_from_file(file_path) -> bool` | `file_path`: 网格文件路径（如 `.stl`） | `bool`：`True` 加载成功 | 从文件读取网格并加载到切割器 |
| `export_to_mesh` | `export_to_mesh(mesh) -> bool` | `mesh`: 接收内部网格的空 `cutmesh.Mesh` | `bool`：`True` 导出成功 | 将切割器内部网格导出到给定 `Mesh` |
| `save_to_file` | `save_to_file(file_path) -> bool` | `file_path`: 输出文件路径（如 `.mrmesh`） | `bool`：`True` 保存成功 | 保存切割器内部网格到文件 |
| `segment_by_contour` (单输出) | `segment_by_contour(contour_points, keep_left_side) -> (ok, mesh)` | `contour_points`: 轮廓点序列（`list[Vector3f]` 或 `(N,3)` 数组）；`keep_left_side`: 保留轮廓左侧（`True`），`False` 保留右侧（必填） | `(bool, cutmesh.Mesh)`：`ok` 是否成功，`mesh` 切出的单个网格 | 按轮廓切到单个输出网格 |
| `segment_by_contour` (多输出) | `segment_by_contour(contour_points) -> (ok, meshes)` | `contour_points`: 同上 | `(bool, list[cutmesh.Mesh])`：`ok` 是否成功，`meshes` 切出的子网格列表 | 按轮廓切到多个输出网格 |
| `segment_by_source_sink` | `segment_by_source_sink(source_face_indices, sink_face_indices) -> (ok, mesh)` | `source_face_indices`: 源面索引列表（`list[int]`）；`sink_face_indices`: 汇面索引列表（`list[int]`） | `(bool, cutmesh.Mesh)`：`ok` 是否成功，`mesh` 分割结果 | 按源/汇面索引分割 |
| `get_vertex_count` | `get_vertex_count() -> int` | 无 | `int`：已加载网格的顶点数 | 返回切割器内部网格顶点数 |
| `get_face_count` | `get_face_count() -> int` | 无 | `int`：已加载网格的面数 | 返回切割器内部网格面数 |

静态方法：

| 方法 | 签名 | 参数 | 返回值 | 说明 |
|---|---|---|---|---|
| `read_contour_from_asc` | `read_contour_from_asc(asc_file) -> list[Vector3f]` | `asc_file`: `.asc` 轮廓点文件路径 | `list[Vector3f]`：轮廓点列表（每项 3 个 float） | 读取 `.asc` 文件返回轮廓点 |

> `segment_by_contour` 有两个重载：传 `keep_left_side` 走「单输出」重载，返回 `(ok, Mesh)`；
> 只传 `contour_points` 走「多输出」重载，返回 `(ok, [Mesh, ...])`。
> 三个切割接口风格统一，均为返回元组。

示例：
```python
cutter = cutmesh.MeshLibCutMesh()
cutter.load_from_mesh(mesh)
print("faces:", cutter.get_face_count())

# 多输出 (推荐, 一次切出所有子网格)
ok, meshes = cutter.segment_by_contour(points)
for i, m in enumerate(meshes):
    m.write_stl("output/%d.stl" % i)

# 单输出 (只取一侧, keep_left_side 为必填参数)
ok, single = cutter.segment_by_contour(points, keep_left_side=True)
# 或 ok, single = cutter.segment_by_contour(points, True)

# 源/汇分割
ok, seg = cutter.segment_by_source_sink([0, 1, 2], [100, 101])

# 静态读轮廓
pts = cutmesh.MeshLibCutMesh.read_contour_from_asc("example/input_curve.asc")
```

## 外部构造示例

不从 STL 文件读取，直接用 numpy/list 构造 `Mesh`（顶点 + 面）与轮廓点，调用 `segment_by_contour` 切割。

```python
import sys
import numpy as np

sys.path.insert(0, "py311")   # 或用 --lib_path 指定
import cutmesh

# 1. 手动构造 Mesh: numpy 数组赋值 vertices / faces
#    vertices: (N, 3) float32  ← 对应 Eigen::Vector3f
#    faces:    (M, 3) int32     ← 对应 Eigen::Vector3i
mesh = cutmesh.Mesh()
mesh.vertices = np.array([
    [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
    [0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [1.0, 1.0, 1.0], [0.0, 1.0, 1.0],
], dtype=np.float32)
mesh.faces = np.array([
    [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
    [0, 5, 1], [0, 4, 5], [1, 5, 6], [1, 6, 2],
    [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0],
], dtype=np.int32)
# 也可用 list 赋值 (不依赖 numpy):
#   mesh.vertices = [[0.0,0.0,0.0], [1.0,0.0,0.0], ...]
#   mesh.faces    = [[0,1,2], ...]

print("Mesh: vertices=%d faces=%d" % (len(mesh.vertices), len(mesh.faces)))

# 2. 手动构造轮廓点: (K, 3) float32, 对应 Pt3fVector (std::vector<Eigen::Vector3f>)
contour_points = np.array([
    [0.5, 0.0, 0.0], [1.0, 0.5, 0.0], [0.5, 1.0, 0.0], [0.0, 0.5, 0.0],
], dtype=np.float32)
# 或用 list: contour_points = [[0.5,0,0], [1,0.5,0], [0.5,1,0], [0,0.5,0]]

# 3. 加载并切割
cutter = cutmesh.MeshLibCutMesh()
cutter.load_from_mesh(mesh)
print("cutter faces:", cutter.get_face_count())

# 多输出: segment_by_contour(contour_points) -> (ok, [Mesh, ...])
ok, meshes = cutter.segment_by_contour(contour_points)
print("多输出: ok=%s  切出 %d 个子网格" % (ok, len(meshes)))
for i, m in enumerate(meshes):
    print("  [%d] vertices=%d faces=%d" % (i, len(m.vertices), len(m.faces)))
    # m.write_stl("output_%d.stl" % i)

# 单输出: segment_by_contour(contour_points, keep_left_side) -> (ok, Mesh)
ok, single_l = cutter.segment_by_contour(contour_points, keep_left_side=True)
print("单输出(左): ok=%s  vertices=%d faces=%d" % (ok, len(single_l.vertices), len(single_l.faces)))

ok, single_r = cutter.segment_by_contour(contour_points, keep_left_side=False)
print("单输出(右): ok=%s  vertices=%d faces=%d" % (ok, len(single_r.vertices), len(single_r.faces)))
```

赋值方式说明（三种等价，pybind11/eigen 自动转换）：

| 目标属性 | numpy 写法 | list 写法 | dtype |
|---|---|---|---|
| `mesh.vertices` | `np.array(N,3, float32)` | `[[x,y,z], ...]` | `float32`（`Vector3f`） |
| `mesh.faces` | `np.array(M,3, int32)` | `[[i,j,k], ...]` | `int32`（`Vector3i`） |
| `contour_points` | `np.array(K,3, float32)` | `[[x,y,z], ...]` | `float32`（`Pt3fVector`） |

> dtype 不匹配时自动转换（如 `float64`→`float32`）；形状必须为 `(N, 3)`。

