import base64
import json
import traceback
import requests
import DracoPy
import MQCompressPy
import numpy as np
import trimesh

from input_compat import file_name2template_name, load_input_info, upload_result
from crown_cpu import stdcrown


def read_mesh_bytes(buffer):
    a = base64.b64decode(buffer)
    mesh_object = DracoPy.decode_buffer_to_mesh(a)
    V = np.array(mesh_object.points).astype(np.float32).reshape(-1, 3)
    F = np.array(mesh_object.faces).astype(np.int64).reshape(-1, 3)
    return trimesh.Trimesh(V, F)


def write_mesh_bytes(mesh, colors=None, preserve_order=False):
    if mesh:
        # 设置 Draco 编码选项
        encoding_test = DracoPy.encode_mesh_to_buffer(
            mesh.vertices,
            mesh.faces,
            preserve_order=preserve_order,
            quantization_bits=14,
            compression_level=10,
            colors=colors,
        )
        b64_bytes = base64.b64encode(encoding_test)
        b64_str = b64_bytes.decode("utf-8")
        return b64_str
    else:
        return ""


def write_drc(drc, file):
    with open(file, "wb") as test_file:
        test_file.write(base64.b64decode(drc))


def compress_drc(mesh, points_id=[]):
    vert_flags = np.zeros(len(mesh.vertices), dtype=np.uint8)
    vert_flags[points_id] = 1
    # trimesh.PointCloud(mesh.vertices[points_id]).export('p.ply')
    in_mesh = MQCompressPy.MQC_Mesh()
    in_mesh.verts = MQCompressPy.VerticeArray(mesh.vertices)
    in_mesh.faces = MQCompressPy.FaceArray(mesh.faces)
    in_vert_flags = MQCompressPy.VerticeFlag_UINT8(
        np.array(vert_flags).astype(np.uint8)
    )
    compressed_data, error_code = MQCompressPy.compressMesh_UINT8(
        in_mesh, in_vert_flags
    )
    # with open('mesh.drc', 'wb') as f:
    #     f.write(compressed_data)
    if error_code == 0:
        b64_bytes = base64.b64encode(compressed_data)
        b64_str = b64_bytes.decode("utf-8")
        return b64_str
    else:
        assert "drc compress error"


def matrix2matrix(crown_rot_matirx):
    ai_matrix = np.eye(4)  # 创建一个单位矩阵作为变换矩阵的初始值
    ai_matrix[:3, :3] = crown_rot_matirx  # 复制旋转矩阵的前三列到变换矩阵的前三列
    ai_matrix[:, 3] = [0, 0, 0, 1]
    return ai_matrix


def get_kps_and_crowns(miss_id, kps_info, seg_crowns):
    keys_1_2_up = [
        "occc",
        "glp",
        "gbp",
        "occm",
        "occd",
        "mrm",
        "mrd",
        "lmc",
        "ldc",
        "bmc",
        "bdc",
    ]
    keys_1_2_low = ["occc", "glp", "gbp", "occm", "occd", "lmc", "ldc", "bmc", "bdc"]
    keys_3 = ["occc", "glp", "gbp", "occm", "occd", "lmc", "ldc", "bmc", "bdc"]
    keys_4_5 = [
        "occc",
        "glp",
        "gbp",
        "fc",
        "nfc",
        "occm",
        "occd",
        "mrm",
        "mrd",
        "lmc",
        "ldc",
        "bmc",
        "bdc",
    ]
    keys_6_7 = [
        "occc",
        "glp",
        "gbp",
        "fcm",
        "fcd",
        "nfcm",
        "nfcd",
        "mrm",
        "mrd",
        "obp",
        "lmc",
        "ldc",
        "bmc",
        "bdc",
    ]

    if str(miss_id - 1) in kps_info.keys():
        pt1_dic = kps_info[str(miss_id - 1)]
    else:
        pt1_dic = {}
    if str(miss_id + 1) in kps_info.keys():
        pt2_dic = kps_info[str(miss_id + 1)]
    else:
        pt2_dic = {}
    pt1 = []
    pt2 = []
    if miss_id in [14, 24, 34, 44]:
        if len(pt1_dic):
            for key in keys_3:
                pt1.append(pt1_dic[key])
        if len(pt2_dic):
            for key in keys_4_5:
                pt2.append(pt2_dic[key])
    elif miss_id in [15, 25, 35, 45, 16, 26, 36, 46]:
        if len(pt1_dic):
            for key in keys_4_5:
                pt1.append(pt1_dic[key])
        if len(pt2_dic):
            for key in keys_6_7:
                pt2.append(pt2_dic[key])
    elif miss_id in [17, 27, 37, 47]:
        if len(pt1_dic):
            for key in keys_6_7:
                pt1.append(pt1_dic[key])

    kps = {"arch": {"teeth_keypoints": {}}}
    all_other_crowns = {}
    for i in list(kps_info.keys()):
        keys = {}
        if i[-1] in ["1", "2"]:
            if i[0] in ["1", "2"]:
                for key in keys_1_2_up:
                    keys[key] = kps_info[i][key]
            else:
                for key in keys_1_2_low:
                    keys[key] = kps_info[i][key]
        elif i[-1] in ["3"]:
            for key in keys_3:
                keys[key] = kps_info[i][key]
        elif i[-1] in ["4", "5"]:
            for key in keys_4_5:
                keys[key] = kps_info[i][key]
        elif i[-1] in ["6", "7"]:
            for key in keys_6_7:
                keys[key] = kps_info[i][key]
        kps["arch"]["teeth_keypoints"][i] = keys

        all_other_crowns[i] = seg_crowns.get(i)
    return kps, all_other_crowns, pt1, pt2


