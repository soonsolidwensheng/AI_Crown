import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
import pymeshlab
import trimesh
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree as sCKDTree
from sklearn.cluster import KMeans
from sklearn.neighbors import NearestNeighbors
from pathlib import Path
import os
import json
from scipy.spatial import transform, KDTree
import time

def align_by_fast_global(crown_mesh, voxel_points):
    """
    快速全局对齐 - 适用于大规模数据集
    简化版，专注于速度和稳定性
    """
    print("开始快速全局对齐...")
    
    # 1. 基于质心和尺寸的快速对齐
    crown_center = np.mean(crown_mesh.vertices, axis=0)
    voxel_center = np.mean(voxel_points, axis=0)
    
    crown_min = np.min(crown_mesh.vertices, axis=0)
    crown_max = np.max(crown_mesh.vertices, axis=0)
    crown_size = crown_max - crown_min
    
    voxel_min = np.min(voxel_points, axis=0)
    voxel_max = np.max(voxel_points, axis=0)
    voxel_size = voxel_max - voxel_min
    
    # 计算缩放
    scale = voxel_size / (crown_size + 1e-10)
    uniform_scale = np.mean(scale)
    
    # 应用变换
    aligned_mesh = crown_mesh.copy()
    V = aligned_mesh.vertices
    
    # 先移到原点，缩放，再移回，最后平移到目标
    V_centered = V - crown_center
    V_scaled = V_centered * uniform_scale
    V_translated = V_scaled + voxel_center
    
    aligned_mesh.vertices = V_translated
    
    # 2. 快速ICP（单阶段）
    try:
        crown_pcd = o3d.geometry.PointCloud()
        crown_pcd.points = o3d.utility.Vector3dVector(aligned_mesh.vertices)
        
        voxel_pcd = o3d.geometry.PointCloud()
        voxel_pcd.points = o3d.utility.Vector3dVector(voxel_points)
        
        crown_pcd.estimate_normals()
        voxel_pcd.estimate_normals()
        
        reg_result = o3d.pipelines.registration.registration_icp(
            crown_pcd, voxel_pcd, 5.0, np.eye(4),
            o3d.pipelines.registration.TransformationEstimationPointToPlane(),
            o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=30)
        )
        
        if reg_result.inlier_rmse < 10.0:  # 合理的误差阈值
            aligned_mesh.apply_transform(reg_result.transformation)
            print(f"快速对齐完成，误差: {reg_result.inlier_rmse:.3f}")
            return aligned_mesh, reg_result.transformation
    except:
        pass
    
    print("快速对齐完成（无ICP精炼）")
    return aligned_mesh, np.eye(4)


def compute_actual_alignment_score(crown_mesh, voxel_points):
    """
    计算实际对齐后的拟合分数 - 使用真实的对齐结果
    """
    try:
        # 使用fast_global进行真实对齐
        aligned_mesh, transform = align_by_fast_global(crown_mesh, voxel_points)
        
        # 计算点到点距离
        tree = KDTree(voxel_points)
        distances, _ = tree.query(aligned_mesh.vertices, k=1)
        
        avg_distance = np.mean(distances)
        max_distance = np.max(distances)
        
        # 计算覆盖率
        tree_crown = KDTree(aligned_mesh.vertices)
        voxel_distances, _ = tree_crown.query(voxel_points, k=1)
        coverage = np.sum(voxel_distances < 2.0) / len(voxel_distances)  # 2mm内视为覆盖
        
        # 计算拟合分数（距离越小分数越高）
        distance_score = 1.0 / (1.0 + avg_distance)
        
        # 综合分数
        fitness_score = (distance_score * 0.6) + (coverage * 0.4)
        
        return {
            'fitness_score': fitness_score,
            'avg_distance': avg_distance,
            'max_distance': max_distance,
            'coverage': coverage,
            'aligned_mesh': aligned_mesh,
            'transform': transform
        }
        
    except Exception as e:
        print(f"对齐失败: {e}")
        return {
            'fitness_score': 0.0,
            'avg_distance': float('inf'),
            'max_distance': float('inf'),
            'coverage': 0.0,
            'aligned_mesh': crown_mesh.copy(),
            'transform': np.eye(4)
        }


