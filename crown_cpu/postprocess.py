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
    if mesh:
        vert_flags = np.zeros(len(mesh.vertices), dtype=np.uint8)
        for i in range(len(points_id)):
            if len(points_id[i]) == 0:
                continue
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
        if error_code == 0:
            b64_bytes = base64.b64encode(compressed_data)
            b64_str = b64_bytes.decode("utf-8")
            return b64_str
        else:
            assert "drc compress error"
    else:
        return ''


def decompress_drc(compressed_data):
    compressed_data = base64.b64decode(compressed_data)
    out_mesh = MQCompressPy.MQC_Mesh()
    out_flags = MQCompressPy.VerticeFlag_UINT8()
    out_mesh_, out_flags, error_code = MQCompressPy.decompressMesh_UINT8(
        compressed_data
    )
    out_mesh = trimesh.Trimesh()
    out_mesh.vertices = out_mesh_.verts
    out_mesh.faces = out_mesh_.faces
    return out_mesh, out_flags


def compress_drc_int16(mesh, config):
    vert_flags = np.zeros(len(mesh.vertices), dtype=np.int16)
    vert_flags[config["occl_points"]] += 1
    vert_flags[config["adj1_points"]] += 2
    vert_flags[config["adj2_points"]] += 2**2
    vert_flags[config["fcm_points"]] += 2**3
    vert_flags[config["nfcm_points"]] += 2**4
    vert_flags[config["fcd_points"]] += 2**5
    vert_flags[config["nfcd_points"]] += 2**6
    vert_flags[config["oc_points"]] += 2**7
    vert_flags[config["outer_points"]] += 2**8
    vert_flags[config["inner_points"]] += 2**9
    vert_flags[config["edge_points"]] += 2**10
    in_mesh = MQCompressPy.MQC_Mesh()
    in_mesh.verts = MQCompressPy.VerticeArray(mesh.vertices)
    in_mesh.faces = MQCompressPy.FaceArray(mesh.faces)
    in_vert_flags = MQCompressPy.VerticeFlag(vert_flags)
    compressed_data, error_code = MQCompressPy.compressMesh(in_mesh, in_vert_flags)
    if error_code == 0:
        b64_bytes = base64.b64encode(compressed_data)
        b64_str = b64_bytes.decode("utf-8")
        return b64_str
    else:
        assert "drc compress error"


