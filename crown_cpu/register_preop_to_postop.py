from pre_op_mirror.pre_op import preop2post
from crown_cpu import read_mesh_bytes
import trimesh
import traceback
import numpy as np


def handler(event, context):
    try:
        preop_teeth_o3d = event["preop_teeth"]
        post_teeth_o3d = event["postop_teeth"]
        pre_keys = set(preop_teeth_o3d.keys())
        post_keys = set(post_teeth_o3d.keys())
        intersect_keys = list(pre_keys & post_keys)
        pre_mesh_upper = []
        pre_mesh_lower = []
        post_mesh_upper = []
        post_mesh_lower = []
        for key in intersect_keys:
            if key[0] in ["1", "2"]:
                pre_mesh_upper.append(read_mesh_bytes(preop_teeth_o3d[key]))
                post_mesh_upper.append(read_mesh_bytes(post_teeth_o3d[key]))
            else:
                pre_mesh_lower.append(read_mesh_bytes(preop_teeth_o3d[key]))
                post_mesh_lower.append(read_mesh_bytes(post_teeth_o3d[key]))
        pre_mesh_upper = trimesh.util.concatenate(pre_mesh_upper)
        pre_mesh_lower = trimesh.util.concatenate(pre_mesh_lower)
        post_mesh_upper = trimesh.util.concatenate(post_mesh_upper)
        post_mesh_lower = trimesh.util.concatenate(post_mesh_lower)
        _, pre_to_post_upper = preop2post(
            pre_mesh_upper.as_open3d, post_mesh_upper.as_open3d
        )
        _, pre_to_post_lower = preop2post(
            pre_mesh_lower.as_open3d, post_mesh_lower.as_open3d
        )
        post_to_pre_upper = np.linalg.pinv(pre_to_post_upper)
        post_to_pre_lower = np.linalg.pinv(pre_to_post_lower)

        return {
            "Msg": {
                "data": {
                    "preop_to_postop": {
                        "upper_matrix": pre_to_post_upper.tolist(),
                        "lower_matrix": pre_to_post_lower.tolist(),
                    },
                    "postop_to_preop": {
                        "upper_matrix": post_to_pre_upper.tolist(),
                        "lower_matrix": post_to_pre_lower.tolist(),
                    },
                }
            },
            "Code": 200,
            "State": "Success",
        }
    except Exception as _:
        res = {"Msg": traceback.format_exc(), "Code": 203, "State": "Failure"}
        traceback.print_exc()
        return res
