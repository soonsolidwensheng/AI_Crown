import base64
import copy
import json
import traceback

import DracoPy
import MQCompressPy
import numpy as np
import trimesh

from crown_cpu import post


def read_mesh_bytes(buffer):
    a = base64.b64decode(buffer)
    mesh_object = DracoPy.decode_buffer_to_mesh(a)
    V = np.array(mesh_object.points).astype(np.float32).reshape(-1, 3)
    F = np.array(mesh_object.faces).astype(np.int64).reshape(-1, 3)
    return trimesh.Trimesh(V, F)


def write_mesh_bytes(mesh, preserve_order=False):
    # 设置 Draco 编码选项
    encoding_test = DracoPy.encode_mesh_to_buffer(
        mesh.vertices,
        mesh.faces,
        preserve_order=preserve_order,
        quantization_bits=14,
        compression_level=10,
        colors=None,
    )
    b64_bytes = base64.b64encode(encoding_test)
    b64_str = b64_bytes.decode("utf-8")
    return b64_str


def compress_drc(mesh, points_id=[]):
    vert_flags = np.zeros(len(mesh.vertices), dtype=np.uint8)
    for i in range(len(points_id)):
        vert_flags[points_id[i]] = i + 1
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


def write_drc(drc, file):
    with open(file, "wb") as test_file:
        test_file.write(base64.b64decode(drc))


def dict_np2list(data):
    d = copy.deepcopy(data)

    for k, v in d.items():
        if isinstance(v, np.ndarray):
            d[k] = v.tolist()
        elif isinstance(v, dict):
            d[k] = dict_np2list(v)

    return d


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


