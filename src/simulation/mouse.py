"""
鼠标模拟 — Bezier 曲线自然移动

核心：模拟人类手臂移动时的曲线轨迹，而非机器人式的直线移动。
使用三次贝塞尔曲线（Cubic Bezier），增加随机控制点使其更自然。
"""

import asyncio
import random
from typing import Optional

import numpy as np
from loguru import logger
from playwright.async_api import ElementHandle, Page


class MouseSimulator:
    """鼠标移动模拟器"""

    def __init__(self, page: Page, bezier_points: int = 25):
        self.page = page
        self.bezier_points = bezier_points
        # 初始位置随机（模拟用户刚打开页面时鼠标不在固定位置）
        self.current_position = (
            random.randint(200, 800),
            random.randint(200, 600),
        )

    async def move_to_element(self, element: ElementHandle,
                              offset_x: int = 0, offset_y: int = 0,
                              hover_time: Optional[float] = None) -> None:
        """
        自然移动到元素位置

        Args:
            element: 目标元素
            offset_x: X 轴偏移
            offset_y: Y 轴偏移
            hover_time: 悬停时间（默认随机 0.2-0.8 秒）
        """
        try:
            box = await element.bounding_box()
            if not box:
                logger.warning("Element has no bounding box")
                return

            target = (
                box["x"] + box["width"] / 2 + offset_x,
                box["y"] + box["height"] / 2 + offset_y,
            )

            await self.move_to(target)

            # 悬停片刻（模拟人类在点击前会暂停一下看按钮）
            if hover_time is None:
                hover_time = random.uniform(0.2, 0.8)
            await asyncio.sleep(hover_time)

        except Exception as e:
            logger.warning(f"Mouse move to element failed: {e}")
            # 降级：直接跳到目标位置
            await element.hover()

    async def move_to(self, target: tuple[float, float]) -> None:
        """
        从当前位置自然移动到目标位置

        Args:
            target: (x, y) 坐标
        """
        path = self._generate_bezier_path(
            self.current_position,
            target,
            num_points=self.bezier_points,
        )

        # 沿路径移动
        for i, point in enumerate(path):
            # 移动到当前点
            await self.page.mouse.move(point[0], point[1])

            # 移动速度不是均匀的 — 中间慢（快到目标前减速）
            # ease-in-out: 开头和结尾慢，中间快
            progress = i / len(path)
            # 使用 ease-in-out 速度曲线
            speed_factor = 1.0 - abs(progress - 0.5) * 1.5
            base_delay = 0.008  # 8ms 基础间隔
            delay = base_delay * (0.5 + speed_factor)
            delay += random.normalvariate(0, 0.002)  # 加入微小抖动

            await asyncio.sleep(max(0.003, delay))

        self.current_position = target

    async def click_element(self, element: ElementHandle,
                            move_first: bool = True) -> None:
        """
        模拟人类点击元素：先移动，再悬停，再点击

        Args:
            element: 目标元素
            move_first: 是否先移动鼠标（默认是）
        """
        if move_first:
            await self.move_to_element(element)
        else:
            # 直接悬停（如果已经在元素上）
            await element.hover()
            await asyncio.sleep(random.uniform(0.1, 0.3))

        # 人类点击不是瞬间的，先按下再释放之间有微小间隔
        box = await element.bounding_box()
        if box:
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2

            # 有 5% 概率点击稍微偏移中心（人类不总是点正中心）
            if random.random() < 0.05:
                x += random.normalvariate(0, 2)
                y += random.normalvariate(0, 2)

            await self.page.mouse.click(x, y)
        else:
            # 降级：使用 Playwright 的 click（即时）
            await element.click()

        # 点击后有微小停顿（确认点击生效）
        await asyncio.sleep(random.uniform(0.05, 0.2))

    async def random_movement(self, max_distance: int = 200) -> None:
        """
        随机移动鼠标（模拟人类"走神"或偶然移动）

        Args:
            max_distance: 最大移动距离
        """
        # 在当前位置附近随机选择一个点
        target = (
            self.current_position[0] + random.normalvariate(0, max_distance / 2),
            self.current_position[1] + random.normalvariate(0, max_distance / 2),
        )

        # 确保在视口内
        viewport = self.page.viewport_size
        target = (
            max(0, min(viewport["width"], target[0])),
            max(0, min(viewport["height"], target[1])),
        )

        await self.move_to(target)

    def _generate_bezier_path(self,
                              start: tuple[float, float],
                              end: tuple[float, float],
                              num_points: int = 25) -> list:
        """
        生成三次贝塞尔曲线路径

        策略：
        - 控制点随机偏移，模拟手臂的自然弧线
        - 有时会"过冲"一点再回来（像真实手臂惯性的感觉）
        """
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = np.sqrt(dx**2 + dy**2)

        # 控制点的偏移量与距离成正比，但有随机性
        # 偏移方向随机（上、下、左、右取决于移动方向）
        offset_scale = distance * random.uniform(0.15, 0.35)

        # 决定偏移方向
        if random.random() < 0.5:
            # 偏向一侧
            perp_x = -dy / distance if distance > 0 else 0
            perp_y = dx / distance if distance > 0 else 0
        else:
            # 偏向另一侧
            perp_x = dy / distance if distance > 0 else 0
            perp_y = -dx / distance if distance > 0 else 0

        # 添加过冲效果（偶尔超过目标一点再回来）
        overshoot = random.random() < 0.2  # 20% 概率

        # 控制点1：靠近起点，但偏离直线路径
        cp1 = (
            start[0] + dx * 0.3 + perp_x * offset_scale,
            start[1] + dy * 0.3 + perp_y * offset_scale,
        )

        # 控制点2：靠近终点，但偏离方向可能不同（模拟手腕调整）
        cp2 = (
            start[0] + dx * 0.7 - perp_x * offset_scale * random.uniform(0.5, 1.0),
            start[1] + dy * 0.7 - perp_y * offset_scale * random.uniform(0.5, 1.0),
        )

        if overshoot:
            # 稍微过冲
            cp2 = (cp2[0] + dx * 0.1, cp2[1] + dy * 0.1)

        # 生成路径点
        t_values = np.linspace(0, 1, num_points)
        path = []

        for t in t_values:
            point = self._cubic_bezier(t, start, cp1, cp2, end)
            path.append(point)

        return path

    @staticmethod
    def _cubic_bezier(t: float,
                      p0: tuple[float, float],
                      p1: tuple[float, float],
                      p2: tuple[float, float],
                      p3: tuple[float, float]) -> tuple[float, float]:
        """三次贝塞尔曲线公式"""
        mt = 1 - t
        x = (mt**3 * p0[0] +
             3 * mt**2 * t * p1[0] +
             3 * mt * t**2 * p2[0] +
             t**3 * p3[0])
        y = (mt**3 * p0[1] +
             3 * mt**2 * t * p1[1] +
             3 * mt * t**2 * p2[1] +
             t**3 * p3[1])
        return (x, y)
