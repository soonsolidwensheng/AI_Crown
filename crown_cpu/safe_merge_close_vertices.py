import math

import numpy as np
import trimesh
from scipy.spatial import KDTree


def _as_trimesh(mesh):
    if isinstance(mesh, trimesh.Trimesh):
        return trimesh.Trimesh(
            vertices=np.array(mesh.vertices),
            faces=np.array(mesh.faces),
            process=False,
        )
    return trimesh.Trimesh(
        vertices=np.asarray(mesh.vertices),
        faces=np.asarray(mesh.triangles),
        process=False,
    )


def _unique_faces(faces):
    if len(faces) == 0:
        return faces
    faces_sorted = np.sort(faces, axis=1)
    _, unique_idx = np.unique(faces_sorted, axis=0, return_index=True)
    unique_idx = np.sort(unique_idx)
    return faces[unique_idx]


def _boundary_vertex_ids(mesh):
    unique_edges, counts = np.unique(mesh.edges_sorted, return_counts=True, axis=0)
    boundary_edges = unique_edges[np.where(counts == 1)[0]]
    if len(boundary_edges) == 0:
        return np.array([], dtype=np.int64)
    return np.unique(boundary_edges.reshape(-1)).astype(np.int64)


def _boundary_distances(mesh, boundary_ids):
    if len(boundary_ids) == 0:
        return np.full(len(mesh.vertices), np.inf, dtype=np.float64)
    tree = KDTree(mesh.vertices[boundary_ids])
    distances, _ = tree.query(mesh.vertices, k=1)
    return distances.astype(np.float64)


def _topology_summary(mesh):
    mesh = _as_trimesh(mesh)
    unique_edges, counts = np.unique(mesh.edges_sorted, return_counts=True, axis=0)
    boundary_edges = unique_edges[np.where(counts == 1)[0]]
    nonmanifold_edges = unique_edges[np.where(counts > 2)[0]]
    edge_vertex_degree = {}
    for edge in boundary_edges:
        edge_vertex_degree[int(edge[0])] = edge_vertex_degree.get(int(edge[0]), 0) + 1
        edge_vertex_degree[int(edge[1])] = edge_vertex_degree.get(int(edge[1]), 0) + 1
    bad_boundary_vertices = sorted(
        [vertex for vertex, degree in edge_vertex_degree.items() if degree != 2]
    )

    components = 0
    if len(boundary_edges):
        import networkx as nx

        graph = nx.Graph()
        graph.add_edges_from(boundary_edges.tolist())
        components = int(nx.number_connected_components(graph))

    return {
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "boundary_vertex_count": int(len(np.unique(boundary_edges.reshape(-1))))
        if len(boundary_edges)
        else 0,
        "boundary_component_count": int(components),
        "bad_boundary_vertex_count": int(len(bad_boundary_vertices)),
        "bad_boundary_vertices": bad_boundary_vertices[:50],
        "nonmanifold_edge_count": int(len(nonmanifold_edges)),
    }


