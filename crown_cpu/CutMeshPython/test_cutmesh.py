"""CutMesh Python 绑定示例 + 程序化接口 (随包分发, 自包含运行)。

用法: 三方自行切换到匹配版本的 Python 虚拟环境, 用 --lib_path 指定 cutmesh.so 所在目录
(cutmesh.so 的 RPATH=$ORIGIN/libs, .so 与 libs/ 必须同目录, 勿单独拆开)。

  # 命令行
  source .venv38/bin/activate
  python test_cutmesh.py --lib_path ./py38
  # 输出: output/0.stl, 1.stl (默认放脚本同级目录)

  # 三种独立运行模式 (可单独或组合使用)
  python test_cutmesh.py --lib_path ./py38 --test_cutmesh   # 完整切割流程, 输出 STL
  python test_cutmesh.py --lib_path ./py38 --test_api       # API 断言自测 (20 项)
  python test_cutmesh.py --lib_path ./py38 --test_demo      # API 用法演示 (讲解式)

  # 程序化调用
  from test_cutmesh import run_cutmesh_test, run_api_test, run_api_demo
  r = run_cutmesh_test(lib_path="./py38")        # 会把 lib_path 加入 sys.path 再 import

前提:
  - Linux x86_64, glibc >= 2.39
  - Python 版本需匹配 .so 的 ABI 标签 (py311=3.11.x, py38=3.8.x)
  - 已 pip install numpy (3.11 任意; 3.8 需 numpy<1.25)

运行时第三方 .so 靠模块 RPATH ($ORIGIN/libs) 自动加载,
libmlCutMesh.so 靠 RUNPATH($ORIGIN) 找同目录 libMRMesh.so,
无需 LD_LIBRARY_PATH。
"""
import argparse
import importlib
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

_LIB_PATH = None  # 由 _ensure_import() 记录, 供 run_cutmesh_test 默认值使用


def _ensure_import(lib_path):
    """把 lib_path 加入 sys.path 后 import cutmesh; 重复调用只 import 一次。"""
    global _LIB_PATH
    lib_path = lib_path or _LIB_PATH or os.path.join(_HERE, "py311")
    # lib_path 若为相对路径, 相对当前工作目录解析 (而非脚本所在目录 _HERE),
    # 这样从项目根 `python dist/test_cutmesh.py --lib_path ./dist/py38` 也能工作。
    abs_path = lib_path if os.path.isabs(lib_path) else os.path.abspath(lib_path)
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)
    if "cutmesh" not in sys.modules:
        import cutmesh  # noqa: F401  (注册到 sys.modules)
    _LIB_PATH = abs_path
    return importlib.import_module("cutmesh")


def run_cutmesh_test(lib_path=None, input_prefix="example/", out_dir=None, write_stl=True, verbose=True):
    """程序化调用: 跑完整切割流程, 返回结构化结果。

    参数:
        lib_path:      cutmesh.so 所在目录 (如 "./py38"); None 则用默认 py311
        input_prefix:  输入文件目录 (含 input_mesh.stl / input_curve.asc)
        out_dir:       输出 STL 目录; None 则默认放脚本同级 output/
        write_stl:     是否写出 STL 文件
        verbose:       是否打印进度

    返回 dict: { ok, input_mesh, contour_points, cutter_faces,
                 segment_ok, output_meshes, output_dir, error }
    """
    result = {
        "ok": False, "input_mesh": None, "contour_points": None,
        "cutter_faces": 0, "segment_ok": False, "output_meshes": [],
        "output_dir": None, "error": None,
    }

    def log(msg):
        if verbose:
            print(msg)

    try:
        cutmesh = _ensure_import(lib_path)  # 把 lib_path 加入 sys.path 后 import

        # 默认输入: 优先 dist/example/ (脚本同级), 找不到再尝试相对 cwd
        if not os.path.isdir(input_prefix):
            cand = os.path.join(_HERE, "example")
            if os.path.isdir(cand):
                input_prefix = cand + "/"

        mesh = cutmesh.Mesh()
        if not mesh.read_stl(input_prefix + "input_mesh.stl"):
            result["error"] = "bad readSTL: " + input_prefix + "input_mesh.stl"
            log(result["error"])
            return result
        result["input_mesh"] = mesh
        log("vertices: %d" % len(mesh.vertices))
        log("faces:    %d" % len(mesh.faces))

        points = cutmesh.MeshLibCutMesh.read_contour_from_asc(input_prefix + "input_curve.asc")
        result["contour_points"] = points
        log("contour points: %d" % len(points))

        cutter = cutmesh.MeshLibCutMesh()
        if not cutter.load_from_mesh(mesh):
            result["error"] = "loadFromMesh failed"
            log("loadFromMesh failed")
            return result
        result["cutter_faces"] = cutter.get_face_count()
        log("cutter faces: %d" % cutter.get_face_count())

        seg_ok, res_meshes = cutter.segment_by_contour(points)
        result["segment_ok"] = seg_ok
        result["output_meshes"] = res_meshes
        log("segmentByContour => %s  res.size = %d" % (seg_ok, len(res_meshes)))

        if not res_meshes:
            log("no result meshes, skip writing")
            result["ok"] = True
            return result

        # 输出默认放脚本同级目录 (_HERE)/output/
        if out_dir is None:
            out_dir = os.path.join(_HERE, "output")
        if write_stl:
            os.makedirs(out_dir, exist_ok=True)
            result["output_dir"] = out_dir
            log("output dir: %s" % out_dir)
            for i, m in enumerate(res_meshes):
                path = os.path.join(out_dir, str(i) + ".stl")
                w = m.write_stl(path)
                log("writeStl[%d] %s => %s  verts=%d faces=%d"
                    % (i, path, w, len(m.vertices), len(m.faces)))

        result["ok"] = True
        return result
    except Exception as e:
        result["error"] = str(e)
        if verbose:
            print("ERROR: %s" % e)
        return result