def select_best_crown_with_real_alignment(crown_meshes, voxel_points, selection_method="fitness", crown_names=None):
    """
    使用真实的对齐结果选择最合适的标准牙冠
    
    参数:
        crown_meshes: 标准牙冠网格对象列表 [mesh1, mesh2, mesh3, ...]
        voxel_model_path: 体素模型文件路径
        selection_method: 选择方法，可选：fitness, features, hybrid
        crown_names: 牙冠名称列表（可选，用于标识）
        
    返回:
        best_crown_index: 最佳牙冠索引
        best_crown_mesh: 最佳牙冠网格
        best_score: 最佳分数
        all_results: 所有牙冠的对齐结果
    """
    print("找到 {} 个标准牙冠网格".format(len(crown_meshes)))
    
    print("加载体素模型...")
    print("   体素点数: {}".format(len(voxel_points)))
    
    results = []
    
    for i, crown_mesh in enumerate(crown_meshes):
        try:
            # 使用提供的名称或生成默认名称
            if crown_names and i < len(crown_names):
                crown_name = crown_names[i]
            else:
                crown_name = f"crown_{i+1}"
            
            print(f"\n评估牙冠 {i+1}/{len(crown_meshes)}: {crown_name}")
            print(f"   顶点数: {len(crown_mesh.vertices)}")
            
            # 计算实际对齐分数
            start_time = time.time()
            score_info = compute_actual_alignment_score(crown_mesh, voxel_points)
            elapsed_time = time.time() - start_time
            
            # 添加额外信息
            score_info['name'] = crown_name
            score_info['index'] = i
            score_info['vertex_count'] = len(crown_mesh.vertices)
            score_info['elapsed_time'] = elapsed_time
            
            results.append(score_info)
            
            print(f"   拟合度: {score_info['fitness_score']:.4f}")
            print(f"   平均距离: {score_info['avg_distance']:.2f} mm")
            print(f"   覆盖率: {score_info['coverage']:.1%}")
            print(f"   处理时间: {elapsed_time:.2f} 秒")
            
        except Exception as e:
            print(f"   评估失败: {e}")
            crown_name = crown_names[i] if (crown_names and i < len(crown_names)) else f"crown_{i+1}"
            results.append({
                'name': crown_name,
                'index': i,
                'fitness_score': 0.0,
                'avg_distance': float('inf'),
                'max_distance': float('inf'),
                'coverage': 0.0,
                'elapsed_time': 0.0
            })
    
    # 根据选择方法进行排序
    if selection_method == "fitness":
        # 按拟合度排序（分数越高越好）
        results.sort(key=lambda x: x['fitness_score'], reverse=True)
        print("使用拟合度选择方法")
    elif selection_method == "features":
        # 按特征综合评分（可以考虑添加更多特征）
        for result in results:
            # 特征综合评分：拟合度权重 + 距离权重
            feature_score = result['fitness_score'] * 0.7 + (1.0 - min(result['avg_distance'] / 10.0, 1.0)) * 0.3
            result['feature_score'] = feature_score
        results.sort(key=lambda x: x['feature_score'], reverse=True)
        print("使用特征选择方法")
    elif selection_method == "hybrid":
        # 混合方法：结合拟合度和覆盖率
        for result in results:
            # 混合评分：拟合度 + 覆盖率
            hybrid_score = result['fitness_score'] * 0.6 + result['coverage'] * 0.4
            result['hybrid_score'] = hybrid_score
        results.sort(key=lambda x: x['hybrid_score'], reverse=True)
        print("使用混合选择方法")
    else:
        # 默认使用拟合度
        results.sort(key=lambda x: x['fitness_score'], reverse=True)
    
    # 选择最佳牙冠
    best_result = results[0]
    best_crown_index = best_result['index']
    
    # 获取最佳牙冠网格（使用已对齐的版本）
    best_crown_mesh = best_result['aligned_mesh']
    
    print("\n" + "=" * 60)
    print("选择结果:")
    print("=" * 60)
    print(f"   最佳牙冠: {best_result['name']} (索引: {best_crown_index})")
    print(f"   拟合度分数: {best_result['fitness_score']:.4f}")
    print(f"   平均距离: {best_result['avg_distance']:.2f} mm")
    print(f"   覆盖率: {best_result['coverage']:.1%}")
    
    print("\n所有牙冠排名:")
    for i, result in enumerate(results[:5]):  # 显示前5名
        print(f"   {i+1}. {result['name']}: {result['fitness_score']:.4f}")
    
    return best_crown_index, best_crown_mesh, best_result['fitness_score'], results

def clean_results_for_json(results):
    """清理结果数据，移除不能序列化的对象"""
    cleaned_results = []
    for result in results:
        cleaned = result.copy()
        # 移除不能序列化的对象
        cleaned.pop('aligned_mesh', None)
        cleaned.pop('transform', None)
        cleaned_results.append(cleaned)
    return cleaned_results

def select_and_align_crowns_v2(crown_meshes, voxel_model,
                              selection_method="hybrid", crown_names=None):
    """
    选择最合适标准牙冠并进行对齐 - 改进版主函数
    
    参数:
        crown_meshes: 标准牙冠网格对象列表 [mesh1, mesh2, mesh3, ...]
        voxel_model: 体素模型points对象
        output_dir: 输出目录路径
        selection_method: 牙冠选择方法，可选: fitness, features, hybrid
        crown_names: 牙冠名称列表（可选，用于标识）
        
    返回:
        aligned_mesh: 对齐后的牙冠网格
        selection_info: 选择过程信息
    """
    print("=" * 60)
    print("选择最合适标准牙冠（改进版）")
    print("=" * 60)
    
    # 验证输入
    if not crown_meshes or len(crown_meshes) == 0:
        raise ValueError("crown_meshes 不能为空列表")
    
    print(f"接收到 {len(crown_meshes)} 个标准牙冠网格")
    
    # 使用真实对齐结果选择最佳牙冠
    best_crown_index, best_crown_mesh, best_score, all_results = select_best_crown_with_real_alignment(
        crown_meshes, voxel_model, selection_method, crown_names
    )
    
    # 清理结果用于JSON序列化
    cleaned_results = clean_results_for_json(all_results)
    
    # 获取最佳牙冠名称
    best_crown_name = crown_names[best_crown_index] if (crown_names and best_crown_index < len(crown_names)) else f"crown_{best_crown_index+1}"
    
    # 保存选择信息
    selection_info = {
        'best_crown': {
            'name': best_crown_name,
            'index': best_crown_index,
            'fitness_score': best_score,
            'avg_distance': all_results[0]['avg_distance'],
            'coverage': all_results[0]['coverage']
        },
        'all_results': cleaned_results,
        'timestamp': time.time(),
        'crown_count': len(crown_meshes)
    }
    
    
    aligned_mesh = all_results[0]['aligned_mesh']
    
    print("\n" + "=" * 60)
    print("选择完成！")
    print("=" * 60)
    
    return aligned_mesh, selection_info