def _collapse_disjoint_short_edges(
    mesh,
    threshold,
    boundary_buffer,
    normal_angle_deg,
    protect_boundary,
):
    mesh = _as_trimesh(mesh)
    boundary_ids = _boundary_vertex_ids(mesh)
    boundary_mask = np.zeros(len(mesh.vertices), dtype=bool)
    boundary_mask[boundary_ids] = True
    if protect_boundary:
        boundary_distances = _boundary_distances(mesh, boundary_ids)
        safe_vertex_mask = (~boundary_mask) & (boundary_distances > boundary_buffer)
    else:
        boundary_distances = np.full(len(mesh.vertices), np.inf, dtype=np.float64)
        safe_vertex_mask = np.ones(len(mesh.vertices), dtype=bool)

    edges = np.asarray(mesh.edges_unique, dtype=np.int64)
    if len(edges) == 0:
        return mesh, {
            "selected_edge_count": 0,
            "candidate_edge_count": 0,
            "collapsed_vertex_count": 0,
            "boundary_buffer": float(boundary_buffer),
            "protect_boundary": bool(protect_boundary),
        }

    edge_lengths = np.linalg.norm(
        mesh.vertices[edges[:, 0]] - mesh.vertices[edges[:, 1]], axis=1
    )
    candidate_mask = edge_lengths < threshold
    candidate_mask &= safe_vertex_mask[edges[:, 0]]
    candidate_mask &= safe_vertex_mask[edges[:, 1]]

    if len(mesh.vertex_normals) == len(mesh.vertices):
        normal_cos = np.sum(
            mesh.vertex_normals[edges[:, 0]] * mesh.vertex_normals[edges[:, 1]], axis=1
        )
        candidate_mask &= normal_cos >= math.cos(math.radians(normal_angle_deg))

    candidate_edges = edges[candidate_mask]
    candidate_lengths = edge_lengths[candidate_mask]
    if len(candidate_edges) == 0:
        return mesh, {
            "selected_edge_count": 0,
            "candidate_edge_count": 0,
            "collapsed_vertex_count": 0,
            "boundary_buffer": float(boundary_buffer),
            "protect_boundary": bool(protect_boundary),
        }

    order = np.argsort(candidate_lengths)
    selected_edges = []
    used_vertices = np.zeros(len(mesh.vertices), dtype=bool)
    replacement = np.arange(len(mesh.vertices), dtype=np.int64)
    new_vertices = np.array(mesh.vertices)

    for edge in candidate_edges[order]:
        v0 = int(edge[0])
        v1 = int(edge[1])
        if used_vertices[v0] or used_vertices[v1]:
            continue
        keep = min(v0, v1)
        drop = max(v0, v1)
        midpoint = (new_vertices[v0] + new_vertices[v1]) / 2.0
        new_vertices[keep] = midpoint
        replacement[drop] = keep
        used_vertices[v0] = True
        used_vertices[v1] = True
        selected_edges.append([keep, drop])

    if len(selected_edges) == 0:
        return mesh, {
            "selected_edge_count": 0,
            "candidate_edge_count": int(len(candidate_edges)),
            "collapsed_vertex_count": 0,
            "boundary_buffer": float(boundary_buffer),
        }

    new_faces = replacement[np.asarray(mesh.faces, dtype=np.int64)]
    valid_face_mask = (
        (new_faces[:, 0] != new_faces[:, 1])
        & (new_faces[:, 1] != new_faces[:, 2])
        & (new_faces[:, 0] != new_faces[:, 2])
    )
    new_faces = new_faces[valid_face_mask]

    keep_vertex_mask = np.ones(len(new_vertices), dtype=bool)
    keep_vertex_mask[[drop for _keep, drop in selected_edges]] = False
    compact_index = np.full(len(new_vertices), -1, dtype=np.int64)
    compact_index[keep_vertex_mask] = np.arange(np.sum(keep_vertex_mask))
    new_faces = compact_index[new_faces]
    new_vertices = new_vertices[keep_vertex_mask]
    new_faces = _unique_faces(new_faces)

    merged_mesh = trimesh.Trimesh(
        vertices=new_vertices,
        faces=new_faces,
        process=False,
    )
    debug = {
        "selected_edge_count": int(len(selected_edges)),
        "candidate_edge_count": int(len(candidate_edges)),
        "collapsed_vertex_count": int(len(selected_edges)),
        "boundary_buffer": float(boundary_buffer),
        "protect_boundary": bool(protect_boundary),
        "selected_edges_preview": selected_edges[:50],
    }
    return merged_mesh, debug


def safe_merge_close_vertices(
    mesh,
    threshold,
    boundary_buffer=None,
    normal_angle_deg=25.0,
    max_passes=3,
    protect_boundary=True,
    log_fn=None,
):
    if log_fn is None:
        log_fn = lambda message: None

    if boundary_buffer is None:
        boundary_buffer = threshold

    current_mesh = _as_trimesh(mesh)
    before_summary = _topology_summary(current_mesh)
    pass_logs = []

    for pass_index in range(1, max_passes + 1):
        merged_mesh, collapse_debug = _collapse_disjoint_short_edges(
            current_mesh,
            threshold=threshold,
            boundary_buffer=boundary_buffer,
            normal_angle_deg=normal_angle_deg,
            protect_boundary=protect_boundary,
        )
        after_summary = _topology_summary(merged_mesh)
        accepted = (
            after_summary["nonmanifold_edge_count"]
            <= before_summary["nonmanifold_edge_count"]
            and after_summary["bad_boundary_vertex_count"]
            <= before_summary["bad_boundary_vertex_count"]
            and after_summary["boundary_component_count"]
            <= before_summary["boundary_component_count"]
        )

        pass_log = {
            "pass": int(pass_index),
            "accepted": bool(accepted),
            "before": before_summary,
            "after": after_summary,
            "collapse": collapse_debug,
        }
        pass_logs.append(pass_log)
        log_fn(
            "[SAFE_MERGE] pass={} accepted={} selected_edges={} "
            "boundary_components {}->{} bad_boundary_vertices {}->{}".format(
                pass_index,
                accepted,
                collapse_debug["selected_edge_count"],
                before_summary["boundary_component_count"],
                after_summary["boundary_component_count"],
                before_summary["bad_boundary_vertex_count"],
                after_summary["bad_boundary_vertex_count"],
            )
        )

        if not accepted or collapse_debug["selected_edge_count"] == 0:
            break

        current_mesh = merged_mesh
        before_summary = after_summary

    debug_info = {
        "threshold": float(threshold),
        "boundary_buffer": float(boundary_buffer),
        "normal_angle_deg": float(normal_angle_deg),
        "max_passes": int(max_passes),
        "protect_boundary": bool(protect_boundary),
        "result_summary": _topology_summary(current_mesh),
        "passes": pass_logs,
    }
    return current_mesh, debug_info