def handler(event, context):
    print("receive case")
    try:
        print("start AI_Crown_Post ..")

        print("pred_filestem_name", event.get("pred_filestem_name"))
        if event.get("pred_filestem_name"):
            event["template_name"] = file_name2template_name(
                event.get("pred_filestem_name")
            )
        cpu_input_json = {
            "inner": event.get("inner"),
            "standard": event.get("standard"),
            "paras": event.get("paras"),
            "crown_rot_matirx": event.get("crown_rot_matirx"),
            "template_name": event.get("template_name", "st_tooth"),
            "points_info": event.get("points_info"),
        }
        if "cpu_undercut_json" in event.keys():
            for k, v in event["cpu_undercut_json"].items():
                if k not in event.keys():
                    event[k] = v
            event["pre_tag"] = "undercut"
        elif "cpu_std_json" in event.keys():
            for k, v in event["cpu_std_json"].items():
                if k not in event.keys():
                    event[k] = v
            event["pre_tag"] = "std"
        print("template_name", event.get("template_name"))
        print("job_id", event.get("job_id"))
        if event.get("multi_restoration"):
            event["new_transform_list"] = event["rot_matrix"]
            inner = read_mesh_bytes(event["inner"])
            inner.apply_transform(event["new_transform_list"][1])
            inner.apply_transform(event["new_transform_list"][0])
            inner.apply_transform(event["new_transform_list"][2])
            inner.apply_transform(event["ai_matrix"])
            event["inner"] = write_mesh_bytes(inner)

            standard = read_mesh_bytes(event["standard"])
            standard.apply_transform(event["new_transform_list"][1])
            standard.apply_transform(event["new_transform_list"][0])
            standard.apply_transform(event["new_transform_list"][2])
            standard.apply_transform(event["ai_matrix"])
            event["standard"] = write_mesh_bytes(standard)

        post_out = post(event)
        crown = compress_drc(
            post_out.mesh,
            [
                post_out.points_inner_id,
                post_out.points_edge_outer_id,
                post_out.points_edge_inner_id,
                # post_out.points_edge_id,
            ],
        )
        out = compress_drc(post_out.mesh_outside)
        inner = compress_drc(post_out.mesh_beiya)
        thickness_shell = compress_drc(post_out.thickness_shell)
        closer = compress_drc(post_out.mesh1)
        further = compress_drc(post_out.mesh2)
        cpu_points_info = {}
        points_keys = [
            x for x in vars(post_out.mesh) if x not in vars(trimesh.Trimesh())
        ][2:]
        for key in points_keys:
            points = getattr(post_out.mesh, key, None)
            if points:
                cpu_points_info[key] = points.pt.tolist()

        print_points = (
            trimesh.PointCloud(post_out.mesh.ad_points.pt)
            .apply_transform(post_out.print_matrix)
            .vertices.tolist()
        )
        print_normal = (
            trimesh.PointCloud(post_out.add_point_normal)
            .apply_transform(post_out.print_matrix)
            .vertices.tolist()
        )
        axis = np.array(post_out.axis).tolist()
        print_matrix = np.array(post_out.print_matrix).tolist()
        template_name = post_out.template_name

        if event.get("multi_restoration"):
            cpu_info_json = {
                "mesh_oppo": compress_drc(post_out.mesh_oppo),
                "mesh_jaw": compress_drc(post_out.mesh_jaw),
                "closer": closer,
                "further": further,
                "beiya_id": post_out.miss_id,
                "is_single": post_out.is_single,
                "cpu_points_info": cpu_points_info,
                "axis": axis,
                "template_name": template_name,
                "rot_matrix": event["new_transform_list"],
                "ai_matrix": event["ai_matrix"],
            }
        else:
            cpu_info_json = {
                "mesh_oppo": compress_drc(post_out.mesh_oppo),
                "closer": closer,
                "further": further,
                "beiya_id": post_out.miss_id,
                "is_single": post_out.is_single,
                "cpu_points_info": cpu_points_info,
                "axis": axis,
                "template_name": template_name,
            }

        if event.get("multi_restoration"):
            post_out.mesh.apply_transform(np.linalg.pinv(event["ai_matrix"]))
            post_out.mesh.apply_transform(
                np.linalg.pinv(event["new_transform_list"][2])
            )
            post_out.mesh.apply_transform(
                np.linalg.pinv(event["new_transform_list"][0])
            )
            post_out.mesh.apply_transform(
                np.linalg.pinv(event["new_transform_list"][1])
            )
            crown = compress_drc(
                post_out.mesh,
                [
                    post_out.points_inner_id,
                    post_out.points_edge_outer_id,
                    post_out.points_edge_inner_id,
                    # post_out.points_edge_id,
                ],
            )

            post_out.mesh_outside.apply_transform(np.linalg.pinv(event["ai_matrix"]))
            post_out.mesh_outside.apply_transform(
                np.linalg.pinv(event["new_transform_list"][2])
            )
            post_out.mesh_outside.apply_transform(
                np.linalg.pinv(event["new_transform_list"][0])
            )
            post_out.mesh_outside.apply_transform(
                np.linalg.pinv(event["new_transform_list"][1])
            )
            out = compress_drc(post_out.mesh_outside)

            post_out.mesh_beiya.apply_transform(np.linalg.pinv(event["ai_matrix"]))
            post_out.mesh_beiya.apply_transform(
                np.linalg.pinv(event["new_transform_list"][2])
            )
            post_out.mesh_beiya.apply_transform(
                np.linalg.pinv(event["new_transform_list"][0])
            )
            post_out.mesh_beiya.apply_transform(
                np.linalg.pinv(event["new_transform_list"][1])
            )
            inner = compress_drc(post_out.mesh_beiya)

            post_out.thickness_shell.apply_transform(np.linalg.pinv(event["ai_matrix"]))
            post_out.thickness_shell.apply_transform(
                np.linalg.pinv(event["new_transform_list"][2])
            )
            post_out.thickness_shell.apply_transform(
                np.linalg.pinv(event["new_transform_list"][0])
            )
            post_out.thickness_shell.apply_transform(
                np.linalg.pinv(event["new_transform_list"][1])
            )
            thickness_shell = compress_drc(post_out.thickness_shell)

        post_json = {
            "crown": crown,
            "out": out,
            "inner": inner,
            "thickness_shell": thickness_shell,
            "points_info": {
                "points": print_points,
                "normals": print_normal,
                "axis": axis,
                "matrix": print_matrix,
            },
            "cpu_info_json": cpu_info_json,
            "cpu_input_json": cpu_input_json,
        }

        print("suncess postprocess")

        return {"Msg": {"data": post_json}, "Code": 200, "State": "Success"}
    except Exception as _:
        res = {"Msg": traceback.format_exc(), "Code": 203, "State": "Failure"}
        traceback.print_exc()
        return res