class SingleCrownMatcher:
    """单案例牙冠匹配器"""
    
    # 标准牙类型映射表
    CROWN_TYPE_MAPPING = {
        "Generic Standard v1": {
            "name": "Generic Standard v1",
            "short": "gs",
            "dir": "Generic Standard v1"
        },
        "Cyber Standard v1": {
            "name": "Cyber Standard v1", 
            "short": "cs",
            "dir": "Cyber Standard v1"
        },
        "Mature v1": {
            "name": "Mature v1",
            "short": "mt",
            "dir": "Mature v1"
        },
        "Soft Standard v1": {
            "name": "Soft Standard v1",
            "short": "ss",
            "dir": "Soft Standard v1"
        },
        "Youth v1": {
            "name": "Youth v1",
            "short": "yt",
            "dir": "Youth v1"
        },
        "st_tooth": {
            "name": "st_tooth",
            "short": "st",
            "dir": "st_tooth"
        }
    }
    
    def __init__(self, config_dir):
        """
        初始化单案例匹配器
        
        参数:
            config_dir: 标准牙冠配置目录
        """
        self.config_dir = Path(config_dir)
        
        if not self.config_dir.exists():
            raise ValueError(f"配置目录不存在: {self.config_dir}")
        
        print(f"📁 配置目录: {self.config_dir}")
    
    def get_crown_path(self, crown_type_short, tooth_id):
        """
        获取指定标准牙类型和牙号的牙冠文件路径
        
        参数:
            crown_type_short: 标准牙类型简写 (gs, cs, mt, ss, yt, st)
            tooth_id: 牙号 (如: 46)
            
        返回:
            crown_path: 牙冠文件路径
        """
        # 查找对应的类型信息
        type_info = None
        for crown_type, info in self.CROWN_TYPE_MAPPING.items():
            if info["short"] == crown_type_short:
                type_info = info
                break
        
        if not type_info:
            raise ValueError(f"未知的标准牙类型简写: {crown_type_short}")
        
        type_dir = self.config_dir / type_info["dir"]
        
        if not type_dir.exists():
            raise ValueError(f"标准牙类型目录不存在: {type_dir}")
        
        # 根据类型确定文件名模式
        if crown_type_short == "st":
            crown_file = type_dir / f"{tooth_id}.stl"
        else:
            crown_file = type_dir / f"{tooth_id} FDI.stl"
        
        if not crown_file.exists():
            raise ValueError(f"牙冠文件不存在: {crown_file}")
        
        return str(crown_file)
    def process_all_types(self, voxel_model, tooth_id,
                         selection_method="hybrid"):
        """
        对所有标准牙类型进行匹配，返回最佳结果
        
        参数:
            voxel_model: 体素模型
            tooth_id: 牙号
            output_dir: 输出目录（可选）
            selection_method: 选择方法
            
        返回:
            best_result: 最佳匹配结果信息
        """
        
        print(f"\n{'='*60}")
        print(f"🔬 单案例全类型牙冠匹配")
        print(f"{'='*60}")
        print(f"🦷 牙号: {tooth_id}")
        
        results = []
        
        # 遍历所有标准牙类型
        for crown_type, type_info in self.CROWN_TYPE_MAPPING.items():
            crown_type_short = type_info["short"]
            
            try:
                print(f"\n📋 处理标准牙类型: {crown_type}")
                
                # 获取牙冠路径
                try:
                    crown_path = self.get_crown_path(crown_type_short, tooth_id)
                except ValueError as e:
                    print(f"   ⚠️ 跳过: {e}")
                    continue
                
                # 加载配置并生成旋转网格
                with open(f'{os.path.dirname(crown_path)}/config.json', 'r') as f:
                    config = json.load(f)
                
                cross_points = config[tooth_id]['cross_points']
                mesh = trimesh.load(crown_path)
                mesh1 = mesh.copy()
                mesh2 = mesh.copy()
                mesh3 = mesh.copy()
                
                v_occl = mesh.vertices[cross_points[0]] - mesh.vertices[cross_points[1]]
                v_misial = mesh.vertices[cross_points[2]] - mesh.vertices[cross_points[3]]
                v_ac = mesh.vertices[cross_points[4]] - mesh.vertices[cross_points[5]]
                
                frameA_1 = np.array([v_occl, v_misial])
                frameB_1 = np.array([[0, 1, 0], [1, 0, 0]])
                frameA_2 = np.array([v_ac, v_misial])
                frameB_2 = np.array([[0, 0, 1], [1, 0, 0]])
                frameA_3 = np.array([v_occl, v_ac])
                frameB_3 = np.array([[0, 1, 0], [0, 0, 1]])
                weights = np.array([0.5, 0.5])
                
                def rot(frameA, frameB, weights):
                    rot_mat, _ = transform.Rotation.align_vectors(frameA, frameB, weights=weights)
                    rot_matrix = np.eye(4)
                    rot_matrix[:3, :3] = rot_mat.as_matrix()
                    rot_matrix[:, 3] = [0, 0, 0, 1]
                    return rot_matrix
                
                mesh1.apply_transform(np.linalg.pinv(rot(frameA_1, frameB_1, weights)))
                mesh2.apply_transform(np.linalg.pinv(rot(frameA_2, frameB_2, weights)))
                mesh3.apply_transform(np.linalg.pinv(rot(frameA_3, frameB_3, weights)))
                
                # 执行匹配
                start_time = time.time()
                
                
                aligned_mesh, selection_info = select_and_align_crowns_v2(
                    crown_meshes=[mesh1, mesh2, mesh3],
                    voxel_model=voxel_model,
                    selection_method=selection_method,
                    crown_names=["orientation_1", "orientation_2", "orientation_3"]
                )
                
                elapsed_time = time.time() - start_time
                
                result = {
                    "crown_type": crown_type,
                    "crown_type_short": crown_type_short,
                    "fitness_score": selection_info['best_crown']['fitness_score'],
                    "avg_distance": selection_info['best_crown']['avg_distance'],
                    "coverage": selection_info['best_crown']['coverage'],
                    "best_orientation": selection_info['best_crown']['name'],
                    "elapsed_time": elapsed_time,
                    "success": True
                }
                result['_aligned_mesh'] = aligned_mesh
                results.append(result)
                
                print(f"   ✅ 拟合度: {result['fitness_score']:.4f}")
                
            except Exception as e:
                print(f"   ❌ 失败: {e}")
                results.append({
                    "crown_type": crown_type,
                    "crown_type_short": crown_type_short,
                    "error": str(e),
                    "success": False
                })
        
        # 找出最佳结果
        successful_results = [r for r in results if r.get("success", False)]
        if not successful_results:
            raise RuntimeError("所有标准牙类型匹配均失败")
        
        best_result = max(successful_results, key=lambda x: x['fitness_score'])
        
        # 打印汇总
        print(f"\n{'='*60}")
        print(f"📊 匹配汇总")
        print(f"{'='*60}")
        for r in sorted(successful_results, key=lambda x: x['fitness_score'], reverse=True):
            print(f"   {r['crown_type_short']}: {r['fitness_score']:.4f}")
        print(f"\n最佳: {best_result['crown_type']} (拟合度: {best_result['fitness_score']:.4f})")
        
        return best_result

