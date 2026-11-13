import MQCompressPy
import trimesh
import base64
import DracoPy
import numpy as np


def compress_drc(mesh, vert_flags=[]):
    # vert_flags = np.zeros(len(mesh.vertices), dtype=np.uint8)
    # vert_flags[points_id] = 1
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
    # return compressed_data
    # with open('mesh.drc', 'wb') as f:
    #     f.write(compressed_data)
    if error_code == 0:
        b64_bytes = base64.b64encode(compressed_data)
        b64_str = b64_bytes.decode("utf-8")
        return b64_str
    else:
        assert "drc compress error"


def decompress_drc(compressed_data):
    # compressed_data = base64.b64decode(compressed_data)
    out_mesh = MQCompressPy.MQC_Mesh()
    out_flags = MQCompressPy.VerticeFlag_UINT8()
    out_mesh, out_flags, error_code = MQCompressPy.decompressMesh_UINT8(compressed_data)
    # out_mesh, out_flags, error_code = MQCompressPy.decompressMesh(compressed_data)
    out_mesh = trimesh.Trimesh(out_mesh.verts, out_mesh.faces)

    return out_mesh, out_flags


def read_mesh_bytes(buffer):
    a = base64.b64decode(buffer)
    mesh_object = DracoPy.decode_buffer_to_mesh(a)
    # V = np.array(mesh_object.points).astype(np.float32).reshape(-1, 3)
    # F = np.array(mesh_object.faces).astype(np.int64).reshape(-1, 3)
    return mesh_object


def srgb_to_rgb_255_from_0_1(srgb):
    """
    Convert sRGB in [0, 1] to linear RGB in [0, 255].
    srgb: numpy array of shape (..., 3) with values in range [0, 1].
    Returns linear RGB array in same shape with values in range [0, 255].
    """
    srgb = srgb.astype(float)  # Ensure computations are in float
    threshold = 0.04045
    linear_rgb = np.where(
        srgb <= threshold, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4
    )
    # Scale to [0, 255] and return as integer values
    return np.clip(linear_rgb * 255, 0, 255).astype(int)


# mesh = trimesh.load("b.stl")
# colors = np.zeros_like(mesh.vertices, dtype=np.uint8)
# colors[:50, 0] = 50
# colors[50:100, 1] = 80
# colors[100:150, 2] = 110
# colors[150:200, 2] = 140
# colors[200:250, 2] = 170
# colors[250:300, 2] = 200
# colors[300:350, 2] = 220
# colors[350:400, 2] = 250
# binary = DracoPy.encode(mesh.vertices, mesh.faces, colors=colors)
# b64_bytes = base64.b64encode(binary)
# b64_str = b64_bytes.decode("utf-8")
# with open("3.txt", "w") as test_file:
#     test_file.write(b64_str)

# points_id = np.zeros(len(mesh.vertices), dtype=np.uint8)
# points_id[:10] = 1
# points_id[10:20] = 2
# points_id[20:25] = 3
# drc = compress_drc(mesh, points_id)

color = ''
a = base64.b64decode(color)
mesh_object = DracoPy.decode_buffer_to_mesh(a)
print
# with open("test.drc", "rb") as f:
#     drc_s = np.fromfile(f, dtype=np.uint8)
# with open("colored.txt", "rb") as f:
#     drc_s = f.read()
# with open("colored.drc", "wb") as f:
#     f.write(base64.b64decode(drc_s))
# m1 = read_mesh_bytes(drc_s)
# with open("2.txt", "rb") as f:
#     drc_s = f.read()
# m2 = read_mesh_bytes(drc_s)
print
# out = decompress_drc(drc_s)
# print(np.array(out[1]))