# ==================== 输入准备策略 ====================


def _normalize_input_info(event):
    """归一化 stdcrown 入口的公共兼容字段。"""
    input_info = dict(event)

    prep_tid = input_info.get("prep_tid", [])
    if prep_tid is None:
        prep_tid = []
    input_info["prep_tid"] = [int(x) for x in prep_tid]

    return input_info


def _prepare_input_legacy(input_info):
    """旧版本输入数据准备"""
    if input_info.get("pred_filestem_name"):
        input_info["template_name"] = file_name2template_name(
            input_info.get("pred_filestem_name")
        )

    if input_info.get("multi_restoration"):
        return _prepare_multi_restoration_legacy(input_info)
    else:
        return _prepare_single_restoration(input_info)


def _prepare_input_new(input_info):
    """新版本输入数据准备 (new_placement=True)"""
    if input_info.get("multi_restoration"):
        return _prepare_multi_restoration_new(input_info)
    else:
        return _prepare_single_restoration(input_info)


def _prepare_multi_restoration_common(input_info):
    """多修复模式的公共字段准备。"""
    input_info["ai_matrix"] = matrix2matrix(input_info["crown_rot"])

    # 提取牙弓数据
    kps_info, seg_crowns = _extract_arch_data(
        input_info, input_info["beiya_id"][0] in ["1", "2"]
    )

    # 处理 mirror 或 preop 逻辑
    arch_seg_crowns = _process_mirror_or_preop(input_info)

    # 获取关键点与牙冠
    (
        input_info["kps"],
        input_info["all_other_crowns"],
        input_info["pt1"],
        input_info["pt2"],
    ) = get_kps_and_crowns(int(input_info["beiya_id"]), kps_info, seg_crowns)

    input_info["arch_seg_crowns"] = arch_seg_crowns
    input_info["mesh_beiya"] = input_info["prep"]
    input_info["mesh1"] = input_info["closer"]
    input_info["mesh2"] = input_info["further"]

    return input_info


def _prepare_multi_restoration_new(input_info):
    """多修复模式数据准备（new_placement=True）。"""
    input_info["vox_points"] = input_info["xyz_ori"]

    return _prepare_multi_restoration_common(input_info)


def _prepare_multi_restoration_legacy(input_info):
    """多修复模式数据准备（legacy）。"""
    return _prepare_multi_restoration_common(input_info)


def _prepare_single_restoration_meshes(input_info):
    """单修复模式的网格变换准备。"""
    input_info["ai_matrix"] = matrix2matrix(input_info["crown_rot_matirx"])
    transforms = [
        input_info["ai_matrix"],
        input_info["new_transform_list"][2],
        input_info["new_transform_list"][0],
        input_info["new_transform_list"][1],
    ]

    mesh_keys = ["mesh_beiya", "mesh_upper", "mesh_lower", "mesh1", "mesh2"]
    for key in mesh_keys:
        if key in input_info:
            input_info[key] = _transform_mesh(input_info[key], transforms)

    return input_info


def _prepare_single_restoration(input_info):
    """单修复模式数据准备。"""
    try:
        input_info = _prepare_single_restoration_meshes(input_info)
    except Exception:
        pass

    return input_info


def _extract_arch_data(input_info, is_upper):
    """提取牙弓关键点与分割数据"""
    kps_info = {}
    seg_crowns = {}
    arch = "upper_arch" if is_upper else "lower_arch"

    for _, v in input_info["mesh_kps"][arch].items():
        kps_info = {**kps_info, **v}
    for _, v in input_info["all_teeth_seg"][arch].items():
        seg_crowns = {**seg_crowns, **v}

    return kps_info, seg_crowns