def adaptive_sparse_pointcloud_to_mesh(points, point_distance_threshold=0.205):
    """
    自适应稀疏点云转网格，包含更详细的参数级别
    """
    # 分析点云密度

    points = np.array(points)
    # nbrs = NearestNeighbors(n_neighbors=10).fit(points)
    # distances, _ = nbrs.kneighbors(points)
    # pc_points = points[
    #     np.where(np.mean(distances, axis=1) > point_distance_threshold)[0]
    # ]
    # pc = trimesh.PointCloud(pc_points)
    pc = trimesh.PointCloud(points)
    ms_mesh = pymeshlab.Mesh(pc.vertices)
    ms = pymeshlab.MeshSet()
    ms.add_mesh(ms_mesh)
    ms.generate_surface_reconstruction_ball_pivoting()
    print("    平滑中...")
    ms.apply_coord_taubin_smoothing()
    print("    补洞中...")
    ms.meshing_close_holes()
    return trimesh.Trimesh(
        ms.current_mesh().vertex_matrix(),
        ms.current_mesh().face_matrix(),
        process=False,
    )


def getBoundaryPoints(mesh):
    """get the boundary points of a mesh IN THE ORDER of how they appear in the mesh"""
    if type(mesh) is not trimesh.Trimesh:
        mesh = trimesh.Trimesh(mesh.vertices, mesh.triangles)
    unique_elements, counts = np.unique(mesh.edges_sorted, return_counts=True, axis=0)
    edges = unique_elements[np.where(counts == 1)[0]]
    boundary_point_id = np.unique(edges.flatten())
    boundary_point = mesh.vertices[boundary_point_id]
    return boundary_point, boundary_point_id


def _split_with_neck_removal(sub_adj_neck, sub_adj_full, density_local, min_nb):
    """
    细颈剥离后求连通组件。
    - sub_adj_neck: 小半径子图，用于判断颈部点与连通关系
    - sub_adj_full: 大半径子图，用于颈部点归回投票
    返回与子图点数等长的组件编号数组（从 0 开始）。
    """
    n_sub = sub_adj_neck.shape[0]
    core_idx = np.where(density_local >= min_nb)[0]

    if len(core_idx) == 0:
        _, cc_lab = connected_components(sub_adj_neck, directed=False)
        return cc_lab

    core_adj = sub_adj_neck[core_idx][:, core_idx]
    n_cc, cc_lab_core = connected_components(core_adj, directed=False)

    cc_label = np.full(n_sub, -1, dtype=int)
    cc_label[core_idx] = cc_lab_core

    neck_idx = np.where(cc_label == -1)[0]
    for _ in range(n_sub):
        unresolved = neck_idx[cc_label[neck_idx] == -1]
        if len(unresolved) == 0:
            break
        changed = False
        for li in unresolved:
            assigned = cc_label[sub_adj_full[li].indices]
            assigned = assigned[assigned >= 0]
            if len(assigned) == 0:
                continue
            cc_label[li] = np.bincount(assigned, minlength=n_cc).argmax()
            changed = True
        if not changed:
            break

    for li in np.where(cc_label == -1)[0]:
        cc_label[li] = n_cc
        n_cc += 1

    return cc_label


def _build_adj(pairs, n_pts):
    """根据点对列表构建对称稀疏邻接矩阵。"""
    return csr_matrix(
        (
            np.ones(len(pairs) * 2),
            (
                np.concatenate([pairs[:, 0], pairs[:, 1]]),
                np.concatenate([pairs[:, 1], pairs[:, 0]]),
            ),
        ),
        shape=(n_pts, n_pts),
    )