def run_api_test(lib_path=None, input_prefix="example/", verbose=True):
    """对 README API 参考中的每个接口做测试用例, 返回 (ok, passed, failed, details)。

    覆盖: Mesh 构造/属性/read_stl/write_stl; MeshLibCutMesh 构造/
    load_from_mesh/load_from_file/export_to_mesh/save_to_file/
    segment_by_contour(单/多输出)/segment_by_source_sink/
    get_vertex_count/get_face_count/read_contour_from_asc(静态)。
    """
    passed = []
    failed = []

    def check(name, cond, detail=""):
        (passed if cond else failed).append((name, detail))
        if verbose:
            print("[%s] %s%s" % ("PASS" if cond else "FAIL", name,
                                  (" — " + detail) if detail else ""))

    try:
        cutmesh = _ensure_import(lib_path)
    except Exception as e:
        if verbose:
            print("[FAIL] import cutmesh — %s" % e)
        return False, 0, 1, [("import cutmesh", str(e))]

    # 默认输入目录回退
    if not os.path.isdir(input_prefix):
        cand = os.path.join(_HERE, "example")
        if os.path.isdir(cand):
            input_prefix = cand + "/"
    stl = os.path.join(input_prefix, "input_mesh.stl")
    asc = os.path.join(input_prefix, "input_curve.asc")

    # ---- Mesh: 构造 ----
    mesh = cutmesh.Mesh()
    check("Mesh() 构造", isinstance(mesh, cutmesh.Mesh))

    # ---- Mesh: 属性 (空网格) ----
    check("Mesh.vertices 属性(空)", len(mesh.vertices) == 0)
    check("Mesh.faces 属性(空)", len(mesh.faces) == 0)

    # ---- Mesh: read_stl ----
    ok_read = mesh.read_stl(stl)
    check("Mesh.read_stl", ok_read, "verts=%d faces=%d" % (len(mesh.vertices), len(mesh.faces)))

    # ---- Mesh: 属性 (非空) ----
    check("Mesh.vertices 属性(非空)", len(mesh.vertices) > 0)
    check("Mesh.faces 属性(非空)", len(mesh.faces) > 0)

    # ---- MeshLibCutMesh.read_contour_from_asc (静态) ----
    points = cutmesh.MeshLibCutMesh.read_contour_from_asc(asc)
    check("MeshLibCutMesh.read_contour_from_asc(静态)", len(points) > 0, "points=%d" % len(points))

    # ---- MeshLibCutMesh: 构造 ----
    cutter = cutmesh.MeshLibCutMesh()
    check("MeshLibCutMesh() 构造", isinstance(cutter, cutmesh.MeshLibCutMesh))

    # ---- MeshLibCutMesh: load_from_mesh ----
    ok_load = cutter.load_from_mesh(mesh)
    check("MeshLibCutMesh.load_from_mesh", ok_load)

    # ---- MeshLibCutMesh: get_vertex_count / get_face_count ----
    vc = cutter.get_vertex_count()
    fc = cutter.get_face_count()
    check("MeshLibCutMesh.get_vertex_count", vc == len(mesh.vertices), "vc=%d" % vc)
    check("MeshLibCutMesh.get_face_count", fc == len(mesh.faces), "fc=%d" % fc)

    # ---- MeshLibCutMesh: segment_by_contour (多输出) ----
    ok_seg, meshes = cutter.segment_by_contour(points)
    check("MeshLibCutMesh.segment_by_contour(多输出)", ok_seg and len(meshes) >= 1,
          "ok=%s count=%d" % (ok_seg, len(meshes)))

    # ---- MeshLibCutMesh: segment_by_contour (单输出) ----
    ok_seg1, out_mesh = cutter.segment_by_contour(points, keep_left_side=True)
    check("MeshLibCutMesh.segment_by_contour(单输出)", ok_seg1,
          "verts=%d faces=%d" % (len(out_mesh.vertices), len(out_mesh.faces)))

    # ---- Mesh: write_stl (用切出的子网格) ----
    if meshes:
        tmp_out = os.path.join(_HERE, "output", "_api_selftest.stl")
        os.makedirs(os.path.dirname(tmp_out), exist_ok=True)
        w_ok = meshes[0].write_stl(tmp_out)
        check("Mesh.write_stl", w_ok, "path=%s" % tmp_out)
        if os.path.isfile(tmp_out):
            os.remove(tmp_out)

    # ---- MeshLibCutMesh: export_to_mesh ----
    exported = cutmesh.Mesh()
    ok_exp = cutter.export_to_mesh(exported)
    check("MeshLibCutMesh.export_to_mesh", ok_exp,
          "verts=%d faces=%d" % (len(exported.vertices), len(exported.faces)))

    # ---- MeshLibCutMesh: load_from_file ----
    cutter2 = cutmesh.MeshLibCutMesh()
    ok_lf = cutter2.load_from_file(stl)
    check("MeshLibCutMesh.load_from_file", ok_lf, "faces=%d" % cutter2.get_face_count())

    # ---- MeshLibCutMesh: save_to_file ----
    tmp_save = os.path.join(_HERE, "output", "_api_selftest_save.stl")
    os.makedirs(os.path.dirname(tmp_save), exist_ok=True)
    ok_sv = cutter2.save_to_file(tmp_save)
    check("MeshLibCutMesh.save_to_file", ok_sv, "path=%s" % tmp_save)
    if os.path.isfile(tmp_save):
        os.remove(tmp_save)

    # ---- MeshLibCutMesh: segment_by_source_sink ----
    # 用前两个面作 source, 最后两个面作 sink (仅验证可调用与返回形态)
    ok_ss, seg_mesh = cutter.segment_by_source_sink([0, 1], [fc - 1, fc - 2])
    check("MeshLibCutMesh.segment_by_source_sink", ok_ss is not None,
          "ok=%s verts=%d" % (ok_ss, len(seg_mesh.vertices)))

    # ---- vertices/faces 可作为 numpy 数组读取 (若装了 numpy) ----
    try:
        import numpy as _np
        v_arr = _np.asarray(mesh.vertices)
        f_arr = _np.asarray(mesh.faces)
        check("Mesh.vertices 可转 numpy", v_arr.ndim == 2 and v_arr.shape[1] == 3,
              "shape=%s" % (v_arr.shape,))
        check("Mesh.faces 可转 numpy", f_arr.ndim == 2 and f_arr.shape[1] == 3,
              "shape=%s" % (f_arr.shape,))
    except ImportError:
        check("numpy 互转(跳过-未装numpy)", True, "numpy 未安装, 跳过")

    ok = len(failed) == 0
    return ok, len(passed), len(failed), failed


