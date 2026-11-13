import numpy as np
import open3d as o3d
import trimesh

def compute_centroid(vertices):
    """计算三角形顶点的质心"""
    return np.mean(vertices, axis=0)


def find_changed_faces(mesh1, mesh2, threshold=0.05):
    vertices1 = np.array(mesh1.vertices)
    faces1 = np.array(mesh1.faces)

    vertices2 = np.array(mesh2.vertices)
    faces2 = np.array(mesh2.faces)

    # 确保两个网格的面数量相同
    assert faces1.shape == faces2.shape, "两个网格的面数量不一致"

    # 计算每个面的质心
    centroids1 = np.array([compute_centroid(vertices1[face]) for face in faces1])
    centroids2 = np.array([compute_centroid(vertices2[face]) for face in faces2])

    # 计算质心和法向量的差异矩阵
    centroid_diffs = np.linalg.norm(centroids1 - centroids2, axis=1)

    changed_faces = np.where(centroid_diffs > threshold)[0]

    return changed_faces


def analyze_direction_changes_efficient(source_sample, target_sample):
    """
    更高效的向量方向变化分析（使用向量化操作）
    """
    print("\n=== 向量方向变化分析 (高效版本) ===")

    n_points = source_sample.shape[0]

    # 计算所有点对向量
    # 使用广播创建所有向量对
    source_vectors = source_sample[:, np.newaxis, :] - source_sample[np.newaxis, :, :]
    target_vectors = target_sample[:, np.newaxis, :] - target_sample[np.newaxis, :, :]

    # 只保留上三角矩阵的元素（避免重复和自身向量）
    triu_indices = np.triu_indices(n_points, k=1)
    source_vecs = source_vectors[triu_indices]
    target_vecs = target_vectors[triu_indices]

    # 计算向量长度
    source_lengths = np.linalg.norm(source_vecs, axis=1)
    target_lengths = np.linalg.norm(target_vecs, axis=1)

    # 过滤掉长度太小的向量
    valid_mask = (source_lengths > 1e-10) & (target_lengths > 1e-10)
    source_vecs_valid = source_vecs[valid_mask]
    target_vecs_valid = target_vecs[valid_mask]
    source_lengths_valid = source_lengths[valid_mask]
    target_lengths_valid = target_lengths[valid_mask]

    if len(source_vecs_valid) == 0:
        print("警告：没有有效的向量对进行分析")
        return None

    # 归一化向量
    source_norms = source_vecs_valid / source_lengths_valid[:, np.newaxis]
    target_norms = target_vecs_valid / target_lengths_valid[:, np.newaxis]

    # 计算点积（余弦值）
    cos_angles = np.einsum("ij,ij->i", source_norms, target_norms)
    cos_angles = np.clip(cos_angles, -1.0, 1.0)

    # 计算角度变化（度数）
    angle_changes = np.degrees(np.arccos(cos_angles))

    # 计算长度变化比例
    length_ratios = np.abs(target_lengths_valid - source_lengths_valid)

    # 计算统计信息
    stats_info = {
        "max_angle_change": np.max(angle_changes),
        "max_length_ratio": np.max(length_ratios),
    }

    return stats_info

def warning_from_mesh(source, target, angle_threshold=100, length_threshold=1.0):
    changed_faces = find_changed_faces(source,  target)
    max_angle_change = 0
    max_length_ratio = 0
    if len(changed_faces):
        source_o3d = source.as_open3d
        target_o3d = target.as_open3d
        source_o3d = source_o3d.select_by_index(np.unique(source.faces[changed_faces].reshape(-1)))
        target_o3d = target_o3d.select_by_index(np.unique(target.faces[changed_faces].reshape(-1)))
        source_trimesh = trimesh.Trimesh(source_o3d.vertices, source_o3d.triangles)
        target_trimesh = trimesh.Trimesh(target_o3d.vertices, target_o3d.triangles)
        source_split = source_trimesh.split(only_watertight=False)
        target_split = target_trimesh.split(only_watertight=False)
        results = []
        for i in range(len(source_split)):
            result = analyze_direction_changes_efficient(source_split[i].vertices, target_split[i].vertices)
            result['area'] = np.abs(source_split[i].area - target_split[i].area)
            result['area_faces'] = np.max(np.abs(source_split[i].area_faces - target_split[i].area_faces))
            result['integral_mean_curvature'] = np.abs(source_split[i].integral_mean_curvature - target_split[i].integral_mean_curvature)
            results.append(result)
        for res in results:
            if res['max_angle_change'] > max_angle_change:
                max_angle_change = res['max_angle_change']
            if res['max_length_ratio'] > max_length_ratio:
                max_length_ratio = res['max_length_ratio']
    if max_angle_change > angle_threshold or max_length_ratio > length_threshold:
        return True, max_angle_change, max_length_ratio
    else:
        return False, max_angle_change, max_length_ratio