def _process_mirror_or_preop(input_info):
    """处理 mirror 或 preop 逻辑"""
    arch_seg_crowns = {}

    if input_info.get("preop_or_mirror") == "mirror":
        is_upper = input_info["mirror_id"][0] in ["1", "2"]
        arch = "upper_arch" if is_upper else "lower_arch"
        for _, v in input_info["all_teeth_seg"][arch].items():
            arch_seg_crowns = {**arch_seg_crowns, **v}
        input_info["vox_points"] = input_info["xyz_ori"]
    else:
        preop_to_postop = input_info.get("preop_to_postop")
        if preop_to_postop is not None:
            is_upper = input_info["beiya_id"][0] in ["1", "2"]
            matrix_key = "upper_matrix" if is_upper else "lower_matrix"
            input_info["preop_matrix"] = preop_to_postop.get(matrix_key, np.eye(4))

    return arch_seg_crowns


def _transform_mesh(mesh_bytes, transforms):
    """应用变换到网格"""
    mesh = read_mesh_bytes(mesh_bytes)
    for t in transforms:
        mesh.apply_transform(np.linalg.pinv(t))
    return write_mesh_bytes(mesh)


# ==================== 颜色编码处理 ====================


def _encode_point_colors(mesh, backup=False):
    """编码点颜色信息"""
    cpu_points_info = {}
    cpu_colors_info = {}

    target_mesh = mesh.copy() if backup else mesh
    colors = np.zeros_like(target_mesh.vertices, dtype=np.uint8)

    points_keys = [x for x in vars(mesh) if x not in vars(trimesh.Trimesh())][2:]
    color_n = 0

    for key in points_keys:
        points = getattr(mesh, key, None)
        if not points:
            continue

        color_list = []
        for p_n, p_idx in enumerate(points.idx):
            color_r, color_g, color_b = colors[p_idx]
            color_str = (
                bin(color_r)[2:].zfill(8)
                + bin(color_g)[2:].zfill(8)
                + bin(color_b)[2:].zfill(8)
            )
            color_str = color_str[:color_n] + "1" + color_str[color_n + 1 :]

            if key == "ad_points":
                color_str = color_str[:-8] + bin(p_n)[2:].zfill(4) + color_str[-4:]
            elif key == "cross_points":
                color_str = color_str[:-4] + bin(p_n)[2:].zfill(4)

            colors[p_idx] = [
                int(color_str[:8], 2),
                int(color_str[8:16], 2),
                int(color_str[16:], 2),
            ]

            if colors[p_idx].tolist() not in color_list:
                color_list.append(colors[p_idx].tolist())

        cpu_colors_info[key] = color_list
        cpu_points_info[key] = points.pt.tolist()
        color_n += 1

    return cpu_points_info, cpu_colors_info, colors


# ==================== 结果构建策略 ====================


def _build_result_legacy(input_info, std_out):
    """旧版本结果构建"""
    # 编码颜色
    cpu_points_info, cpu_colors_info, colors = _encode_point_colors(
        std_out.mesh, backup=False
    )
    std_out.mesh_backup = std_out.mesh.copy()

    cpu_points_info_backup, cpu_colors_info_backup, colors_backup = (
        _encode_point_colors(std_out.mesh_backup, backup=True)
    )

    points_oppo_id = std_out.points_oppo_id

    # 序列化网格
    meshes = _serialize_meshes(std_out, colors, colors_backup)

    # 构建 JSON
    cpu_std_json = _build_cpu_std_json(
        input_info, std_out, meshes, cpu_points_info, cpu_colors_info, points_oppo_id
    )

    # 多修复模式额外处理
    if input_info.get("multi_restoration"):
        meshes["standard"], meshes["inner"], meshes["standard_backup"] = (
            _apply_multi_restoration_transforms(
                input_info, std_out, colors, colors_backup
            )
        )

    return {
        "cpu_std_json": cpu_std_json,
        "standard": meshes["standard"],
        "inner": meshes["inner"],
        "standard_backup": meshes["standard_backup"],
    }


def _build_result_new(input_info, std_out):
    """新版本结果构建 (new_placement=True)"""
    # TODO: 在这里实现新版本的结果构建逻辑
    # 目前先复用旧版本逻辑，后续可替换
    return _build_result_legacy(input_info, std_out)