def decompress_drc_int16(compressed_data):
    compressed_data = base64.b64decode(compressed_data)
    out_mesh = MQCompressPy.MQC_Mesh()
    out_flags = MQCompressPy.VerticeFlag()
    out_mesh_, out_flags, error_code = MQCompressPy.decompressMesh(compressed_data)
    out_mesh = trimesh.Trimesh()
    out_mesh.vertices = out_mesh_.verts
    out_mesh.faces = out_mesh_.faces
    return out_mesh, out_flags


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

            if event.get("std_crown"):
                std_crown, occ_id = decompress_drc(event["std_crown"])
                std_crown.apply_transform(event["new_transform_list"][1])
                std_crown.apply_transform(event["new_transform_list"][0])
                std_crown.apply_transform(event["new_transform_list"][2])
                std_crown.apply_transform(event["ai_matrix"])
                event["std_crown"] = std_crown
                event["occ_id"] = np.where(np.array(occ_id) == 1)[0]
                standard, _ = decompress_drc(event["standard"])
                standard.apply_transform(event["new_transform_list"][1])
                standard.apply_transform(event["new_transform_list"][0])
                standard.apply_transform(event["new_transform_list"][2])
                standard.apply_transform(event["ai_matrix"])
                event["standard"] = standard
            else:
                standard, occ_id = decompress_drc(event["standard"])
                standard.apply_transform(event["new_transform_list"][1])
                standard.apply_transform(event["new_transform_list"][0])
                standard.apply_transform(event["new_transform_list"][2])
                standard.apply_transform(event["ai_matrix"])
                event["standard"] = standard
                event["occ_id"] = np.where(np.array(occ_id) == 1)[0]
            

            # standard, out_flags = decompress_drc(event["standard"])
            # standard.apply_transform(event["new_transform_list"][1])
            # standard.apply_transform(event["new_transform_list"][0])
            # standard.apply_transform(event["new_transform_list"][2])
            # standard.apply_transform(event["ai_matrix"])
            # event["standard"] = standard
            # config = {}
            # config['occl_points'] = np.where((np.array(out_flags) & (1 << 0)) != 0)[0]
            # config['adj1_points'] = np.where((np.array(out_flags) & (1 << 1)) != 0)[0]
            # config['adj2_points'] = np.where((np.array(out_flags) & (1 << 2)) != 0)[0]
            # config['fcm_points'] = np.where((np.array(out_flags) & (1 << 3)) != 0)[0]
            # config['nfcm_points'] = np.where((np.array(out_flags) & (1 << 4)) != 0)[0]
            # config['fcd_points'] = np.where((np.array(out_flags) & (1 << 5)) != 0)[0]
            # config['nfcd_points'] = np.where((np.array(out_flags) & (1 << 6)) != 0)[0]
            # config['oc_points'] = np.where((np.array(out_flags) & (1 << 7)) != 0)[0]
            

        post_out = post(event)
        if post_out.occ_id is not None:
            crown = compress_drc(
                post_out.mesh,
                [
                    post_out.points_inner_id,
                    post_out.points_edge_outer_id,
                    post_out.points_edge_inner_id,
                    post_out.mesh.occ_id.idx,
                ],
            )
        else:
            crown = compress_drc(
                post_out.mesh,
                [
                    post_out.points_inner_id,
                    post_out.points_edge_outer_id,
                    post_out.points_edge_inner_id,
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
            if post_out.occ_id is not None:
                crown = compress_drc(
                    post_out.mesh,
                    [
                        post_out.points_inner_id,
                        post_out.points_edge_outer_id,
                        post_out.points_edge_inner_id,
                        post_out.mesh.occ_id.idx,
                    ],
                )
            else:
                crown = compress_drc(
                    post_out.mesh,
                    [
                        post_out.points_inner_id,
                        post_out.points_edge_outer_id,
                        post_out.points_edge_inner_id,
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
            "self_intersecting": post_out.self_intersecting,
            "thick_shell_hit": post_out.colloision,
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

    # dir_path = "test_data_/muti_crown/post"
    # files = os.listdir(dir_path)
    # error_file = [
    #     "cf576eee-361d-4622-8205-ba5987006c19",
    #     "db1058fe-e21e-4ae9-bc81-c3bc5bd78f99",
    # ]
    # for file in files:
    #     if file in error_file:
    #         continue
    #     # file = '9fdb1618-3a1e-4383-bb4e-72e719700997'
    #     print(1111, file)
    #     post_case = os.listdir(os.path.join(dir_path, file))
    #     for case in post_case:
    #         if not os.path.exists(
    #             os.path.join(dir_path, file, case, "crown_post.json")
    #         ):
    #             continue
    #         else:
    #             if os.path.exists(
    #                 os.path.join(dir_path, file, case, "out3", "fill_gap.stl")
    #             ):
    #                 # continue
    #                 mesh = trimesh.load(
    #                     os.path.join(dir_path, file, case, "out3", "fill_gap.stl")
    #                 )
    #                 # mesh.show()
    #                 print
                # with open(os.path.join(dir_path, file, case, "crown_post.json"), "r") as f:
                #     event = json.load(f)
                # event["test"] = True
                # event["save_path"] = os.path.join(dir_path, file, case, 'out3')
                # out = handler(event, "")
                # with open(os.path.join(dir_path, file, case, 'out3', "post.json"), "w") as f:
                #     f.write(json.dumps(out["Msg"]["data"]))
                # try:
                #     mesh = trimesh.load(os.path.join(dir_path, file, case, 'out2', 'fill_gap.stl'))
                #     thick_shell = trimesh.load(os.path.join(dir_path, file, case, 'out2', 'thickness_shell.stl'))
                # except:
                #     continue
                # c = trimesh.collision.CollisionManager()
                # c.add_object('crown', mesh)
                # colloision = c.in_collision_single(thick_shell)
                # if colloision:
                #     print(file)
                # with open(os.path.join(dir_path, file, case, 'out2', "post.json"), 'r') as f:
                #     data = json.load(f)
                # crown, flag = decompress_drc(data['crown'])
                # inner = crown.as_open3d.select_by_index(np.where(np.array(flag) == 1)[0])
                # inner = trimesh.Trimesh(inner.vertices, inner.triangles)
                # outer = trimesh.load(os.path.join(dir_path, file, case, 'out2', 'mesh_out.stl'))
                # from crown_cpu import get_thickness_gap
                # inner.invert()
                # thick_shell = get_thickness_gap(inner, outer)
                # thick_shell.export(os.path.join(dir_path, file, case, 'out2', 'thickness_shell.stl'))
        # break
    # params = {
    #     "occlusal_distance": 0.3,
    #     "ad_gap": -0.03,
    #     "prox_or_occlu": 2,
    #     "adjust_crown": 0,
    #     "morph_template": "st_tooth",
    # }

    # with open("test_data_/test/output.json", "r") as f:
    #     event_gpu = json.load(f)

    # with open("test_data_/test/input.json", "r") as f:
    #     event = json.load(f)

    # with open("test_data_/test/output_std.json", "r") as f:
    #     event_std = json.load(f)['cpu_std_json']
    # # mesh_beiya = write_mesh_bytes(trimesh.load('test_data_/muti_crown/case2/mesh_beiya.stl'))
    # # event['inner'] = mesh_beiya
    # # event["standard"] = event_gpu["crown_res"]["16"]["pred_st"]
    # # event["multi_restoration"] = True
    # for k, v in event_gpu["cpu_process_info"].items():
    #     if k not in event.keys():
    #         event[k] = v
    # for k, v in event_std.items():
    #     if k not in event.keys():
    #         event[k] = v
    # event["paras"] = params
    # event['test'] = True
    # event['save_path'] = 'test_data_/test'
    # out = handler(event, "")
    # with open("test_data_/muti_crown/case2/post.json", "w") as f:
    #     f.write(json.dumps(out["Msg"]["data"]))

    # params = {
    #     "occlusal_distance": 0.3,
    #     "ad_gap": -0.03,
    #     "prox_or_occlu": 2,
    #     "adjust_crown": 1,
    #     "morph_template": "st_tooth",
    # }
    # with open("test_data_/test/crown_post_36.json", "r") as f:
    #     event = json.load(f)
    with open("test_data_/thick_shell/095193d9-dbbd-4ce0-831f-5ad15edf8a87/crown_post.json", "r") as f:
        event = json.load(f)
    # with open("/home/wanglong/下载/data/1/response_pcd.json", "r") as f:
    #     event_out = json.load(f)
    # event_input = event['cpu_input_json']
    # for k, v in event_input.items():
    #     event[k] = v
    event["test"] = True
    event["save_path"] = 'test_data_/thick_shell/095193d9-dbbd-4ce0-831f-5ad15edf8a87'
    event["paras"]["fill_undercut"] = True
    out = handler(event, "")
    with open("test_data_/thick_shell/095193d9-dbbd-4ce0-831f-5ad15edf8a87/post.json", "w") as f:
        f.write(json.dumps(out["Msg"]["data"]))
