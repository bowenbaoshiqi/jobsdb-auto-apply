"""
高级行为模式 — 模拟完整的人类浏览行为

组合 mouse + scroll + typing + timing，
模拟"一个真实人类浏览招聘网站"的完整行为链。
"""

import asyncio
import contextlib
import random

from playwright.async_api import Page

from src.simulation.mouse import MouseSimulator
from src.simulation.scroll import ScrollSimulator
from src.simulation.timing import HumanActionType, wait_human


class HumanSimulator:
    """
    人类行为模拟器（高层封装）

    封装了所有低层模拟模块，提供"人类化浏览"的完整行为链。
    """

    def __init__(self, page: Page,
                 bezier_points: int = 25,
                 typo_probability: float = 0.04,
                 base_delay_ms: float = 80.0,
                 delay_variance_ms: float = 40.0):
        self.page = page
        self.mouse = MouseSimulator(page, bezier_points)
        self.scroll = ScrollSimulator(page)
        self.typing = None  # lazy init，需要时才创建
        self.typo_probability = typo_probability
        self.base_delay_ms = base_delay_ms
        self.delay_variance_ms = delay_variance_ms

    async def browse_homepage(self, scroll_depth: int = 3) -> None:
        """
        模拟人类浏览首页的行为

        行为链：
        1. 页面加载后稍等
        2. 随机向下滚动几次
        3. 有时回滚一点看之前的内容
        4. 偶尔随机移动鼠标
        """
        await wait_human(HumanActionType.PAGE_LOAD)

        for _ in range(scroll_depth):
            # 向下滚动一屏
            await self.scroll.scroll_page_down()

            # 80% 概率再多滚动一点看内容
            if random.random() < 0.8:
                await asyncio.sleep(random.uniform(0.5, 1.5))
                await self.scroll._smooth_scroll_by(random.randint(100, 250))

            # 30% 概率回滚一点（好像看漏了什么）
            if random.random() < 0.3:
                await asyncio.sleep(random.uniform(0.5, 1.0))
                await self.scroll.scroll_page_up(random.randint(100, 300))

            # 20% 概率随机移动鼠标
            if random.random() < 0.2:
                await self.mouse.random_movement(max_distance=150)

            # 阅读停顿
            await wait_human(HumanActionType.READ_CONTENT,
                           mean_override=random.uniform(1.5, 4.0))

    async def view_job_detail(self) -> None:
        """
        模拟查看职位详情页的行为

        行为链：
        1. 等待页面加载
        2. 从上到下滚动看内容
        3. 在中间某处停顿较长时间（看 JD 描述）
        4. 偶尔回滚看薪资/公司信息
        """
        await wait_human(HumanActionType.PAGE_LOAD)

        # 先看上半部分（标题、公司、薪资）
        await wait_human(HumanActionType.READ_CONTENT, mean_override=2.0)

        # 向下滚动看 JD
        await self.scroll.scroll_page_down()
        await wait_human(HumanActionType.READ_CONTENT, mean_override=3.0)

        # 50% 概率继续滚动看更多JD
        if random.random() < 0.5:
            await self.scroll.scroll_page_down(
                amount=random.randint(200, 400)
            )
            await wait_human(HumanActionType.READ_CONTENT,
                           mean_override=random.uniform(1.0, 2.5))

        # 20% 概率回滚看薪资/要求
        if random.random() < 0.2:
            await self.scroll.scroll_page_up(random.randint(100, 300))
            await wait_human(HumanActionType.READ_CONTENT,
                           mean_override=random.uniform(0.5, 1.5))

        # 15% 概率再回滚到顶部看公司名
        if random.random() < 0.15:
            await self.page.evaluate("window.scrollTo(0, 0)")
            await wait_human(HumanActionType.READ_CONTENT,
                           mean_override=random.uniform(0.8, 1.5))

    async def click_apply_button(self, apply_button) -> None:
        """
        模拟点击"Apply"按钮的行为

        行为链：
        1. 滚动到按钮可见
        2. 停顿一下（确认按钮位置）
        3. 鼠标移动到按钮
        4. 悬停片刻
        5. 点击
        """
        # 滚动到按钮
        await self.scroll.scroll_to_element(apply_button, offset_ratio=0.4)
        await wait_human(HumanActionType.CLICK)

        # 点击按钮
        await self.mouse.click_element(apply_button)

        # 点击后等响应
        await wait_human(HumanActionType.SUBMIT_WAIT)

    async def fill_form_field(self, field, text: str, is_password: bool = False) -> None:
        """
        模拟填写表单项

        Args:
            field: 输入框元素
            text: 要输入的文本
            is_password: 是否是密码（更慢更谨慎）
        """
        # 先滚动到输入框
        await self.scroll.scroll_to_element(field, offset_ratio=0.5)

        # 等待片刻（找到输入框）
        await wait_human(HumanActionType.FORM_FILL)

        # 创建打字模拟器（lazy init）
        if self.typing is None:
            from src.simulation.typing import TypingSimulator
            self.typing = TypingSimulator(
                self.page,
                typo_probability=self.typo_probability,
                base_delay_ms=self.base_delay_ms,
                delay_variance_ms=self.delay_variance_ms,
            )

        # 输入
        if is_password:
            await self.typing.type_slowly(field, text)
        else:
            await self.typing.type_text(field, text)

        # 输入后停顿
        await wait_human(HumanActionType.FORM_FILL)

    async def random_distractor(self) -> None:
        """
        随机"分神"行为 — 模拟人类在做一件事时突然被打断或走神

        例如：
        - 鼠标移到非目标元素上悬停
        - 稍微滚动看看别的东西
        - 停顿较长时间（好像在想别的事）
        """
        choices = ["mouse_wander", "small_scroll", "pause", "tab_away"]
        weights = [0.4, 0.3, 0.2, 0.1]

        action = random.choices(choices, weights=weights, k=1)[0]

        if action == "mouse_wander":
            # 鼠标随机漫游
            await self.mouse.random_movement(max_distance=300)
            await wait_human(HumanActionType.HOVER, mean_override=0.5)

        elif action == "small_scroll":
            # 小幅度滚动
            direction = random.choice([1, -1])
            amount = random.randint(50, 200) * direction
            await self.scroll._smooth_scroll_by(amount)
            await wait_human(HumanActionType.READ_CONTENT, mean_override=1.0)

        elif action == "pause":
            # 停顿（走神）
            await wait_human(HumanActionType.READ_CONTENT,
                           mean_override=random.uniform(2.0, 5.0))

        elif action == "tab_away":
            # 模拟切到别的标签页再回来（如果有多标签）
            # 暂时不实现，需要跨标签支持
            pass

    async def wait_for_page_stability(self, timeout: int = 5000) -> None:
        """
        等待页面稳定（网络空闲）

        在关键操作前（如点击 Apply 前）确认页面已完全加载
        """
        # 超时则忽略(三分法 B 类:降级)
        with contextlib.suppress(Exception):
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