if __name__ == "__main__":
    import os
    import time

    # params = {
    #     "occlusal_distance": 0.3,
    #     "ad_gap": -0.03,
    #     "prox_or_occlu": 2,
    #     "adjust_crown": 1,
    #     "morph_template": "st_tooth",
    # }
    # path = r"test_data_/月牙手工牙冠订单-200份-20250715"
    # dirs = ["50-2", "50-3", "50-4", "50-5"]
    # error_list = []
    # pass_id = [
    #     # 'e1dc-7771', # 备牙id错误
    #     # 'c281-9644', # 备牙id错误
    #     # '7916-5156', # 备牙id错误
    #     # '62c7-7572',  # 嵌体数据
    #     # '7c62-3711',  # 备牙边缘错误
    #     # # '#12028', # 自相交 邻牙调整

    #     # '2d89d1ea36504dcfa73f', # 对颌距离判断错误 ?  对颌有飞边, 可以生成但缝合失败
    #     # '6ebf-7321',  # 初始位置不佳，咬合调整错误  ?  没有空间

    #     # 'cce6-0503',  # 咬合调整错误  ?  没有空间

    #     # '838b-2912',  # 初始位置不佳 ?  没有空间
    #     # '917a-4299',  # 网格结构问题，需要修复  ?  可以生成但缝合失败

    #     # # 成功101
    # ]
    # for dir in dirs:
    #     # dir = '50-2'
    #     cases = os.listdir(os.path.join(path, dir))
    #     for case in cases:
    #         # if case in pass_id:
    #         #     continue
    #         # case = '603f-5397'
    #         if os.path.exists(os.path.join(path, dir, case, "succes_res.json")):
    #             with open(os.path.join(path, dir, case, "succes_res.json"), "r") as f:
    #                 event_ = json.load(f)["Msg"]["data"]
    #             if os.path.exists(os.path.join(path, dir, case, "std.json")):
    #                 if os.path.exists(os.path.join(path, dir, case, "post.json")):
    #                     continue
    #                 print(case)
    #                 with open(os.path.join(path, dir, case, "std.json"), "r") as f:
    #                     event_std = json.load(f)
    #                 try:
    #                     event = event_["cpu_process_info"]
    #                     for k, v in event_std["cpu_std_json"].items():
    #                         if k not in event.keys():
    #                             event[k] = v
    #                     model_name = event_['pred_filestem_name']
    #                     standard = trimesh.load(f'/home/wanglong/pyproject/lambda_crown/cad_git/Merge_OriginalSTL/{model_name}.stl')
    #                     standard.apply_transform(event_['spatial_loc_prediction_transform'])
    #                     event['standard'] = standard
    #                     event["crown_rot_matirx"] = np.eye(4)
    #                     event["inner"] = event["mesh_beiya"]
    #                     event["paras"] = params
    #                     event["pre_tag"] = "std"
    #                     event["test"] = True
    #                     event["save_path"] = os.path.join(path, dir, case)
    #                     s1 = time.time()
    #                     out = handler(event, os.path.join(path, dir, case))
    #                     s2 = time.time()
    #                     print(s2 - s1)
    #                     with open(os.path.join(path, dir, case, "post.json"), "w") as f:
    #                         f.write(json.dumps(out["Msg"]["data"]))
    #                 except Exception as e:
    #                     error_list.append(case)
    #     #     break
    #     # break
    # with open(os.path.join(path, "error_post_list.txt"), "w") as f:
    #     f.write("\n".join(error_list))
    params = {
        "occlusal_distance": 0.3,
        "ad_gap": -0.03,
        "prox_or_occlu": 2,
        "adjust_crown": 1,
        "morph_template": "st_tooth",
    }
    with open("test_data_/muti_crown/response.json", "r") as f:
        event_gpu = json.load(f)["Msg"]["data"]

    with open("test_data_/muti_crown/std.json", "r") as f:
        event = json.load(f)
    event["standard"] = event_gpu["crown_res"]["47"]["pred_st"]
    event["multi_restoration"] = True
    out = handler(event, "")
    with open("test_data_/muti_crown/post.json", "w") as f:
        f.write(json.dumps(out["Msg"]["data"]))
