import json
import traceback
import base64
import DracoPy
import numpy as np
import trimesh
from crown_cpu import undercut_filling


def read_mesh_bytes(buffer):
    a = base64.b64decode(buffer)
    mesh_object = DracoPy.decode_buffer_to_mesh(a)
    V = np.array(mesh_object.points).astype(np.float32).reshape(-1, 3)
    F = np.array(mesh_object.faces).astype(np.int64).reshape(-1, 3)
    return trimesh.Trimesh(V, F)


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


def write_drc(drc, file):
    with open(file, "wb") as test_file:
        test_file.write(base64.b64decode(drc))


def handler(event, context):
    print("receive case")
    try:
        print("start AI_Crown_CPU_Undercut_Filling ..")
        print("job_id", event.get("job_id"))
        print("event keys", event.keys())
        print("AOI", event.get("AOI"))
        cpu_input_json = {
            "inner": event.get("inner"),
            "AOI_or_UB": event.get("AOI_or_UB"),
            "AOI": event.get("AOI"),
            "prep_extended": event.get("prep_extended"),
        }
        if "cpu_info_json" in event.keys():
            for k, v in event["cpu_info_json"].items():
                if k not in event.keys():
                    event[k] = v
        elif "cpu_std_json" in event.keys():
            for k, v in event["cpu_std_json"].items():
                if k not in event.keys():
                    event[k] = v
        filling_out = undercut_filling(event)
        # filling_out.mesh_beiya.export(os.path.join(context, 'inner.stl'))
        # filling_out.undercut_mesh.export(os.path.join(context, 'vox.stl'))
        if filling_out.AOI_or_UB == 0:
            insert_direction = filling_out.insert_direction.tolist()
        elif filling_out.AOI_or_UB == 1:
            print(len(filling_out.mesh_beiya.vertices))
            mesh_beiya = write_mesh_bytes(filling_out.mesh_beiya)
            insert_direction = filling_out.insert_direction

        if filling_out.AOI_or_UB == 0:
            undercut_json = {
                "AOI": insert_direction,
                "inner": None,
                "cpu_input_json": cpu_input_json,
            }
        elif filling_out.AOI_or_UB == 1:
            undercut_json = {
                "AOI": insert_direction,
                "inner": mesh_beiya,
                "cpu_input_json": cpu_input_json,
            }

        print("suncess undercut")

        return {"Msg": {"data": undercut_json}, "Code": 200, "State": "Success"}
    except Exception as _:
        res = {"Msg": traceback.format_exc(), "Code": 203, "State": "Failure"}
        traceback.print_exc()
        return res


if __name__ == "__main__":
    import time
    import os
    import open3d as o3d

    def read_mesh(path: str) -> o3d.geometry.TriangleMesh:
        mesh = o3d.io.read_triangle_mesh(path)
        mesh.compute_vertex_normals()
        mesh.remove_duplicated_vertices()
        mesh.remove_degenerate_triangles()
        mesh.remove_unreferenced_vertices()
        
        # 新增网格简化逻辑
        target_triangles = 8000
        if len(mesh.triangles) > target_triangles:
            mesh = mesh.simplify_quadric_decimation(target_triangles)
        
        print(len(mesh.vertices))
        # return mesh
        return trimesh.Trimesh(mesh.vertices, mesh.triangles, vertex_normals=mesh.vertex_normals, process=False)
    save_dir = r"test_data_/unercut"
    cases = os.listdir(save_dir)
    for case_id in cases:
        case_id = "d8186235-2ea8-4dc6-88d3-4b4ac71a0a09/under_31577ba2-54f5-4d3f-bc40-59420c28a9e8"
        print(case_id)
        with open(os.path.join(save_dir, case_id, "output.json"), "r") as f:
            event = json.load(f)['cpu_input_json']
        s1 = time.time()
        event["AOI_or_UB"] = 1
        # event["AOI"] = None
        # event["inner"] = event["prep"]
        out = handler(event, os.path.join(save_dir, case_id))
        s2 = time.time()
        print(s2 - s1)
        # event['inner'] = out["Msg"]["data"]['inner']
        with open(os.path.join(save_dir, case_id, "undercut_filling_out.json"), "w") as f:
            f.write(json.dumps(out))
        break
    
    # save_dir = 'test_data_'
    # case_id = '3c8a'
    
    # with open(os.path.join(save_dir, case_id, "undercut_input.json"), "r") as f:
    #     event = json.load(f)
    
    # # with open(os.path.join(save_dir, case_id, "gpu-step-2-result.json"), "r") as f:
    # #     event['prep_extended'] = json.load(f)["prep_extended"]
    # # event["AOI_or_UB"] = 1
    # # with open(os.path.join(save_dir, case_id, "crown_std.json"), "r") as f:
    # #     event_ = json.load(f)
    
    # # with open(os.path.join(save_dir, case_id, "std.json"), "r") as f:
    # #     event_s = json.load(f)
    # # event['prep_extended'] = event_['prep_extended']
    # # event_['cpu_std_json']['cpu_colors_info'] = event_s['cpu_std_json']['cpu_colors_info']
    # # event['cpu_std_json'] = event_['cpu_std_json']
    
    # out = handler(event, os.path.join(save_dir, case_id))
    
    # print