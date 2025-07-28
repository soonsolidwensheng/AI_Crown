import base64
import json
import traceback
import DracoPy
import MQCompressPy
import numpy as np
import trimesh

from crown_cpu import stdcrown


def read_mesh_bytes(buffer):
    a = base64.b64decode(buffer)
    mesh_object = DracoPy.decode_buffer_to_mesh(a)
    V = np.array(mesh_object.points).astype(np.float32).reshape(-1, 3)
    F = np.array(mesh_object.faces).astype(np.int64).reshape(-1, 3)
    return trimesh.Trimesh(V, F)


def write_mesh_bytes(mesh, colors=None, preserve_order=False):
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


def file_name2template_name(file_name):
    s = file_name.split("_")[0]
    f2t = {
        "CSv1": "Cyber Standard v1",
        "GSv1": "Generic Standard v1",
        "Mv1": "Mature v1",
        "rev1": "st_tooth",
        "SSv1": "Soft Standard v1",
        "Yv1": "Youth v1",
    }
    return f2t[s]


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

    kps = {}
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
        kps[i] = keys

        all_other_crowns[i] = seg_crowns.get(i)
    return kps, all_other_crowns, pt1, pt2


def handler(event, context):
    print("receive case")
    try:
        input_info = event
        if input_info.get("multi_restoration"):
            input_info["ai_matrix"] = matrix2matrix(input_info["crown_rot"])
            kps_info = {}
            for k, v in input_info["mesh_kps"].items():
                kps_info = {**kps_info, **v["teeth_keypoints"]}
            seg_crowns = {}
            for k, v in input_info["all_teeth_seg"].items():
                seg_crowns = {**seg_crowns, **v["teeth_crowns"]}
            (
                input_info["kps"],
                input_info["all_other_crowns"],
                input_info["pt1"],
                input_info["pt2"],
            ) = get_kps_and_crowns(
                int(input_info["beiya_id"]),
                kps_info,
                seg_crowns,
            )
            input_info["mesh_beiya"] = input_info["prep"]
            input_info["mesh1"] = input_info["closer"]
            input_info["mesh2"] = input_info["further"]
            if input_info.get("pred_filestem_name"):
                input_info["template_name"] = file_name2template_name(
                    input_info.get("pred_filestem_name")
                )

        else:
            try:
                input_info["ai_matrix"] = matrix2matrix(input_info["crown_rot_matirx"])
                new_transform = input_info["new_transform_list"]
                mesh_beiya = input_info["mesh_beiya"]
                mesh_beiya = read_mesh_bytes(mesh_beiya)
                mesh_beiya.apply_transform(np.linalg.pinv(input_info["ai_matrix"]))
                mesh_beiya.apply_transform(np.linalg.pinv(new_transform[2]))
                mesh_beiya.apply_transform(np.linalg.pinv(new_transform[0]))
                mesh_beiya.apply_transform(np.linalg.pinv(new_transform[1]))
                mesh_beiya = write_mesh_bytes(mesh_beiya)
                input_info["mesh_beiya"] = mesh_beiya
                mesh_upper = input_info["mesh_upper"]
                mesh_upper = read_mesh_bytes(mesh_upper)
                mesh_upper.apply_transform(np.linalg.pinv(input_info["ai_matrix"]))
                mesh_upper.apply_transform(np.linalg.pinv(new_transform[2]))
                mesh_upper.apply_transform(np.linalg.pinv(new_transform[0]))
                mesh_upper.apply_transform(np.linalg.pinv(new_transform[1]))
                mesh_upper = write_mesh_bytes(mesh_upper)
                input_info["mesh_upper"] = mesh_upper
                mesh_lower = input_info["mesh_lower"]
                mesh_lower = read_mesh_bytes(mesh_lower)
                mesh_lower.apply_transform(np.linalg.pinv(input_info["ai_matrix"]))
                mesh_lower.apply_transform(np.linalg.pinv(new_transform[2]))
                mesh_lower.apply_transform(np.linalg.pinv(new_transform[0]))
                mesh_lower.apply_transform(np.linalg.pinv(new_transform[1]))
                mesh_lower = write_mesh_bytes(mesh_lower)
                input_info["mesh_lower"] = mesh_lower
                mesh1 = input_info["mesh1"]
                mesh1 = read_mesh_bytes(mesh1)
                mesh1.apply_transform(np.linalg.pinv(input_info["ai_matrix"]))
                mesh1.apply_transform(np.linalg.pinv(new_transform[2]))
                mesh1.apply_transform(np.linalg.pinv(new_transform[0]))
                mesh1.apply_transform(np.linalg.pinv(new_transform[1]))
                mesh1 = write_mesh_bytes(mesh1)
                input_info["mesh1"] = mesh1
                mesh2 = input_info["mesh2"]
                mesh2 = read_mesh_bytes(mesh2)
                mesh2.apply_transform(np.linalg.pinv(input_info["ai_matrix"]))
                mesh2.apply_transform(np.linalg.pinv(new_transform[2]))
                mesh2.apply_transform(np.linalg.pinv(new_transform[0]))
                mesh2.apply_transform(np.linalg.pinv(new_transform[1]))
                mesh2 = write_mesh_bytes(mesh2)
                input_info["mesh2"] = mesh2
            except Exception:
                pass
            print("pred_filestem_name", input_info.get("pred_filestem_name"))
            if input_info.get("pred_filestem_name"):
                input_info["template_name"] = file_name2template_name(
                    input_info.get("pred_filestem_name")
                )
        print("template_name", input_info.get("template_name"))
        print("job_id", input_info.get("job_id"))
        print("start AI_Crown_CPU_Std ..")
        std_out = stdcrown(input_info)
        cpu_points_info = {}
        cpu_colors_info = {}
        colors = np.zeros_like(std_out.mesh.vertices, dtype=np.uint8)
        points_keys = [
            x for x in vars(std_out.mesh) if x not in vars(trimesh.Trimesh())
        ][2:]
        color_n = 0
        for key in points_keys:
            points = getattr(std_out.mesh, key, None)
            if points:
                color_list = []
                for p_n, p_idx in enumerate(points.idx):
                    color_r, color_g, color_b = colors[p_idx]
                    color_str = (
                        bin(color_r)[2:].zfill(8)
                        + bin(color_g)[2:].zfill(8)
                        + bin(color_b)[2:].zfill(8)
                    )
                    color_str = color_str[:color_n] + "1" + color_str[color_n + 1 :]
                    if key in [
                        "ad_points",
                    ]:
                        color_str = (
                            color_str[:-8] + bin(p_n)[2:].zfill(4) + color_str[-4:]
                        )
                    if key in [
                        "cross_points",
                    ]:
                        color_str = color_str[:-4] + bin(p_n)[2:].zfill(4)
                    color_r = int(color_str[:8], 2)
                    color_g = int(color_str[8:16], 2)
                    color_b = int(color_str[16:], 2)
                    colors[p_idx] = [color_r, color_g, color_b]
                    if [color_r, color_g, color_b] not in color_list:
                        color_list.append([color_r, color_g, color_b])
                cpu_colors_info[key] = color_list
                color_n += 1

                cpu_points_info[key] = points.pt.tolist()
                # cpu_points_info[key] = points.idx.tolist()
        cpu_points_info_backup = {}
        cpu_colors_info_backup = {}
        colors_backup = np.zeros_like(std_out.mesh_backup.vertices, dtype=np.uint8)
        points_keys = [
            x for x in vars(std_out.mesh) if x not in vars(trimesh.Trimesh())
        ][2:]
        # color = 100
        color_n = 0
        for key in points_keys:
            points = getattr(std_out.mesh, key, None)
            if points:
                color_list = []
                for p_n, p_idx in enumerate(points.idx):
                    color_r, color_g, color_b = colors_backup[p_idx]
                    color_str = (
                        bin(color_r)[2:].zfill(8)
                        + bin(color_g)[2:].zfill(8)
                        + bin(color_b)[2:].zfill(8)
                    )
                    color_str = color_str[:color_n] + "1" + color_str[color_n + 1 :]
                    if key in [
                        "ad_points",
                    ]:
                        color_str = (
                            color_str[:-8] + bin(p_n)[2:].zfill(4) + color_str[-4:]
                        )
                    if key in [
                        "cross_points",
                    ]:
                        color_str = color_str[:-4] + bin(p_n)[2:].zfill(4)
                    color_r = int(color_str[:8], 2)
                    color_g = int(color_str[8:16], 2)
                    color_b = int(color_str[16:], 2)
                    colors_backup[p_idx] = [color_r, color_g, color_b]
                    if [color_r, color_g, color_b] not in color_list:
                        color_list.append([color_r, color_g, color_b])
                cpu_colors_info_backup[key] = color_list
                color_n += 1

                cpu_points_info_backup[key] = points.pt.tolist()
                # cpu_points_info_backup[key] = points.idx.tolist()
        points_oppo_id = std_out.points_oppo_id

        standard = write_mesh_bytes(std_out.mesh, colors)
        mesh_backup = write_mesh_bytes(std_out.mesh_backup, colors_backup)
        closer = write_mesh_bytes(std_out.mesh1)
        further = write_mesh_bytes(std_out.mesh2)
        mesh_beiya = write_mesh_bytes(std_out.mesh_beiya)
        mesh_upper = write_mesh_bytes(std_out.mesh_upper)
        mesh_lower = write_mesh_bytes(std_out.mesh_lower)
        mesh_jaw = write_mesh_bytes(std_out.mesh_jaw)
        mesh_oppo = write_mesh_bytes(std_out.mesh_oppo)
        template_name = std_out.template_name

        if input_info.get("multi_restoration"):
            cpu_std_json = {
                "closer": closer,
                "further": further,
                "mesh_upper": mesh_upper,
                "mesh_lower": mesh_lower,
                "mesh_jaw": mesh_jaw,
                "mesh_oppo": mesh_oppo,
                "beiya_id": std_out.miss_id,
                "is_single": std_out.is_single,
                "template_name": template_name,
                "cpu_points_info": cpu_points_info,
                "cpu_colors_info": cpu_colors_info,
                "points_oppo_id": points_oppo_id,
                "rot_matrix": std_out.new_transform_list,
                "ai_matrix": input_info["ai_matrix"].tolist()
            }
        else:
            cpu_std_json = {
                "closer": closer,
                "further": further,
                "mesh_upper": mesh_upper,
                "mesh_lower": mesh_lower,
                "mesh_jaw": mesh_jaw,
                "mesh_oppo": mesh_oppo,
                "beiya_id": std_out.miss_id,
                "is_single": std_out.is_single,
                "template_name": template_name,
                "cpu_points_info": cpu_points_info,
                "cpu_colors_info": cpu_colors_info,
                "points_oppo_id": points_oppo_id,
            }

        if input_info.get("multi_restoration"):
            std_out.mesh.apply_transform(np.linalg.pinv(input_info["ai_matrix"]))
            std_out.mesh.apply_transform(np.linalg.pinv(std_out.new_transform_list[2]))
            std_out.mesh.apply_transform(np.linalg.pinv(std_out.new_transform_list[0]))
            std_out.mesh.apply_transform(np.linalg.pinv(std_out.new_transform_list[1]))
            standard = write_mesh_bytes(std_out.mesh, colors)

            std_out.mesh_beiya.apply_transform(np.linalg.pinv(input_info["ai_matrix"]))
            std_out.mesh_beiya.apply_transform(
                np.linalg.pinv(std_out.new_transform_list[2])
            )
            std_out.mesh_beiya.apply_transform(
                np.linalg.pinv(std_out.new_transform_list[0])
            )
            std_out.mesh_beiya.apply_transform(
                np.linalg.pinv(std_out.new_transform_list[1])
            )
            mesh_beiya = write_mesh_bytes(std_out.mesh_beiya)

            std_out.mesh_backup.apply_transform(np.linalg.pinv(input_info["ai_matrix"]))
            std_out.mesh_backup.apply_transform(
                np.linalg.pinv(std_out.new_transform_list[2])
            )
            std_out.mesh_backup.apply_transform(
                np.linalg.pinv(std_out.new_transform_list[0])
            )
            std_out.mesh_backup.apply_transform(
                np.linalg.pinv(std_out.new_transform_list[1])
            )
            mesh_backup = write_mesh_bytes(std_out.mesh_backup, colors_backup)

        std_json = {
            "cpu_std_json": cpu_std_json,
            "standard": standard,
            "inner": mesh_beiya,
            "standard_backup": mesh_backup,
        }

        print("suncess stdcrown")

        return {"Msg": {"data": std_json}, "Code": 200, "State": "Success"}
    except Exception as _:
        res = {"Msg": traceback.format_exc(), "Code": 203, "State": "Failure"}
        traceback.print_exc()
        return res