def segment_crown_regions(
    mesh,
    # ---------- KMeans 聚类参数 ----------
    n_clusters=7,  # 聚类数（对应 7 个牙冠区域）
    norm_weight=2.0,  # 法向量特征权重
    xyz_weight=0.2,  # 空间坐标特征权重
    normal_radius=1.5,  # 法向量估计半径
    normal_max_nn=30,  # 法向量估计最大邻居数
    kmeans_n_init=30,  # KMeans 初始化次数
    kmeans_max_iter=500,  # KMeans 最大迭代次数
    kmeans_seed=42,  # KMeans 随机种子
    # ---------- 细颈检测参数 ----------
    r_neck=0.5,  # 细颈检测半径（小）
    min_nb_count=15,  # r_neck 内邻居数低于此值视为颈部点
    # ---------- 碎块吞并参数 ----------
    r_connect=1,  # 吞并投票半径（大）
    max_iter=5,  # 吞并最大迭代轮数
    # ---------- 边界修正参数 ----------
    boundary_ratio=0.15,  # 本区域邻居占比低于此值时重新归类
    # ---------- 调试输出路径（None 则不保存）----------
    debug_cc_path="clustered_cc_before_merge.ply",
    debug_merged_path="clustered_scene_merged.ply",
    debug_result_path="clustered_scene.ply",
):
    """
    对牙冠网格进行区域分割，返回 7 个区域的子网格字典。

    参数
    ----
    mesh : trimesh.Trimesh
        输入牙冠网格。
    n_clusters : int
        聚类数，默认 7（bottom / mesial / distal / lingual / buccal /
        occlusal_lingual / occlusal_buccal）。
    norm_weight : float
        KMeans 特征中法向量的权重，默认 2.0。
    xyz_weight : float
        KMeans 特征中归一化空间坐标的权重，默认 0.5。
    normal_radius : float
        法向量估计的搜索半径，默认 1.5。
    normal_max_nn : int
        法向量估计的最大邻居数，默认 30。
    kmeans_n_init : int
        KMeans 重复初始化次数，默认 30。
    kmeans_max_iter : int
        KMeans 单次最大迭代步数，默认 500。
    kmeans_seed : int
        KMeans 随机种子，默认 42。
    r_neck : float
        细颈检测用的小半径，默认 0.5。
    min_nb_count : int
        r_neck 内邻居数低于此值的点视为颈部，默认 15。
    r_connect : float
        碎块吞并投票及边界修正用的大半径，默认 1.5。
    min_cc_size : int
        小于此点数的连通组件视为碎块并被吞并，默认 200。
    max_iter : int
        吞并与边界修正各自的最大迭代轮数，默认 5。
    boundary_ratio : float
        本区域邻居占比低于此值时将该点归入占比最多的邻域区域，默认 0.25。
    debug_cc_path : str or None
        吞并前连通组件可视化保存路径，None 则不保存。
    debug_merged_path : str or None
        碎块吞并后中间结果保存路径，None 则不保存。
    debug_result_path : str or None
        最终分割结果可视化保存路径，None 则不保存。

    返回
    ----
    dict，键为区域名称，值为对应的 trimesh.Trimesh 子网格：
        "bottom", "mesial", "distal", "lingual", "buccal",
        "occlusal_lingual", "occlusal_buccal"
    """
    k = n_clusters

    # 1) 估计法向量
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.array(mesh.vertices))
    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(
            radius=normal_radius, max_nn=normal_max_nn
        )
    )
    pcd.orient_normals_consistent_tangent_plane(normal_max_nn)

    norm = np.asarray(pcd.normals)
    xyz = np.asarray(pcd.points)

    # 2) KMeans 聚类
    xyz_norm = (xyz - xyz.mean(axis=0)) / (xyz.std() + 1e-8)
    feat = np.hstack([norm * norm_weight, xyz_norm * xyz_weight])
    kmeans = KMeans(
        n_clusters=k,
        n_init=kmeans_n_init,
        max_iter=kmeans_max_iter,
        random_state=kmeans_seed,
    ).fit(feat)
    labels = kmeans.labels_

    if debug_result_path:
        pcd.colors = o3d.utility.Vector3dVector(plt.cm.tab20(labels / 20.0)[:, :3])
        o3d.io.write_point_cloud(debug_result_path.replace(".ply", "_kmeans.ply"), pcd)

    # 3) 构建邻接矩阵
    n_pts = len(xyz)
    sktree = sCKDTree(xyz)

    pairs_neck = sktree.query_pairs(r=r_neck, output_type="ndarray")
    adj_neck = _build_adj(pairs_neck, n_pts)

    pairs_all = sktree.query_pairs(r=r_connect, output_type="ndarray")
    adj_full = _build_adj(pairs_all, n_pts)

    local_density = np.array(adj_neck.sum(axis=1)).ravel()

    # 4) 吞并前连通组件可视化
    if debug_cc_path:
        cc_colors = np.zeros((n_pts, 3))
        for lab in range(k):
            mask_idx = np.where(labels == lab)[0]
            if len(mask_idx) == 0:
                continue
            cc_lab = _split_with_neck_removal(
                adj_neck[mask_idx][:, mask_idx],
                adj_full[mask_idx][:, mask_idx],
                local_density[mask_idx],
                min_nb_count,
            )
            base_color = np.array(plt.cm.tab20(lab / 20.0)[:3])
            cc_ids = np.unique(cc_lab)
            n_cc_local = len(cc_ids)
            for j, cc_id in enumerate(cc_ids):
                # 同一 label 下多个连通组件：主组件用原色，其余组件亮度递减
                factor = (
                    1.0 - 0.5 * (j / max(n_cc_local - 1, 1)) if n_cc_local > 1 else 1.0
                )
                cc_colors[mask_idx[cc_lab == cc_id]] = np.clip(
                    base_color * factor, 0, 1
                )

        pcd_cc = o3d.geometry.PointCloud()
        pcd_cc.points = o3d.utility.Vector3dVector(xyz)
        pcd_cc.colors = o3d.utility.Vector3dVector(cc_colors)
        o3d.io.write_point_cloud(debug_cc_path, pcd_cc)
        print(f"吞并前连通组件已保存到 {debug_cc_path}")

    # 5) 碎块吞并：保留点数最多的 k 个连通组件，其余吞并到邻域多数 label
    labels = labels.copy()
    for it in range(max_iter):
        # 收集所有连通组件及其全局点索引
        all_ccs = []  # list of (size, global_pts_array, label)
        for lab in range(k):
            mask_idx = np.where(labels == lab)[0]
            if len(mask_idx) == 0:
                continue
            cc_lab = _split_with_neck_removal(
                adj_neck[mask_idx][:, mask_idx],
                adj_full[mask_idx][:, mask_idx],
                local_density[mask_idx],
                min_nb_count,
            )
            for cc_id in np.unique(cc_lab):
                cc_pts_global = mask_idx[cc_lab == cc_id]
                all_ccs.append((len(cc_pts_global), cc_pts_global, lab))

        # 按点数降序排列，前 k 个为保留组件，其余为碎块
        all_ccs.sort(key=lambda x: x[0], reverse=True)
        keep_set = set(id(c) for c in all_ccs[:k])
        debris = [c for c in all_ccs if id(c) not in keep_set]

        change_cnt = 0
        new_labels = labels.copy()
        for _, cc_pts_global, lab in debris:
            for gi in cc_pts_global:
                nb_labels = labels[adj_full[gi].indices]
                other = nb_labels[nb_labels != lab]
                if len(other) == 0:
                    continue
                new_labels[gi] = np.bincount(other, minlength=k).argmax()
                change_cnt += 1
        labels = new_labels
        print(f"吞并 iter {it + 1}: 吞并点数 {change_cnt}")
        if change_cnt == 0:
            break

    # 5.5) 保存碎块吞并后中间结果
    if debug_merged_path:
        pcd_merged = o3d.geometry.PointCloud()
        pcd_merged.points = o3d.utility.Vector3dVector(xyz)
        pcd_merged.colors = o3d.utility.Vector3dVector(
            plt.cm.tab20(labels / 20.0)[:, :3]
        )
        o3d.io.write_point_cloud(debug_merged_path, pcd_merged)
        print(f"碎块吞并后中间结果已保存到 {debug_merged_path}")

    # 6) 边界修正
    for it in range(max_iter):
        change_cnt = 0
        new_labels = labels.copy()
        for i in range(n_pts):
            nb_idx = adj_full[i].indices
            if len(nb_idx) == 0:
                continue
            nb_labels = labels[nb_idx]
            if np.sum(nb_labels == labels[i]) / len(nb_labels) < boundary_ratio:
                new_labels[i] = np.bincount(nb_labels, minlength=k).argmax()
                change_cnt += 1
        labels = new_labels
        print(f"边界修正 iter {it + 1}: 修正点数 {change_cnt}")
        if change_cnt == 0:
            break

    # 7) 保存最终结果可视化
    if debug_result_path:
        pcd.colors = o3d.utility.Vector3dVector(plt.cm.tab20(labels / 20.0)[:, :3])
        o3d.io.write_point_cloud(debug_result_path, pcd)

    # 8) 按空间均值分配区域语义
    mesh_o3d = mesh.as_open3d
    parts = [mesh_o3d.select_by_index(np.where(labels == i)[0]) for i in range(k)]
    means = np.array([np.mean(np.asarray(p.vertices), axis=0) for p in parts])

    bottom_id = int(np.argmin(means[:, 1]))
    mesial_id = int(np.argmax(means[:, 0]))
    distal_id = int(np.argmin(means[:, 0]))
    lingual_id = int(np.argmin(means[:, 2]))
    buccal_id = int(np.argmax(means[:, 2]))

    used = {bottom_id, mesial_id, distal_id, lingual_id, buccal_id}
    occ_ids = sorted(
        [i for i in range(k) if i not in used], key=lambda i: means[i, 1], reverse=True
    )[:2]

    if means[occ_ids[0], 2] < means[occ_ids[1], 2]:
        occ_lingual_id, occ_buccal_id = occ_ids[0], occ_ids[1]
    else:
        occ_lingual_id, occ_buccal_id = occ_ids[1], occ_ids[0]

    def _to_trimesh(p):
        return trimesh.Trimesh(
            vertices=np.asarray(p.vertices), faces=np.asarray(p.triangles)
        )

    region_ids = {
        "bottom": bottom_id,
        "mesial": mesial_id,
        "distal": distal_id,
        "lingual": lingual_id,
        "buccal": buccal_id,
        "occlusal_lingual": occ_lingual_id,
        "occlusal_buccal": occ_buccal_id,
    }

    # 收集每个区域的边缘点（boundary：仅属于一条三角形边的顶点）
    boundary_pts_list = []
    boundary_labels = []
    for name, rid in region_ids.items():
        region_mesh = _to_trimesh(parts[rid])
        bpts, _ = getBoundaryPoints(region_mesh)
        boundary_pts_list.append(bpts)
        boundary_labels.extend([name] * len(bpts))

    all_boundary_pts = np.vstack(boundary_pts_list)  # (M, 3)

    return all_boundary_pts, boundary_labels