def _serialize_meshes(std_out, colors, colors_backup):
    """序列化所有网格"""
    return {
        "standard": write_mesh_bytes(std_out.mesh, colors),
        "standard_backup": write_mesh_bytes(std_out.mesh_backup, colors_backup),
        "closer": write_mesh_bytes(std_out.mesh1),
        "further": write_mesh_bytes(std_out.mesh2),
        "inner": write_mesh_bytes(std_out.mesh_beiya),
        "mesh_upper": write_mesh_bytes(std_out.mesh_upper),
        "mesh_lower": write_mesh_bytes(std_out.mesh_lower),
        "mesh_jaw": write_mesh_bytes(std_out.mesh_jaw),
        "mesh_oppo": write_mesh_bytes(std_out.mesh_oppo),
    }


def _build_cpu_std_json(
    input_info, std_out, meshes, cpu_points_info, cpu_colors_info, points_oppo_id
):
    """构建 cpu_std_json"""
    base_json = {
        "closer": meshes["closer"],
        "further": meshes["further"],
        "mesh_upper": meshes["mesh_upper"],
        "mesh_lower": meshes["mesh_lower"],
        "mesh_jaw": meshes["mesh_jaw"],
        "mesh_oppo": meshes["mesh_oppo"],
        "beiya_id": std_out.miss_id,
        "is_single": std_out.is_single,
        "template_name": std_out.template_name,
        "cpu_points_info": cpu_points_info,
        "cpu_colors_info": cpu_colors_info,
        "points_oppo_id": points_oppo_id,
        "xyz_ori": input_info.get("xyz_ori"),
    }
    use_new_placement = input_info.get("new_placement", False)

    if input_info.get("multi_restoration"):
        if use_new_placement:
            base_json.update(
                {
                    "rot_matrix": std_out.new_transform_list,
                    "ai_matrix": input_info["ai_matrix"].tolist(),
                    "preop_or_mirror": input_info.get("preop_or_mirror"),
                    "all_other_crowns": input_info.get("all_other_crowns"),
                    "prep_tid": input_info.get("prep_tid"),
                }
            )
        else:
            base_json.update(
                {
                    "rot_matrix": std_out.new_transform_list,
                    "ai_matrix": input_info["ai_matrix"].tolist(),
                    "std_crown": input_info.get("std_crown"),
                    "preop_or_mirror": input_info.get("preop_or_mirror"),
                }
            )

    return base_json


def _apply_multi_restoration_transforms(input_info, std_out, colors, colors_backup):
    """应用多修复模式变换"""
    transforms = [
        np.linalg.pinv(input_info["ai_matrix"]),
        np.linalg.pinv(std_out.new_transform_list[2]),
        np.linalg.pinv(std_out.new_transform_list[0]),
        np.linalg.pinv(std_out.new_transform_list[1]),
    ]

    # 变换主网格
    target_mesh = std_out.mesh_ if std_out.preop_or_mirror else std_out.mesh
    for t in transforms:
        target_mesh.apply_transform(t)
    standard = write_mesh_bytes(
        target_mesh, None if std_out.preop_or_mirror else colors
    )

    # 变换 beiya 网格
    for t in transforms:
        std_out.mesh_beiya.apply_transform(t)
    mesh_beiya = write_mesh_bytes(std_out.mesh_beiya)

    # 变换 backup 网格
    for t in transforms:
        std_out.mesh_backup.apply_transform(t)
    mesh_backup = write_mesh_bytes(std_out.mesh_backup, colors_backup)

    return standard, mesh_beiya, mesh_backup


# ==================== 主入口 ====================


def handler(event, context=None):
    print("receive case")
    try:
        input_info = load_input_info(event, requests)
        # input_info["new_placement"] = True
        input_info = _normalize_input_info(input_info)
        use_new_placement = input_info.get("new_placement", False)

        # 1. 数据准备阶段
        if use_new_placement:
            input_info = _prepare_input_new(input_info)
        else:
            input_info = _prepare_input_legacy(input_info)

        # 2. 核心处理
        print("job_id", input_info.get("job_id"))
        print("start AI_Crown_CPU_Std ..")
        std_out = stdcrown(input_info)

        # 3. 结果构建阶段
        if use_new_placement:
            std_json = _build_result_new(input_info, std_out)
        else:
            std_json = _build_result_legacy(input_info, std_out)

        print("success stdcrown")
        if event.get("target_url"):
            upload_response = upload_result(
                event.get("target_url"), std_json, requests
            )
            print(upload_response.status_code)
            return {"Msg": {"data": "result saved to target url"}, "Code": 200, "State": "Success"}
        return {"Msg": {"data": std_json}, "Code": 200, "State": "Success"}

    except Exception as _:
        res = {"Msg": traceback.format_exc(), "Code": 203, "State": "Failure"}
        traceback.print_exc()
        return res


if __name__ == "__main__":
    pass
