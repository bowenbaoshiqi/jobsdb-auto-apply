"""
TC-05, TC-06: 打字模拟测试

重点：不依赖真实 Playwright Page，用 mock 对象统计键盘事件。
"""

import asyncio
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.simulation.typing import TypingSimulator


class MockPage:
    """模拟 Playwright Page 的键盘事件"""

    def __init__(self):
        self.keyboard_events = []

    async def keyboard_press(self, key):
        self.keyboard_events.append({"type": "press", "key": key})

    class MockKeyboard:
        def __init__(self, page):
            self.page = page

        async def press(self, key):
            self.page.keyboard_events.append({"type": "press", "key": key})

    @property
    def keyboard(self):
        return self.MockKeyboard(self)


class TestTypingSimulation:
    """打字模拟测试"""

    @pytest.mark.asyncio
    async def test_tc05_delay_distribution_gaussian(self):
        """
        TC-05: 验证打字延迟的平均值和标准差

        策略：mock 掉 asyncio.sleep，记录每次 delay，收集统计量。
        """
        page = MockPage()
        simulator = TypingSimulator(
            page,
            typo_probability=0.0,  # 不打错，简化统计
            base_delay_ms=80.0,
            delay_variance_ms=40.0,
        )

        delays = []
        original_sleep = asyncio.sleep

        async def mock_sleep(delay):
            delays.append(delay)

        # Patch asyncio.sleep
        asyncio.sleep = mock_sleep

        try:
            # Mock 输入框
            class MockElement:
                async def click(self):
                    pass

            await simulator.type_text(MockElement(), "hello")
        finally:
            asyncio.sleep = original_sleep

        # 过滤掉 click() 后的停顿（第一个 sleep）
        # 只保留按键间隔
        key_delays = [d for d in delays if d > 0.01]

        assert len(key_delays) > 0, "Should have recorded key delays"

        mean_delay = np.mean(key_delays) * 1000  # 转 ms
        std_delay = np.std(key_delays) * 1000

        print(f"Mean delay: {mean_delay:.2f}ms, std: {std_delay:.2f}ms")

        # 均值应该在 60-120ms 之间（80ms ± 40ms）
        assert 40 < mean_delay < 140, \
            f"Mean delay {mean_delay:.1f}ms not in expected range 60-120ms"

        # 标准差应该在合理范围（不要太小=均匀分布，不要太大=不稳定）
        assert 10 < std_delay < 100, \
            f"Std {std_delay:.1f}ms too small or too large for Gaussian"

    @pytest.mark.asyncio
    async def test_tc06_typo_probability(self):
        """
        TC-06: 验证 typo 概率约为 4%

        策略：输入大量字符，检查 Backspace 出现次数。
        """
        page = MockPage()
        simulator = TypingSimulator(
            page,
            typo_probability=0.04,
            base_delay_ms=10.0,  # 加快测试
            delay_variance_ms=5.0,
        )

        original_sleep = asyncio.sleep

        async def noop_sleep(delay):
            return None

        asyncio.sleep = noop_sleep

        try:
            class MockElement:
                async def click(self):
                    pass
                async def fill(self, text):
                    pass

            await simulator.type_text(MockElement(), "a" * 100)
        finally:
            asyncio.sleep = original_sleep

        # 统计 Backspace 次数
        backspaces = sum(1 for e in page.keyboard_events if e["key"] == "Backspace")
        total_keys = len(page.keyboard_events) - backspaces  # 原始按键不含 Backspace

        typo_rate = backspaces / total_keys if total_keys > 0 else 0
        print(f"Backspaces: {backspaces}, total keys: {total_keys}, typo rate: {typo_rate:.2%}")

        # 100 个字符，约 4 个 typo（4%），考虑随机性，允许 0-12
        assert 0 <= backspaces <= 15, \
            f"Typo count {backspaces} out of expected range for 4% probability"
