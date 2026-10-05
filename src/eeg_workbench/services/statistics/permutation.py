"""置换检验服务：置换 t 检验、置换方差分析、簇置换检验"""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np
from scipy import stats
from joblib import Parallel, delayed

from eeg_workbench.models.statistics import (
    PermutationParams, MultipleComparisonCorrection,
    ComparisonResult, StatisticsParams
)
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class PermutationResult:
    """置换检验结果"""
    result: ComparisonResult
    null_distribution: np.ndarray
    observed_statistic: float
    processing_time_ms: float


class PermutationService:
    """置换检验服务"""

    @staticmethod
    def run_permutation_ttest(
        group1: np.ndarray,
        group2: np.ndarray,
        params: PermutationParams,
        *,
        statistic_func: Callable[[np.ndarray, np.ndarray], Any] | None = None,
        verbose: bool = False
    ) -> PermutationResult:
        """置换 t 检验"""
        start_time = time.perf_counter()

        if statistic_func is None:
            def statistic_func(g1, g2):
                stat, _ = stats.ttest_ind(g1, g2, equal_var=False)
                return stat

        # 观测统计量
        obs_stat = statistic_func(group1, group2)

        # 合并数据
        combined = np.concatenate([group1, group2])
        n1, n2 = len(group1), len(group2)

        # 置换
        null_stats = Parallel(n_jobs=params.n_jobs, verbose=verbose)(
            delayed(PermutationService._single_permutation)(
                combined, n1, n2, statistic_func, params.seed
            ) for _ in range(params.n_permutations)
        )

        null_stats = np.array(null_stats)

        # 计算 p 值
        if params.tail == 0:  # 双尾
            p = np.mean(np.abs(null_stats) >= np.abs(obs_stat))
        elif params.tail == 1:  # 单尾大于
            p = np.mean(null_stats >= obs_stat)
        else:  # 单尾小于
            p = np.mean(null_stats <= obs_stat)

        result = ComparisonResult(
            test_name="permutation_t_test",
            statistic=float(np.abs(obs_stat)),
            p_value=float(p),
            corrected_p=float(p),
            significant=p < 0.05,
            details={"n_permutations": params.n_permutations}
        )

        return PermutationResult(
            result=result,
            null_distribution=null_stats,
            observed_statistic=float(obs_stat),
            processing_time_ms=(time.perf_counter() - start_time) * 1000
        )

    @staticmethod
    def _single_permutation(
        combined: np.ndarray,
        n1: int,
        n2: int,
        statistic_func: Callable[[np.ndarray, np.ndarray], Any],
        seed: int | None
    ) -> float:
        """单次置换"""
        if seed is not None:
            np.random.seed(seed + np.random.randint(0, 1000000))
        
        np.random.shuffle(combined)
        g1 = combined[:n1]
        g2 = combined[n1:]
        return statistic_func(g1, g2)

    @staticmethod
    def run_cluster_permutation(
        data: np.ndarray,  # (n_subjects, n_channels, n_times) 或 (n_subjects, n_channels)
        params: PermutationParams,
        *,
        channel_adjacency: np.ndarray | None = None,
        verbose: bool = False
    ) -> dict:
        """簇置换检验 (用于时空数据)"""
        start_time = time.perf_counter()

        # 数据形状检查
        if data.ndim == 3:
            n_subj, n_ch, n_times = data.shape
            is_time = True
        elif data.ndim == 2:
            n_subj, n_ch = data.shape
            n_times = 1
            is_time = False
        else:
            raise ValueError("数据必须是 2D 或 3D")

        # 计算观测统计量
        if is_time:
            # 每个时间点做 t 检验
            t_obs = np.zeros((n_ch, n_times))
            for ch in range(n_ch):
                for t in range(n_times):
                    stat, _ = stats.ttest_1samp(data[:, ch, t], 0)
                    t_obs[ch, t] = stat
        else:
            t_obs = np.zeros(n_ch)
            for ch in range(n_ch):
                stat, _ = stats.ttest_1samp(data[:, ch], 0)
                t_obs[ch] = stat

        # 阈值
        if params.cluster_threshold is None:
            # 使用 t 分布的 95% 分位数（别名导入：上文循环变量已占用 t）
            from scipy.stats import t as t_dist
            df = data.shape[0] - 1
            threshold = t_dist.ppf(0.975, df)
        else:
            threshold = params.cluster_threshold

        # 形成簇
        clusters = PermutationService._find_clusters(
            t_obs, threshold, channel_adjacency, is_time
        )

        # 计算簇统计量
        if params.cluster_method == "mass":
            cluster_stats = [np.sum(np.abs(c["values"])) for c in clusters]
        elif params.cluster_method == "size":
            cluster_stats = [c["size"] for c in clusters]
        else:
            cluster_stats = [np.sum(c["values"]) for c in clusters]

        max_obs = max(cluster_stats) if cluster_stats else 0

        # 置换
        null_max_stats = Parallel(n_jobs=-1)(
            delayed(PermutationService._single_cluster_permutation)(
                data, threshold, channel_adjacency, is_time, params.cluster_method
            ) for _ in range(params.n_permutations)
        )

        # p 值
        p = np.mean(np.array(null_max_stats) >= max_obs)

        return {
            "clusters": clusters,
            "observed_max_stat": max_obs,
            "null_distribution": np.array(null_max_stats),
            "p_value": p,
            "significant": p < 0.05
        }

    @staticmethod
    def _find_clusters(
        t_map: np.ndarray,
        threshold: float,
        adjacency: np.ndarray | None,
        is_time: bool
    ) -> list[dict]:
        """寻找簇"""
        clusters = []
        visited = np.zeros_like(t_map, dtype=bool)

        if is_time:
            n_ch, n_times = t_map.shape
            for ch in range(n_ch):
                for t in range(n_times):
                    if not visited[ch, t] and np.abs(t_map[ch, t]) > threshold:
                        # BFS 找簇
                        cluster = PermutationService._bfs_cluster(
                            t_map, visited, (ch, t), threshold, adjacency
                        )
                        if cluster["size"] >= 2:
                            clusters.append(cluster)
        else:
            n_ch = t_map.shape[0]
            for ch in range(n_ch):
                if not visited[ch] and np.abs(t_map[ch]) > threshold:
                    cluster = PermutationService._bfs_cluster(
                        t_map, visited, (ch,), threshold, adjacency
                    )
                    if cluster["size"] >= 2:
                        clusters.append(cluster)

        return clusters

    @staticmethod
    def _bfs_cluster(
        t_map: np.ndarray,
        visited: np.ndarray,
        start: tuple,
        threshold: float,
        adjacency: np.ndarray | None
    ) -> dict:
        """BFS 找簇"""
        from collections import deque
        queue = deque([start])
        cluster_points = []
        cluster_values = []

        while queue:
            pt = queue.popleft()
            if visited[pt]:
                continue
            visited[pt] = True
            cluster_points.append(pt)
            cluster_values.append(t_map[pt])

            # 找邻居
            if len(start) == 2:  # (ch, time)
                ch, t = pt
                neighbors = []
                if ch > 0: neighbors.append((ch-1, t))
                if ch < t_map.shape[0]-1: neighbors.append((ch+1, t))
                if t > 0: neighbors.append((ch, t-1))
                if t < t_map.shape[1]-1: neighbors.append((ch, t+1))
                if adjacency is not None:
                    for n_ch in np.where(adjacency[ch])[0]:
                        neighbors.append((n_ch, t))
            else:  # (ch,)
                ch = pt[0]
                neighbors = []
                if ch > 0: neighbors.append((ch-1,))
                if ch < t_map.shape[0]-1: neighbors.append((ch+1,))
                if adjacency is not None:
                    for n_ch in np.where(adjacency[ch])[0]:
                        neighbors.append((n_ch,))

                for n_pt in neighbors:
                    if not visited[n_pt] and np.abs(t_map[n_pt]) > threshold:
                        queue.append(n_pt)

        return {
            "points": cluster_points,
            "values": np.array(cluster_values),
            "size": len(cluster_points)
        }

    @staticmethod
    def _single_cluster_permutation(
        data: np.ndarray,
        threshold: float,
        adjacency: np.ndarray | None,
        is_time: bool,
        cluster_method: str
    ) -> float:
        """单次簇置换"""
        # 随机翻转符号
        n_subj = data.shape[0]
        signs = np.random.choice([-1, 1], size=n_subj)
        perm_data = data * signs[:, np.newaxis] if data.ndim == 2 else data * signs[:, np.newaxis, np.newaxis]

        # 计算 t 统计量
        if is_time:
            n_ch, n_times = data.shape[1], data.shape[2]
            t_map = np.zeros((n_ch, n_times))
            for ch in range(n_ch):
                for t in range(n_times):
                    stat, _ = stats.ttest_1samp(perm_data[:, ch, t], 0)
                    t_map[ch, t] = stat
        else:
            n_ch = data.shape[1]
            t_map = np.zeros(n_ch)
            for ch in range(n_ch):
                stat, _ = stats.ttest_1samp(perm_data[:, ch], 0)
                t_map[ch] = stat

        # 找簇
        clusters = PermutationService._find_clusters(t_map, threshold, adjacency, is_time)
        
        if not clusters:
            return 0

        if cluster_method == "mass":
            cluster_stats = [np.sum(np.abs(c["values"])) for c in clusters]
        elif cluster_method == "size":
            cluster_stats = [c["size"] for c in clusters]
        else:
            cluster_stats = [np.sum(c["values"]) for c in clusters]

        return max(cluster_stats)


def run_permutation_test(
    group1: np.ndarray,
    group2: np.ndarray,
    params: PermutationParams,
    **kwargs
) -> PermutationResult:
    return PermutationService.run_permutation_ttest(group1, group2, params)


def run_cluster_permutation(
    data: np.ndarray,
    params: PermutationParams,
    **kwargs
) -> dict:
    return PermutationService.run_cluster_permutation(data, params)