def compute_similarity_transform(
    src: np.ndarray, dst: np.ndarray, with_scale: bool = True
):
    """
    计算将 src 映射到 dst 的最佳相似变换（Umeyama 风格）:
        dst ≈ s * R * src + t
    返回 s, R(3x3), t(3,)
    """
    assert src.shape == dst.shape and src.shape[1] == 3
    n = src.shape[0]
    mean_src = src.mean(axis=0)
    mean_dst = dst.mean(axis=0)

    X = src - mean_src
    Y = dst - mean_dst

    Sigma = (Y.T @ X) / n

    U, D, Vt = np.linalg.svd(Sigma)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        Vt[2, :] *= -1
        R = U @ Vt

    if with_scale:
        var_src = (X * X).sum() / n
        s = D.sum() / (var_src + 1e-12)
    else:
        s = 1.0

    t = mean_dst - s * (R @ mean_src)
    return s, R, t


def pose_align(
    line_corners: np.ndarray,
    mesh_s: trimesh.Trimesh,
    pose_use_scale: bool = True,
    pose_max_pair_dist: float = 3.0,
) -> trimesh.Trimesh:
    """
    只做"姿态对齐"，不做非刚性形变。
    """
    V = mesh_s.vertices.copy()

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(V)
    tree = o3d.geometry.KDTreeFlann(pcd)

    src_pts = []
    dst_pts = []

    for p in line_corners:
        _, idx, dist2 = tree.search_knn_vector_3d(p, 1)
        vid = idx[0]
        d = np.sqrt(dist2[0])
        if d > pose_max_pair_dist:
            continue
        src_pts.append(V[vid])
        dst_pts.append(p)

    if len(src_pts) < 3:
        return mesh_s.copy()

    src_pts = np.asarray(src_pts)
    dst_pts = np.asarray(dst_pts)

    s, R, t = compute_similarity_transform(src_pts, dst_pts, with_scale=pose_use_scale)

    V_new = (s * (R @ V.T)).T + t
    mesh_new = mesh_s.copy()
    mesh_new.vertices = V_new
    return mesh_new


