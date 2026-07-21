"""
TC-03, TC-04: Mouse Bezier 曲线模拟测试
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.simulation.mouse import MouseSimulator


class TestMouseBezierPath:
    """鼠标模拟 — P0 核心测试"""

    def test_tc03_path_is_not_straight_line(self):
        """
        TC-03: 生成 path 后验证不是直线

        核心思路：如果路径是直线（y = x），则所有点的 y ≈ x。
        贝塞尔曲线应该有中间点偏离这条直线。
        """
        # Mock page 对象（只需要 current_position 属性）
        class MockPage:
            def __init__(self):
                self.viewport = {"width": 1920, "height": 1080}

            async def viewport_size(self):
                return self.viewport

        mouse = MouseSimulator(MockPage(), bezier_points=25)
        start = (100.0, 100.0)
        end = (500.0, 500.0)

        path = mouse._generate_bezier_path(start, end, num_points=25)

        assert len(path) == 25, f"Expected 25 points, got {len(path)}"

        # 检查是否不是直线：至少有一个点偏离 y = x 超过 5px
        max_deviation = 0
        for x, y in path:
            deviation = abs(y - x)  # 对于从 (100,100) 到 (500,500)，直线是 y=x
            max_deviation = max(max_deviation, deviation)

        print(f"Max deviation from straight line: {max_deviation:.2f}px")
        assert max_deviation > 5, \
            f"Path is too straight (max deviation: {max_deviation}px). " \
            "Bezier curve should deviate from straight line."

    def test_tc03_path_contains_varied_points(self):
        """
        TC-03 补充：多次生成路径，每次应该不同（随机性）
        """
        class MockPage:
            async def viewport_size(self):
                return {"width": 1920, "height": 1080}

        mouse = MouseSimulator(MockPage())
        start, end = (100, 100), (500, 500)

        # 生成两条路径
        path1 = mouse._generate_bezier_path(start, end)
        path2 = mouse._generate_bezier_path(start, end)

        # 路径应该不同
        all_same = all(
            abs(p1[0] - p2[0]) < 0.01 and abs(p1[1] - p2[1]) < 0.01
            for p1, p2 in zip(path1, path2)
        )
        assert not all_same, "Two Bezier paths should differ due to random control points"

    def test_tc04_path_continuity_no_large_gaps(self):
        """
        TC-04: 验证路径连续性

        相邻点之间的距离应该平滑变化，没有突变。
        """
        class MockPage:
            async def viewport_size(self):
                return {"width": 1920, "height": 1080}

        mouse = MouseSimulator(MockPage())
        start, end = (100, 100), (500, 300)

        path = mouse._generate_bezier_path(start, end, num_points=30)

        # 计算相邻点距离
        distances = []
        for i in range(len(path) - 1):
            dx = path[i+1][0] - path[i][0]
            dy = path[i+1][1] - path[i][1]
            dist = np.sqrt(dx**2 + dy**2)
            distances.append(dist)

        max_gap = max(distances)
        avg_gap = np.mean(distances)

        print(f"Avg step: {avg_gap:.2f}px, Max step: {max_gap:.2f}px")

        # 最大步长不应超过 50px
        assert max_gap < 50, \
            f"Path has large gap: {max_gap:.2f}px (max allowed: 50px). " \
            f"Avg gap: {avg_gap:.2f}px"

        # 步长应该相对均匀（标准差不太大）
        std_gap = np.std(distances)
        assert std_gap < max(avg_gap * 0.5, 5), \
            f"Step sizes too irregular: std={std_gap:.2f}, avg={avg_gap:.2f}"
