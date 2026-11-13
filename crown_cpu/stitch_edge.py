import base64
import json
import traceback
import requests

import DracoPy
import MQCompressPy
import numpy as np
import trimesh

from input_compat import (
    load_input_info,
    merge_missing_fields,
    upload_result,
)
from crown_cpu import stitch_edge


def read_mesh_bytes(buffer):
    a = base64.b64decode(buffer)
    mesh_object = DracoPy.decode_buffer_to_mesh(a)
    V = np.array(mesh_object.points).astype(np.float32).reshape(-1, 3)
    F = np.array(mesh_object.faces).astype(np.int64).reshape(-1, 3)
    return trimesh.Trimesh(V, F)

def read_mesh_bytes_unit16(buffer):
    a = base64.b64decode(buffer)
    mesh_object = DracoPy.decode_buffer_to_mesh(a)
    V = np.array(mesh_object.points).astype(np.float32).reshape(-1, 3)
    F = np.array(mesh_object.faces).astype(np.int64).reshape(-1, 3)
    flag = mesh_object.attributes[1]['data'].reshape(-1)
    return trimesh.Trimesh(V, F), flag


def write_mesh_bytes(mesh, preserve_order=False, colors=None):
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

def write_drc(drc, file):
    with open(file, "wb") as test_file:
        test_file.write(base64.b64decode(drc))


def matrix2matrix(crown_rot_matirx):
    ai_matrix = np.eye(4)  # 创建一个单位矩阵作为变换矩阵的初始值
    ai_matrix[:3, :3] = crown_rot_matirx  # 复制旋转矩阵的前三列到变换矩阵的前三列
    ai_matrix[:, 3] = [0, 0, 0, 1]
    return ai_matrix

def _transform_points(points, matrices, ai_matrix):
    """对 (N,3) 点集应用 multi_restoration 坐标变换链。
    
    变换顺序与 mesh 变换一致: matrices[1] · [0] · [2] · ai_matrix
    """
    pts = np.asarray(points, dtype=np.float64)
    pts_h = np.concatenate([pts, np.ones((len(pts), 1))], axis=1)
    for idx in (1, 0, 2):
        pts_h = (matrices[idx] @ pts_h.T).T
    pts_h = (ai_matrix @ pts_h.T).T
    return pts_h[:, :3].tolist()

STITCH_EDGE_PARAS_WHITELIST = {
    "align_edges",
    "undercut_filled",
    "fill_undercut",
    "margin_width",
    "cement_gap",
    "height_of_minimal_gap",
    "height_of_minimal_gap2",
    "minimal_gap",
}


def _normalize_stitch_edge_input(event):
    """归一化 stitch_edge 入口的公共兼容字段。"""
    normalized = dict(event)

    if normalized.get("cpu_info_json") is not None:
        normalized = merge_missing_fields(normalized, normalized["cpu_info_json"])

    if isinstance(normalized.get("paras"), dict):
        normalized["paras"] = {
            key: value
            for key, value in normalized["paras"].items()
            if key in STITCH_EDGE_PARAS_WHITELIST
        }
        for key in ("align_edges", "fill_undercut"):
            if normalized["paras"].get(key) is not None:
                normalized[key] = normalized["paras"][key]

    return normalized


def _apply_multi_restoration_inverse_transforms(mesh, input_info):
    mesh.apply_transform(np.linalg.pinv(input_info["ai_matrix"]))
    mesh.apply_transform(np.linalg.pinv(input_info["new_transform_list"][2]))
    mesh.apply_transform(np.linalg.pinv(input_info["new_transform_list"][0]))
    mesh.apply_transform(np.linalg.pinv(input_info["new_transform_list"][1]))


def _compress_stitch_crown(stitch_out):
    points_id = [
        stitch_out.points_inner_id,
        stitch_out.points_edge_outer_id,
        stitch_out.points_edge_inner_id,
    ]
    if len(stitch_out.occ_id):
        points_id.append(stitch_out.mesh.occ_id.idx)
    return compress_drc(stitch_out.mesh, points_id)


