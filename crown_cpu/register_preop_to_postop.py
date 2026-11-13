from pre_op_mirror.pre_op import preop2post
from crown_cpu import read_mesh_bytes
from input_compat import load_input_info, upload_result
import requests
import trimesh
import traceback
import numpy as np


def handler(event, context):
    try:
        if not isinstance(event, dict):
            return {"Msg": "Invalid event format", "Code": 400, "State": "Failure"}

        input_info = load_input_info(event, requests)
        if not isinstance(input_info, dict):
            return {
                "Msg": "Invalid input payload format",
                "Code": 400,
                "State": "Failure",
            }

        preop_teeth_o3d = input_info.get("preop_teeth")
        post_teeth_o3d = input_info.get("postop_teeth")
        preop_teeth_classes = preop_teeth_o3d.get("teeth_classes")
        post_teeth_classes = post_teeth_o3d.get("teeth_classes")
        for k, v in preop_teeth_classes.items():
            if v != "normal" and k in preop_teeth_o3d:
                preop_teeth_o3d.pop(k)
        for k, v in post_teeth_classes.items():
            if v != "normal" and k in post_teeth_o3d:
                post_teeth_o3d.pop(k)
        
        if not preop_teeth_o3d or not post_teeth_o3d:
            return {"Msg": "Missing preop_teeth or postop_teeth data", "Code": 400, "State": "Failure"}
        pre_keys = set(preop_teeth_o3d.keys())
        post_keys = set(post_teeth_o3d.keys())
        intersect_keys = list(pre_keys & post_keys)
        intersect_keys.remove('teeth_classes')        
        pre_mesh_upper = []
        pre_mesh_lower = []
        post_mesh_upper = []
        post_mesh_lower = []
        area_upper_ratio = []
        area_lower_ratio = []
        for key in intersect_keys:
            if key[0] in ["1", "2"]:
                pre_mesh_upper.append(read_mesh_bytes(preop_teeth_o3d[key]))
                post_mesh_upper.append(read_mesh_bytes(post_teeth_o3d[key]))
            else:
                pre_mesh_lower.append(read_mesh_bytes(preop_teeth_o3d[key]))
                post_mesh_lower.append(read_mesh_bytes(post_teeth_o3d[key]))
        for i in range(len(pre_mesh_upper)):
            if pre_mesh_upper[i].area < 100 or post_mesh_upper[i].area < 100:
                area_upper_ratio.append(0)
            else:
                area_upper_ratio.append(pre_mesh_upper[i].area / post_mesh_upper[i].area)
        for i in range(len(pre_mesh_lower)):
            if pre_mesh_lower[i].area < 100 or post_mesh_lower[i].area < 100:
                area_lower_ratio.append(0)
            else:
                area_lower_ratio.append(pre_mesh_lower[i].area / post_mesh_lower[i].area)
        area_upper_ratio = np.array(area_upper_ratio)
        area_lower_ratio = np.array(area_lower_ratio)
        upper_idx = np.where((area_upper_ratio < 1.4) & (area_upper_ratio > 0.6))
        lower_idx = np.where((area_lower_ratio < 1.4) & (area_lower_ratio > 0.6))
        pre_mesh_upper = [pre_mesh_upper[i] for i in upper_idx[0]]
        post_mesh_upper = [post_mesh_upper[i] for i in upper_idx[0]]
        pre_mesh_lower = [pre_mesh_lower[i] for i in lower_idx[0]]
        post_mesh_lower = [post_mesh_lower[i] for i in lower_idx[0]]
        
        if len(pre_mesh_upper) > 0:
            pre_mesh_upper = trimesh.util.concatenate(pre_mesh_upper)
        if len(pre_mesh_lower) > 0:
            pre_mesh_lower = trimesh.util.concatenate(pre_mesh_lower)
        if len(post_mesh_upper) > 0:
            post_mesh_upper = trimesh.util.concatenate(post_mesh_upper)
        if len(post_mesh_lower) > 0:
            post_mesh_lower = trimesh.util.concatenate(post_mesh_lower)
        
        pre_to_post_upper = np.eye(4)
        pre_to_post_lower = np.eye(4)
        post_to_pre_upper = np.eye(4)
        post_to_pre_lower = np.eye(4)
        
        if pre_mesh_upper and post_mesh_upper:
            if area_upper_ratio[upper_idx].size > 0 and area_upper_ratio[upper_idx].mean() > 1:
                _, pre_to_post_upper = preop2post(
                    pre_mesh_upper.as_open3d, post_mesh_upper.as_open3d
                )
                post_to_pre_upper = np.linalg.pinv(pre_to_post_upper)
            else:
                _, post_to_pre_upper = preop2post(
                    post_mesh_upper.as_open3d, pre_mesh_upper.as_open3d
                )
                pre_to_post_upper = np.linalg.pinv(post_to_pre_upper)
        
        if pre_mesh_lower and post_mesh_lower:
            if area_lower_ratio[lower_idx].size > 0 and area_lower_ratio[lower_idx].mean() > 1:
                _, pre_to_post_lower = preop2post(
                    pre_mesh_lower.as_open3d, post_mesh_lower.as_open3d
                )
                post_to_pre_lower = np.linalg.pinv(pre_to_post_lower)
            else:
                _, post_to_pre_lower = preop2post(
                    post_mesh_lower.as_open3d, pre_mesh_lower.as_open3d
                )
                pre_to_post_lower = np.linalg.pinv(post_to_pre_lower)

        result_data = {
            "preop_to_postop": {
                "upper_matrix": pre_to_post_upper.tolist(),
                "lower_matrix": pre_to_post_lower.tolist(),
            },
            "postop_to_preop": {
                "upper_matrix": post_to_pre_upper.tolist(),
                "lower_matrix": post_to_pre_lower.tolist(),
            },
        }

        if event.get("target_url"):
            upload_response = upload_result(
                event.get("target_url"), result_data, requests
            )
            print(upload_response.status_code)
            return {
                "Msg": {"data": "result saved to target url"},
                "Code": 200,
                "State": "Success",
            }

        return {"Msg": {"data": result_data}, "Code": 200, "State": "Success"}
    except Exception as e:
        res = {"Msg": traceback.format_exc(), "Code": 203, "State": "Failure"}
        traceback.print_exc()
        return res