def run_api_demo(lib_path=None, input_prefix="example/", verbose=True):
    """详细演示每个 API 的使用例子 (讲解式, 打印中间数据)。返回 (ok, info)。"""
    info = {"error": None}

    def section(title):
        if verbose:
            print("\n========== %s ==========" % title)

    def show(label, val):
        if verbose:
            print("  %s: %s" % (label, val))

    try:
        cutmesh = _ensure_import(lib_path)
    except Exception as e:
        info["error"] = "import cutmesh: %s" % e
        if verbose:
            print("ERROR: %s" % info["error"])
        return False, info

    # 输入目录回退
    if not os.path.isdir(input_prefix):
        cand = os.path.join(_HERE, "example")
        if os.path.isdir(cand):
            input_prefix = cand + "/"
    stl = os.path.join(input_prefix, "input_mesh.stl")
    asc = os.path.join(input_prefix, "input_curve.asc")
    out_dir = os.path.join(_HERE, "output")

    try:
        import numpy as np
        has_np = True
    except ImportError:
        has_np = False

    try:
        # ---- 1. Mesh 构造与属性 ----
        section("1. Mesh 构造与属性")
        m = cutmesh.Mesh()
        show("类型", type(m).__name__)
        show("空 vertices", len(m.vertices))
        show("空 faces", len(m.faces))

        # ---- 2. Mesh.read_stl ----
        section("2. Mesh.read_stl 读取 STL")
        ok = m.read_stl(stl)
        show("返回", ok)
        show("vertices", len(m.vertices))
        show("faces", len(m.faces))
        info["mesh_v"] = len(m.vertices); info["mesh_f"] = len(m.faces)

        # ---- 3. vertices/faces 转 numpy ----
        section("3. vertices/faces 转 numpy 数组")
        if has_np:
            v = np.asarray(m.vertices)
            f = np.asarray(m.faces)
            show("vertices.shape", v.shape)
            show("faces.shape", f.shape)
            show("首顶点", v[0])
            show("首面索引", f[0])
            show("x 范围", (float(v[:,0].min()), float(v[:,0].max())))
        else:
            show("numpy", "未安装, 跳过")

        # ---- 4. read_contour_from_asc (静态) ----
        section("4. MeshLibCutMesh.read_contour_from_asc (静态)")
        pts = cutmesh.MeshLibCutMesh.read_contour_from_asc(asc)
        show("轮廓点数", len(pts))
        show("首点", list(pts[0]) if pts else "无")
        if has_np:
            show("pts.shape", np.asarray(pts).shape)
        info["contour_n"] = len(pts)

        # ---- 5. 构造 + load_from_mesh ----
        section("5. MeshLibCutMesh 构造 + load_from_mesh")
        cutter = cutmesh.MeshLibCutMesh()
        show("load_from_mesh", cutter.load_from_mesh(m))

        # ---- 6. get_vertex_count / get_face_count ----
        section("6. get_vertex_count / get_face_count")
        show("vertex_count", cutter.get_vertex_count())
        show("face_count", cutter.get_face_count())

        # ---- 7. segment_by_contour (多输出) ----
        section("7. segment_by_contour (多输出)")
        ok, meshes = cutter.segment_by_contour(pts)
        show("ok", ok); show("子网格数", len(meshes))
        for i, mm in enumerate(meshes):
            show("  [%d]" % i, "verts=%d faces=%d" % (len(mm.vertices), len(mm.faces)))
        info["seg_multi"] = len(meshes)

        # ---- 8. segment_by_contour (单输出, keep_left_side 必填) ----
        section("8. segment_by_contour (单输出, keep_left_side)")
        ok_l, ml = cutter.segment_by_contour(pts, keep_left_side=True)
        show("左侧 ok", ok_l)
        show("左侧", "verts=%d faces=%d" % (len(ml.vertices), len(ml.faces)))
        ok_r, mr = cutter.segment_by_contour(pts, keep_left_side=False)
        show("右侧 ok", ok_r)
        show("右侧", "verts=%d faces=%d" % (len(mr.vertices), len(mr.faces)))
        show("左+右 顶点", len(ml.vertices) + len(mr.vertices))

        # ---- 9. segment_by_source_sink ----
        section("9. segment_by_source_sink")
        fc = cutter.get_face_count()
        ok, seg = cutter.segment_by_source_sink([0, 1, 2], [fc-1, fc-2])
        show("ok", ok)
        show("结果", "verts=%d faces=%d" % (len(seg.vertices), len(seg.faces)))

        # ---- 10. export_to_mesh ----
        section("10. export_to_mesh")
        exported = cutmesh.Mesh()
        show("ok", cutter.export_to_mesh(exported))
        show("导出", "verts=%d faces=%d" % (len(exported.vertices), len(exported.faces)))
        info["export_v"] = len(exported.vertices)

        # ---- 11. load_from_file ----
        section("11. load_from_file")
        c2 = cutmesh.MeshLibCutMesh()
        show("ok", c2.load_from_file(stl))
        show("face_count", c2.get_face_count())

        # ---- 12. save_to_file ----
        section("12. save_to_file")
        os.makedirs(out_dir, exist_ok=True)
        save_path = os.path.join(out_dir, "_demo_save.stl")
        show("ok", c2.save_to_file(save_path))
        show("保存到", save_path)

        # ---- 13. Mesh.write_stl (二进制 vs ASCII) ----
        section("13. Mesh.write_stl (二进制 / ASCII)")
        if meshes:
            bp = os.path.join(out_dir, "_demo_bin.stl")
            ap_ = os.path.join(out_dir, "_demo_asc.stl")
            meshes[0].write_stl(bp, use_binary=True)
            meshes[0].write_stl(ap_, use_binary=False)
            show("二进制大小", os.path.getsize(bp))
            show("ASCII大小", os.path.getsize(ap_))
            with open(ap_) as fh:
                show("ASCII 首行", fh.readline()[:50])
            show("二进制", bp)
            show("ASCII", ap_)

        # ---- 14. 手动构造 Mesh (list 赋值) ----
        section("14. 手动构造 Mesh (list 赋值 vertices/faces)")
        hand = cutmesh.Mesh()
        hand.vertices = [[0.0,0.0,0.0],[1.0,0.0,0.0],[0.0,1.0,0.0]]
        hand.faces = [[0,1,2]]
        show("手构 verts", len(hand.vertices))
        show("手构 faces", len(hand.faces))
        hp = os.path.join(out_dir, "_demo_hand.stl")
        hand.write_stl(hp)
        rb = cutmesh.Mesh(); rb.read_stl(hp)
        show("写出+读回 verts", len(rb.vertices))
        show("手构 STL", hp)

        info["ok"] = True
        return True, info
    except Exception as e:
        info["error"] = str(e)
        if verbose:
            print("ERROR: %s" % e)
        return False, info


