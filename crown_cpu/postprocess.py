import base64
import copy
import json
import traceback
import requests
import DracoPy
import MQCompressPy
import numpy as np
import trimesh

from input_compat import (
    file_name2template_name,
    load_input_info,
    merge_missing_fields,
    upload_result,
)
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


POSTPROCESS_PARAS_WHITELIST = {
    "adjust_crown",
    "undercut_filled",
    "fill_undercut",
    "minimal_thickness",
    "margin_width",
    "cement_gap",
    "height_of_minimal_gap",
    "height_of_minimal_gap2",
    "minimal_gap",
    "ad_gap",
    "occlusal_distance",
    "prox_or_occlu",
    "local",
}


def _normalize_postprocess_input(event):
    """归一化 postprocess 入口的公共兼容字段。"""
    normalized = dict(event)

    if normalized.get("pred_filestem_name"):
        normalized["template_name"] = file_name2template_name(
            normalized.get("pred_filestem_name")
        )

    if normalized.get("cpu_undercut_json") is not None:
        normalized = merge_missing_fields(normalized, normalized["cpu_undercut_json"])
        normalized["pre_tag"] = "undercut"
    elif normalized.get("cpu_std_json") is not None:
        normalized = merge_missing_fields(normalized, normalized["cpu_std_json"])
        normalized["pre_tag"] = "std"

    if isinstance(normalized.get("paras"), dict):
        normalized["paras"] = {
            key: value
            for key, value in normalized["paras"].items()
            if key in POSTPROCESS_PARAS_WHITELIST
        }

    return normalized


def _apply_multi_restoration_inverse_transforms(mesh, input_info):
    mesh.apply_transform(np.linalg.pinv(input_info["ai_matrix"]))
    mesh.apply_transform(np.linalg.pinv(input_info["new_transform_list"][2]))
    mesh.apply_transform(np.linalg.pinv(input_info["new_transform_list"][0]))
    mesh.apply_transform(np.linalg.pinv(input_info["new_transform_list"][1]))


def _compress_postprocess_crown(post_out):
    points_id = [
        post_out.points_inner_id,
        post_out.points_edge_outer_id,
        post_out.points_edge_inner_id,
    ]
    if post_out.occ_id is not None:
        points_id.append(post_out.mesh.occ_id.idx)
    return compress_drc(post_out.mesh, points_id)


def _build_postprocess_cpu_info_json(
    post_out, input_info, closer, further, cpu_points_info, axis, template_name
):
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
    if input_info.get("multi_restoration"):
        cpu_info_json.update(
            {
                "mesh_jaw": compress_drc(post_out.mesh_jaw),
                "rot_matrix": input_info["new_transform_list"],
                "ai_matrix": input_info["ai_matrix"],
            }
        )
    return cpu_info_json


def handler(event, context):
    print("receive case")
    # event["new_placement"] = True
    try:
        input_info = load_input_info(event, requests)
        print("start AI_Crown_Post ..")
        input_info = _normalize_postprocess_input(input_info)

        print("pred_filestem_name", input_info.get("pred_filestem_name"))
        cpu_input_json = {
            "inner": input_info.get("inner"),
            "standard": input_info.get("standard"),
            "paras": input_info.get("paras"),
            "crown_rot_matirx": input_info.get("crown_rot_matirx"),
            "template_name": input_info.get("template_name", "st_tooth"),
            "points_info": input_info.get("points_info"),
        }
        print("template_name", input_info.get("template_name"))
        print("job_id", input_info.get("job_id"))
        if input_info.get("multi_restoration"):
            input_info["new_transform_list"] = input_info["rot_matrix"]
            inner = read_mesh_bytes(input_info["inner"])
            inner.apply_transform(input_info["new_transform_list"][1])
            inner.apply_transform(input_info["new_transform_list"][0])
            inner.apply_transform(input_info["new_transform_list"][2])
            inner.apply_transform(input_info["ai_matrix"])
            input_info["inner"] = write_mesh_bytes(inner)

            if input_info.get("std_crown"):
                std_crown, occ_id = decompress_drc(input_info["std_crown"])
                std_crown.apply_transform(input_info["new_transform_list"][1])
                std_crown.apply_transform(input_info["new_transform_list"][0])
                std_crown.apply_transform(input_info["new_transform_list"][2])
                std_crown.apply_transform(input_info["ai_matrix"])
                input_info["std_crown"] = std_crown
                input_info["occ_id"] = np.where(np.array(occ_id) == 1)[0]
                standard, _ = decompress_drc(input_info["standard"])
                standard.apply_transform(input_info["new_transform_list"][1])
                standard.apply_transform(input_info["new_transform_list"][0])
                standard.apply_transform(input_info["new_transform_list"][2])
                standard.apply_transform(input_info["ai_matrix"])
                input_info["standard"] = standard
            else:
                standard, occ_id = decompress_drc(input_info["standard"])
                standard.apply_transform(input_info["new_transform_list"][1])
                standard.apply_transform(input_info["new_transform_list"][0])
                standard.apply_transform(input_info["new_transform_list"][2])
                standard.apply_transform(input_info["ai_matrix"])
                input_info["standard"] = standard
                input_info["occ_id"] = np.where(np.array(occ_id) == 1)[0]

            # control_pts_front 与 mesh 同步坐标变换
            if input_info.get("control_pts_front"):
                input_info["control_pts_front"] = _transform_points(
                    input_info["control_pts_front"],
                    input_info["new_transform_list"],
                    input_info["ai_matrix"],
                )

        post_out = post(input_info)
        crown = _compress_postprocess_crown(post_out)
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

        cpu_info_json = _build_postprocess_cpu_info_json(
            post_out,
            input_info,
            closer,
            further,
            cpu_points_info,
            axis,
            template_name,
        )

        if input_info.get("multi_restoration"):
            _apply_multi_restoration_inverse_transforms(post_out.mesh, input_info)
            crown = _compress_postprocess_crown(post_out)

            _apply_multi_restoration_inverse_transforms(
                post_out.mesh_outside, input_info
            )
            out = compress_drc(post_out.mesh_outside)

            _apply_multi_restoration_inverse_transforms(
                post_out.mesh_beiya, input_info
            )
            inner = compress_drc(post_out.mesh_beiya)

            _apply_multi_restoration_inverse_transforms(
                post_out.thickness_shell, input_info
            )
            thickness_shell = compress_drc(post_out.thickness_shell)
            mesh_tmp = post_out.mesh_tmp
            for k, v in mesh_tmp.items():
                _apply_multi_restoration_inverse_transforms(v, input_info)
                mesh_tmp[k] = compress_drc(v)

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
            "warning_info":post_out.warning_info,
            "collides_with_antagonist": post_out.collides_with_antagonist,
            "collides_with_adjacent": post_out.collides_with_adjacent,
            "mesh_tmp": mesh_tmp,
        }
        print("suncess postprocess")
        if event.get("target_url"):
            upload_response = upload_result(
                event.get("target_url"), post_json, requests
            )
            print(upload_response.status_code)
            return {"Msg": {"data": "result saved to target url"}, "Code": 200, "State": "Success"}

        return {"Msg": {"data": post_json}, "Code": 200, "State": "Success"}
    except Exception as _:
        res = {"Msg": traceback.format_exc(), "Code": 203, "State": "Failure"}
        traceback.print_exc()
        return res


if __name__ == "__main__":
    pass