def handler(event, context):
    print("receive case")
    try:
        input_info = load_input_info(event, requests)
        print("start AI_Crown_Stitch_Edge ..")
        input_info = _normalize_stitch_edge_input(input_info)

        cpu_input_json = {
            "inner": input_info.get("inner"),
            "out": input_info.get("out"),
            "align_edges": input_info.get("align_edges"),
        }
        print("job_id", input_info.get("job_id"))
        if input_info.get("multi_restoration"):
            input_info["new_transform_list"] = input_info["rot_matrix"]
            inner = read_mesh_bytes(input_info["inner"])
            inner.apply_transform(input_info["new_transform_list"][1])
            inner.apply_transform(input_info["new_transform_list"][0])
            inner.apply_transform(input_info["new_transform_list"][2])
            inner.apply_transform(input_info["ai_matrix"])
            input_info["inner"] = write_mesh_bytes(inner)

            # out, occ_id = decompress_drc(input_info["out"])
            out, occ_id = read_mesh_bytes_unit16(input_info["out"])
            out.apply_transform(input_info["new_transform_list"][1])
            out.apply_transform(input_info["new_transform_list"][0])
            out.apply_transform(input_info["new_transform_list"][2])
            out.apply_transform(input_info["ai_matrix"])
            input_info["out"] = out
            input_info["occ_id"] = np.where(np.array(occ_id) == 4)[0]

            if input_info.get("control_pts_front"):
                input_info["control_pts_front"] = _transform_points(
                    input_info["control_pts_front"],
                    input_info["new_transform_list"],
                    input_info["ai_matrix"],
                )

        stitch_out = stitch_edge(input_info)
        crown = _compress_stitch_crown(stitch_out)
        inner = write_mesh_bytes(stitch_out.mesh_beiya)
        thickness_shell = write_mesh_bytes(stitch_out.thickness_shell)

        if input_info.get("multi_restoration"):
            _apply_multi_restoration_inverse_transforms(stitch_out.mesh, input_info)
            crown = _compress_stitch_crown(stitch_out)

            _apply_multi_restoration_inverse_transforms(
                stitch_out.mesh_beiya, input_info
            )
            inner = compress_drc(stitch_out.mesh_beiya)

            _apply_multi_restoration_inverse_transforms(
                stitch_out.thickness_shell, input_info
            )
            thickness_shell = compress_drc(stitch_out.thickness_shell)

        stitch_json = {
            "crown": crown,
            "inner": inner,
            "thickness_shell": thickness_shell,
            "cpu_input_json": cpu_input_json,
            "self_intersecting": stitch_out.self_intersecting,
            "thick_shell_hit": stitch_out.colloision
        }
        print("suncess stitch_edge")

        if event.get("target_url"):
            upload_response = upload_result(
                event.get("target_url"), stitch_json, requests
            )
            print(upload_response.status_code)
            return {"Msg": {"data": "result saved to target url"}, "Code": 200, "State": "Success"}

        return {"Msg": {"data": stitch_json}, "Code": 200, "State": "Success"}
    except Exception as _:
        res = {"Msg": traceback.format_exc(), "Code": 203, "State": "Failure"}
        traceback.print_exc()
        return res


if __name__ == "__main__":
    import os
    import time

    # path = r'test_data_/unercut'
    # cases = os.listdir(path)
    # for case in cases:
    #     case = 'd8186235-2ea8-4dc6-88d3-4b4ac71a0a09'
    #     # stitch_file = [x for x in os.listdir(f'{path}/{case}') if 'stitch' in x][0]
    #     # post_file = [x for x in os.listdir(f'{path}/{case}') if 'post' in x][0]
    #     stitch_file = 'stitch_b3cba186-18ca-48dc-b510-e9dd960f037e'
    #     post_file = 'under_91b43ff3-2e6d-4e5c-9f5b-4304d5f48551'
    #     with open(f'{path}/{case}/{stitch_file}/input.json', "r") as f:
    #         event = json.load(f)
    #     with open(f'{path}/{case}/{post_file}/output.json', "r") as f:
    #         event_ = json.load(f)
    #     event['out'] = event_['out']
    #     event['mesh_jaw'] = event_['cpu_std_json']['mesh_jaw']
    #     # read_mesh_bytes(event["fixed_crown"]).export('1.stl')
    #     # read_mesh_bytes(event["crown"]).export('2.stl')
    #     # trimesh.PointCloud(read_mesh_bytes(event["fixed_crown"]).vertices[event['fixed_points']]).export('3.ply')
    #     s1 = time.time()
    #     out = handler(event, f'{path}/{case}/{stitch_file}')
    #     s2 = time.time()
    #     print(s2 - s1)
    #     with open(f'{path}/{case}/{stitch_file}/stitch_edge.json', "w") as f:
    #         f.write(json.dumps(out["Msg"]["data"]))
    #     break
    # with open("test_data_/muti_crown/response.json", "r") as f:
    #     event_gpu = json.load(f)["Msg"]["data"]

    # with open("test_data_/muti_crown/post.json", "r") as f:
    #     event = json.load(f)

    # event["multi_restoration"] = True
    # out = handler(event, "")

    # with open("test_data_/muti_crown/stitch.json", "w") as f:
    #     f.write(json.dumps(out["Msg"]["data"]))
    # with open("test_data_/test/input.json", "r") as f:
    #     event = json.load(f)
    # with open("test_data_/test/output.json", "r") as f:
    #     event_ = json.load(f)
    # event["out"] = event_["out"]
    # event["mesh_jaw"] = event_["cpu_std_json"]["mesh_jaw"]
    # event["test"] = True
    # event["save_path"] = "test_data_/test"
    # out = handler(event, "")
    with open("/home/wanglong/下载/data/8/crown_stitch_edge (1).json", "r") as f:
        event = json.load(f)
    event["test"] = True
    event["save_path"] = "/home/wanglong/下载/data/8"
    out = handler(event, "")
    
