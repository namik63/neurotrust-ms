from __future__ import annotations

from collections import defaultdict, deque
import numpy as np
from skimage.measure import label, regionprops


def connected_components(mask: np.ndarray, connectivity: int = 26) -> tuple[np.ndarray, int]:
    conn = 3 if connectivity == 26 else 1
    labels = label(mask.astype(bool), connectivity=conn)
    return labels.astype(np.int32), int(labels.max())


def component_table(labels: np.ndarray, spacing: tuple[float, float, float], prefix: str) -> list[dict]:
    voxel_volume = float(np.prod(spacing))
    rows = []
    for prop in regionprops(labels):
        zyx = prop.centroid
        rows.append(
            {
                f"{prefix}_id": int(prop.label),
                "volume_voxels": int(prop.area),
                "volume_mm3": float(prop.area * voxel_volume),
                "centroid_x": float(zyx[2]),
                "centroid_y": float(zyx[1]),
                "centroid_z": float(zyx[0]),
                "bbox": [int(v) for v in prop.bbox],
            }
        )
    return rows


def overlap_edges(gt_labels: np.ndarray, pred_labels: np.ndarray) -> dict[tuple[int, int], int]:
    mask = (gt_labels > 0) & (pred_labels > 0)
    edges: dict[tuple[int, int], int] = {}
    if not mask.any():
        return edges
    pairs, counts = np.unique(np.stack([gt_labels[mask], pred_labels[mask]], axis=1), axis=0, return_counts=True)
    for (gt_id, pred_id), count in zip(pairs, counts):
        edges[(int(gt_id), int(pred_id))] = int(count)
    return edges


def greedy_matches(gt_labels: np.ndarray, pred_labels: np.ndarray) -> dict[int, int]:
    edges = overlap_edges(gt_labels, pred_labels)
    by_gt: dict[int, list[tuple[int, int]]] = defaultdict(list)
    used_pred: set[int] = set()
    matches: dict[int, int] = {}
    for (gt_id, pred_id), count in edges.items():
        by_gt[gt_id].append((pred_id, count))
    for gt_id, candidates in by_gt.items():
        for pred_id, _ in sorted(candidates, key=lambda x: (-x[1], x[0])):
            if pred_id not in used_pred:
                matches[gt_id] = pred_id
                used_pred.add(pred_id)
                break
    return matches


def cluster_graph(gt_labels: np.ndarray, pred_labels: np.ndarray) -> list[dict]:
    edges = overlap_edges(gt_labels, pred_labels)
    gt_ids = set(int(v) for v in np.unique(gt_labels) if v > 0)
    pred_ids = set(int(v) for v in np.unique(pred_labels) if v > 0)
    graph: dict[str, set[str]] = defaultdict(set)
    for gt in gt_ids:
        graph[f"g{gt}"]
    for pred in pred_ids:
        graph[f"p{pred}"]
    for gt, pred in edges:
        graph[f"g{gt}"].add(f"p{pred}")
        graph[f"p{pred}"].add(f"g{gt}")
    seen: set[str] = set()
    clusters = []
    cid = 1
    for node in list(graph):
        if node in seen:
            continue
        queue = deque([node])
        seen.add(node)
        members = []
        while queue:
            cur = queue.popleft()
            members.append(cur)
            for nxt in graph[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        g = sorted(int(m[1:]) for m in members if m.startswith("g"))
        p = sorted(int(m[1:]) for m in members if m.startswith("p"))
        if len(g) == 1 and len(p) == 1:
            ctype = "one-to-one"
        elif len(g) == 1 and len(p) > 1:
            ctype = "one-to-many split"
        elif len(g) > 1 and len(p) == 1:
            ctype = "many-to-one merge"
        elif len(g) > 1 and len(p) > 1:
            ctype = "many-to-many complex"
        elif len(g) and not p:
            ctype = "unmatched GT complete miss"
        else:
            ctype = "unmatched prediction false cluster"
        clusters.append({"cluster_id": cid, "gt_ids": g, "pred_ids": p, "cluster_type": ctype})
        cid += 1
    return clusters