def build_uniform_laplacian(num_vertices: int, faces: np.ndarray) -> np.ndarray:
    L = np.zeros((num_vertices, num_vertices), dtype=np.float64)
    for tri in faces:
        i, j, k = tri
        edges = [(i, j), (j, k), (k, i)]
        for a, b in edges:
            if a == b:
                continue
            L[a, a] += 1.0
            L[b, b] += 1.0
            L[a, b] -= 1.0
            L[b, a] -= 1.0
    return L


def build_mesh_pcd_from_mesh(mesh: trimesh.Trimesh):
    """将 trimesh 转为 o3d 点云和网格，供 ICP / TPS 等使用。"""
    mesh_o3d = o3d.geometry.TriangleMesh()
    mesh_o3d.vertices = o3d.utility.Vector3dVector(mesh.vertices)
    mesh_o3d.triangles = o3d.utility.Vector3iVector(mesh.faces)
    mesh_o3d.compute_vertex_normals()

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(mesh.vertices)
    pcd.normals = o3d.utility.Vector3dVector(mesh.vertex_normals)
    return mesh_o3d, pcd


def estimate_normals_for_pcd(pcd: o3d.geometry.PointCloud, radius=1.0, max_nn=1000):
    search_param = o3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=max_nn)
    pcd.estimate_normals(search_param=search_param)
    pcd.orient_normals_consistent_tangent_plane(30)
    return pcd


def subsample_points(points: np.ndarray, step: int) -> np.ndarray:
    """简单按步长下采样边界点，保证顺序不变。"""
    if step <= 1 or len(points) <= 1:
        return points
    return points[::step]


