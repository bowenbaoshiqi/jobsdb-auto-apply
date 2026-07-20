"""
滚动模拟 — 自然滚动行为

核心：模拟人类眼睛跟随滚动时的速度变化：
- 开头较慢（加速）
- 中间较快
- 接近目标时减速（查看内容）

使用 ease-in-out 三次缓动函数。
"""

import asyncio
import random
from typing import Optional

from playwright.async_api import ElementHandle, Page
from loguru import logger


class ScrollSimulator:
    """滚动模拟器"""

    def __init__(self, page: Page):
        self.page = page

    async def scroll_to_element(self, element: ElementHandle,
                                offset_ratio: float = 0.3) -> None:
        """
        自然滚动到元素可见位置

        Args:
            element: 目标元素
            offset_ratio: 元素出现在视口中的位置（0=顶部，0.5=中间，1=底部）
        """
        try:
            # 使用 JavaScript 执行平滑滚动
            # 因为 Playwright 的 scrollIntoViewIfNeeded 是瞬时的
            scroll_script = """
                (args) => {
                    const element = args.element;
                    const offsetRatio = args.offsetRatio;

                    return new Promise((resolve) => {
                        const elementRect = element.getBoundingClientRect();
                        const viewportHeight = window.innerHeight;

                        // 计算目标滚动位置
                        const targetY = window.scrollY +
                            elementRect.top -
                            viewportHeight * offsetRatio +
                            elementRect.height / 2;

                        const startY = window.scrollY;
                        const distance = targetY - startY;

                        // 滚动持续时间根据距离变化
                        const minDuration = 800;
                        const maxDuration = 2000;
                        const duration = Math.min(
                            maxDuration,
                            minDuration + Math.abs(distance) * 0.5
                        );

                        const startTime = performance.now();

                        function scrollStep(currentTime) {
                            const elapsed = currentTime - startTime;
                            const progress = Math.min(elapsed / duration, 1);

                            // ease-in-out cubic 缓动函数
                            // 开始慢 -> 加速 -> 结束慢
                            let ease;
                            if (progress < 0.5) {
                                // ease-in
                                ease = 4 * progress * progress * progress;
                            } else {
                                // ease-out
                                const f = -2 * progress + 2;
                                ease = 1 - (f * f * f) / 2;
                            }

                            window.scrollTo(0, startY + distance * ease);

                            if (progress < 1) {
                                requestAnimationFrame(scrollStep);
                            } else {
                                resolve();
                            }
                        }

                        requestAnimationFrame(scrollStep);
                    });
                }
            """

            await self.page.evaluate(scroll_script, {
                "element": element,
                "offsetRatio": offset_ratio,
            })

            # 滚动后停顿（模拟人眼读内容）
            await asyncio.sleep(random.uniform(0.3, 1.0))

        except Exception as e:
            logger.warning(f"Smooth scroll failed: {e}")
            # 降级：使用 Playwright 内置滚动
            await element.scroll_into_view_if_needed()

    async def scroll_page_down(self, amount: Optional[int] = None) -> None:
        """
        向下滚动一屏或指定距离

        Args:
            amount: 滚动像素数（默认视口高度的 60-90%）
        """
        viewport = self.page.viewport_size
        if amount is None:
            amount = int(viewport["height"] * random.uniform(0.6, 0.9))

        await self._smooth_scroll_by(amount)
        # 停顿时间（模拟阅读）
        await asyncio.sleep(random.uniform(1.0, 3.0))

    async def scroll_page_up(self, amount: Optional[int] = None) -> None:
        """
        向上滚动一屏或指定距离
        """
        viewport = self.page.viewport_size
        if amount is None:
            amount = -int(viewport["height"] * random.uniform(0.4, 0.7))

        await self._smooth_scroll_by(amount)
        await asyncio.sleep(random.uniform(0.5, 1.5))

    async def _smooth_scroll_by(self, delta_y: int) -> None:
        """平滑滚动指定距离"""
        scroll_script = """
            (args) => {
                return new Promise((resolve) => {
                    const deltaY = args.deltaY;
                    const startY = window.scrollY;
                    const targetY = startY + deltaY;
                    const duration = 600 + Math.abs(deltaY) * 0.3;

                    const startTime = performance.now();

                    function scrollStep(currentTime) {
                        const elapsed = currentTime - startTime;
                        const progress = Math.min(elapsed / duration, 1);

                        // ease-out 三次方
                        const ease = 1 - Math.pow(1 - progress, 3);
                        window.scrollTo(0, startY + deltaY * ease);

                        if (progress < 1) {
                            requestAnimationFrame(scrollStep);
                        } else {
                            resolve();
                        }
                    }

                    requestAnimationFrame(scrollStep);
                });
            }
        """
        await self.page.evaluate(scroll_script, {"deltaY": delta_y})

    async def random_scroll_behavior(self) -> None:
        """
        随机滚动行为 — 模拟人类在看内容时的随机滚动
        """
        choices = ["down", "up", "pause", "small_down", "small_up"]
        weights = [0.4, 0.15, 0.25, 0.12, 0.08]

        action = random.choices(choices, weights=weights, k=1)[0]

        if action == "down":
            await self.scroll_page_down()
        elif action == "up":
            await self.scroll_page_up()
        elif action == "pause":
            await asyncio.sleep(random.uniform(1.5, 4.0))
        elif action == "small_down":
            await self._smooth_scroll_by(random.randint(100, 300))
            await asyncio.sleep(random.uniform(0.5, 1.5))
        elif action == "small_up":
            await self._smooth_scroll_by(random.randint(-200, -80))
            await asyncio.sleep(random.uniform(0.3, 1.0))
