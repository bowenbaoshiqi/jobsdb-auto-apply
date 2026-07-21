"""
PlaywrightPageController — PageController 接口的 Playwright 实现

包装真实 Playwright Page,每个方法委托给底层 Page。
v2.0: BrowserEngine 降级为实现细节,本类是 PageController 的生产实现。
"""

from typing import Any, Optional

from playwright.async_api import ElementHandle, Page

from src.browser.ports.page_controller import PageController


class PlaywrightPageController:
    """PageController 的 Playwright 实现。"""

    def __init__(self, page: Page):
        self._page = page

    # --- 导航 ---
    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
        await self._page.goto(url, wait_until=wait_until)

    @property
    def url(self) -> str:
        return self._page.url

    # --- 查询(只读) ---
    async def query_selector(self, selector: str) -> Optional[ElementHandle]:
        return await self._page.query_selector(selector)

    async def query_selector_all(self, selector: str) -> list:
        return await self._page.query_selector_all(selector)

    async def is_visible(self, selector: str) -> bool:
        return await self._page.is_visible(selector)

    async def count(self, selector: str) -> int:
        return await self._page.locator(selector).count()

    async def get_text(self, selector: str) -> Optional[str]:
        """收敛 v1.0 三行模式: query + inner_text + None 防护"""
        elem = await self._page.query_selector(selector)
        if elem is None:
            return None
        return await elem.text_content()

    async def get_attribute(self, selector: str, attr: str) -> Optional[str]:
        elem = await self._page.query_selector(selector)
        if elem is None:
            return None
        return await elem.get_attribute(attr)

    # --- 交互(写) ---
    async def click(self, selector: str, timeout: float = 30.0) -> None:
        await self._page.click(selector, timeout=timeout * 1000)

    async def fill(self, selector: str, value: str) -> None:
        await self._page.fill(selector, value)

    async def type_text(self, selector: str, value: str, delay: int = 50) -> None:
        """type_text 避开 Python 内建 type 名冲突"""
        await self._page.type(selector, value, delay=delay)

    async def select_option(self, selector: str, value: str) -> None:
        await self._page.select_option(selector, value)

    async def check(self, selector: str) -> None:
        await self._page.check(selector)

    # --- 等待 ---
    async def wait_for_selector(self, selector: str, timeout: float = 30.0) -> None:
        await self._page.wait_for_selector(selector, timeout=timeout * 1000)

    async def wait_for_timeout(self, ms: int) -> None:
        await self._page.wait_for_timeout(ms)

    # --- JS 执行 ---
    async def evaluate(self, expression: str) -> Any:
        return await self._page.evaluate(expression)

    # --- 截图 ---
    async def screenshot(self, path: str) -> None:
        await self._page.screenshot(path=path)

    def is_closed(self) -> bool:
        return self._page.is_closed()

    # --- 底层访问(供 HumanSimulator 等需要 page 的场景过渡使用) ---
    @property
    def raw_page(self) -> Page:
        """底层 Playwright Page(过渡期使用,完整迁移后应移除)"""
        return self._page