def nonrigid_icp_lap(
    line_corners: np.ndarray,
    mesh_s: trimesh.Trimesh,
    actual_mesh: trimesh.Trimesh,
    nr_icp_iter: int = 1,
    nr_data_w: float = 5.0,
    nr_handle_w: float = 2.0,
    nr_subsample_boundary: int = 6,
    nr_max_handle_move: float = 0.5,
    nr_laplace_w: float = 50.0,
    nr_samples_for_data: int = 4000,
    icp_voxel_size: float = 0.1,
    icp_max_corr_dist: float = 2.0,
) -> trimesh.Trimesh:
    """
    非刚性 ICP + 拉普拉斯先验的网格变形

    Parameters
    ----------
    line_corners : np.ndarray
        边界角点数组，用于定义变形控制点的位置。
    mesh_s : trimesh.Trimesh
        源网格（模板网格），待变形的初始网格模型。
    actual_mesh : trimesh.Trimesh
        目标网格（实际牙齿扫描数据），变形的目标参考。
    nr_icp_iter : int, optional
        非刚性 ICP 外层迭代次数，默认 1。控制整体变形迭代优化轮数。
    nr_data_w : float, optional
        数据项（Data term）权重，默认 5.0。控制变形后顶点与目标点云的接近程度，
        值越大变形结果越贴近目标网格。
    nr_handle_w : float, optional
        控制点（Handle）权重，默认 2.0。控制边界控制点对变形的约束强度，
        值越大边界控制点位置越被严格约束。
    nr_subsample_boundary : int, optional
        边界点下采样步长，默认 6。每隔 6 个点取一个作为控制点，
        用于平衡计算效率与变形精度。
    nr_max_handle_move : float, optional
        控制点最大单次移动距离，默认 0.5。限制控制点每次迭代的最大位移，
        防止变形过于剧烈导致网格自交或畸形。
    nr_laplace_w : float, optional
        拉普拉斯平滑权重，默认 50.0。约束网格变形的平滑性，
        值越大变形后网格越保持原始的局部几何特征。
    nr_samples_for_data : int, optional
        目标点云采样点数，默认 4000。从 actual_mesh 采样的点数，
        用于计算数据项损失。
    icp_voxel_size : float, optional
        ICP 下采样体素大小，默认 0.1。用于 ICP 配准前的点云下采样体素化，
        值越小配准精度越高但计算量增大。
    icp_max_corr_dist : float, optional
        ICP 最大对应点距离，默认 0.5。ICP 迭代中认为对应的最大距离阈值，
        超过该距离的点对不参与配准。

    Returns
    -------
    trimesh.Trimesh
        变形后的网格模型。
    """
    V0 = mesh_s.vertices.copy()
    F = mesh_s.faces
    N = V0.shape[0]

    L = build_uniform_laplacian(N, F)
    A_lap = nr_laplace_w * (L.T @ L) + 1e-6 * np.eye(N)
    B_lap = nr_laplace_w * (L.T @ (L @ V0))

    actual_o3d = o3d.geometry.TriangleMesh()
    actual_o3d.vertices = o3d.utility.Vector3dVector(actual_mesh.vertices)
    actual_o3d.triangles = o3d.utility.Vector3iVector(actual_mesh.faces)
    actual_pcd = actual_o3d.sample_points_uniformly(
        number_of_points=nr_samples_for_data
    )
    actual_tree = o3d.geometry.KDTreeFlann(actual_pcd)
    actual_points = np.asarray(actual_pcd.points)

    mesh_curr = mesh_s.copy()

    for outer_it in range(nr_icp_iter):
        mesh_o3d_curr, _ = build_mesh_pcd_from_mesh(mesh_curr)
        src_pcd = mesh_o3d_curr.sample_points_uniformly(
            number_of_points=nr_samples_for_data
        )

        src_down = src_pcd.voxel_down_sample(icp_voxel_size)
        tgt_down = actual_pcd.voxel_down_sample(icp_voxel_size)
        src_down.estimate_normals()
        tgt_down.estimate_normals()

        reg = o3d.pipelines.registration.registration_icp(
            src_down,
            tgt_down,
            icp_max_corr_dist,
            np.eye(4),
            o3d.pipelines.registration.TransformationEstimationPointToPoint(),
        )
        T = reg.transformation
        mesh_curr.apply_transform(T)

        V = mesh_curr.vertices.copy()

        _, pcd_s = build_mesh_pcd_from_mesh(mesh_curr)
        pcd_s = estimate_normals_for_pcd(pcd_s, radius=1.0, max_nn=1000)
        pcd_tree = o3d.geometry.KDTreeFlann(pcd_s)

        corners = subsample_points(line_corners, nr_subsample_boundary)
        handle_indices = []
        handle_targets = []

        for p in corners:
            _, idx, _ = pcd_tree.search_knn_vector_3d(p, 1)
            j = idx[0]
            pj = np.asarray(pcd_s.points)[j]
            nj = np.asarray(pcd_s.normals)[j]
            v = p - pj
            dot = np.dot(v, nj)
            move_vec = dot * nj
            d = np.linalg.norm(move_vec)
            if d > nr_max_handle_move and d > 1e-8:
                move_vec = move_vec / d * nr_max_handle_move
            handle_indices.append(j)
            handle_targets.append(pj + move_vec)

        handle_indices = np.asarray(handle_indices, dtype=np.int64)
        handle_targets = np.asarray(handle_targets, dtype=np.float64)

        data_targets = np.zeros_like(V)
        data_counts = np.zeros((N, 1))

        sample_ids = np.linspace(0, N - 1, min(nr_samples_for_data, N), dtype=int)
        for vid in sample_ids:
            p = V[vid]
            _, idx, _ = actual_tree.search_knn_vector_3d(p, 1)
            q = actual_points[idx[0]]
            data_targets[vid] += q
            data_counts[vid] += 1.0

        mask = data_counts[:, 0] > 0
        data_targets[mask] /= data_counts[mask]

        A = A_lap.copy()
        B = B_lap.copy()

        for idx_h, h in enumerate(handle_indices):
            A[h, h] += nr_handle_w
            B[h] += nr_handle_w * handle_targets[idx_h]

        for vid in sample_ids:
            if data_counts[vid] > 0:
                A[vid, vid] += nr_data_w
                B[vid] += nr_data_w * data_targets[vid]

        X = np.zeros_like(V)
        for dim in range(3):
            X[:, dim] = np.linalg.solve(A, B[:, dim])

        mesh_curr.vertices = X

    return mesh_curr


if __name__ == "__main__":
    points = trimesh.load(
        "result_new_xyz.ply"
    ).vertices
    mesh = adaptive_sparse_pointcloud_to_mesh(points)
    mesh.export("mesh.obj")

    # boundary_pts, _ = segment_crown_regions(
    #     mesh,
    #     debug_cc_path=None,
    #     debug_merged_path=None,
    #     debug_result_path=None,
    # )

    # trimesh.PointCloud(boundary_pts).export("boundary_pts.obj")
    # std_mesh = trimesh.load('std.stl')
    # mesh_pose = pose_align(boundary_pts, std_mesh)
    # mesh_pose.export("mesh_pose.obj")
    # mesh_nr = nonrigid_icp_lap(boundary_pts, mesh_pose, mesh)
    # mesh_nr.export("mesh_nr.obj")