if __name__ == "__main__":
    import os
    import time

    # path = r"test_data_/月牙手工牙冠订单-200份-20250715"
    # dirs = ["50-2", "50-3", "50-4", "50-5"]
    # error_list = []
    # for dir in dirs:
    #     # dir = '50-5'
    #     cases = os.listdir(os.path.join(path, dir))
    #     for case in cases:
    #         # case = '838b-2912'
    #         if os.path.exists(os.path.join(path, dir, case, "succes_res.json")):
    #             with open(os.path.join(path, dir, case, "succes_res.json"), "r") as f:
    #                 event = json.load(f)["Msg"]["data"]
    #             event_ = event["cpu_process_info"]
    #             if event_["beiya_id"][-1] in ["4", "5", "6", "7"]:
    #                 try:
    #                     print(case)
    #                     # event["test"] = True
    #                     # event["save_path"] = os.path.join(path, dir, case)
    #                     event_["pred_filestem_name"] = event["pred_filestem_name"]
    #                     out = handler(event_, os.path.join(path, dir, case))
    #                     out["Msg"]["data"]["standard"] = event["pred_filestem_bstr"]
    #                     with open(os.path.join(path, dir, case, "std.json"), "w") as f:
    #                         f.write(json.dumps(out["Msg"]["data"]))
    #                 except:
    #                     error_list.append(case)
    #             # break
    #     # break
    # with open(os.path.join(path, dir, "error_list.txt"), "w") as f:
    #     f.write("\n".join(error_list))
    with open(
        "test_data_/muti_crown/response.json",
        "r",
    ) as f:
        data = json.load(f)["Msg"]["data"]
    # data["multi_restoration"] = True
    data["beiya_id"] = "47"

    for k, v in data["crown_res"][data["beiya_id"]].items():
        data[k] = v
    out = handler(data, "")
    with open('test_data_/muti_crown/std.json', 'w') as f:
        f.write(json.dumps(out["Msg"]["data"]))