def main():
    ap = argparse.ArgumentParser(description="CutMesh 切割流程示例")
    ap.add_argument("--lib_path", default=None,
                    help="cutmesh.so 所在目录, 如 ./py311 或 ./py38 (默认 ./py311)")
    ap.add_argument("--input", default="example/", help="输入文件目录")
    ap.add_argument("--out", default=None, help="输出 STL 目录 (默认 脚本同级 output/)")
    ap.add_argument("--test_cutmesh", action="store_true",
                    help="运行完整切割流程 (run_cutmesh_test), 输出 STL")
    ap.add_argument("--test_api", action="store_true",
                    help="运行 API 断言自测 (run_api_test), 20 项接口检查")
    ap.add_argument("--test_demo", action="store_true",
                    help="运行 API 用法演示 (run_api_demo), 打印各接口详细用法")
    args = ap.parse_args()

    # 相对路径在 chdir 之前解析为绝对 (相对当前工作目录),
    # 这样从项目根 `python dist/test_cutmesh.py --lib_path ./dist/py38` 也能工作。
    # 注意: input_prefix 默认 "example/" 带尾斜杠, abspath 会去掉, 需补回。
    def _abs(p):
        if p is None or os.path.isabs(p):
            return p
        ap = os.path.abspath(p)
        if p.endswith("/") or p.endswith(os.sep):
            ap = ap.rstrip(os.sep) + os.sep
        return ap
    lib_path = _abs(args.lib_path)
    input_prefix = _abs(args.input)
    out_dir = _abs(args.out)

    # 切到脚本所在目录 (dist), 使 example/ 可见, 输出也落在 dist 下
    os.chdir(_HERE)

    # 任一指定即进入对应分支; 默认 (无参数) 走完整流程
    run_full = (not (args.test_cutmesh or args.test_api or args.test_demo)) or args.test_cutmesh

    overall_ok = True

    if args.test_api:
        ok, npass, nfail, fails = run_api_test(lib_path=lib_path, input_prefix=input_prefix)
        print("\nAPI 自测: %d passed, %d failed => %s"
              % (npass, nfail, "OK" if ok else "FAILED"))
        overall_ok = overall_ok and ok

    if args.test_demo:
        ok, info = run_api_demo(lib_path=lib_path, input_prefix=input_prefix)
        print("\nAPI 演示: %s" % ("OK" if ok else "FAILED: %s" % info.get("error")))
        overall_ok = overall_ok and ok

    if run_full:
        r = run_cutmesh_test(lib_path=lib_path, input_prefix=input_prefix, out_dir=out_dir)
        overall_ok = overall_ok and r["ok"]

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
