"""
PlaywrightBrowser — BrowserPort 接口的 Playwright 实现

复用 v1.0 BrowserEngine 的浏览器生命周期管理(启动/停止/stealth/cookies),
但对外暴露 BrowserPort 接口,返回 PageController 而非裸 Page。

v2.0: 这是生产实现;测试用 FakeBrowser(src/browser/fake/)。
"""

from typing import Optional

from src.browser.engine import BrowserEngine
from src.browser.ports.browser_port import BrowserPort
from src.browser.ports.page_controller import PageController
from src.browser.playwright_page_controller import PlaywrightPageController
from config.settings import BrowserConfig


class PlaywrightBrowser:
    """BrowserPort 的 Playwright 实现。"""

    def __init__(self, config: Optional[BrowserConfig] = None,
                 account_alias: str = "default"):
        self._engine = BrowserEngine(config, account_alias=account_alias)
        self._page_controller: Optional[PageController] = None

    async def start(self) -> PageController:
        page = await self._engine.start()
        self._page_controller = PlaywrightPageController(page)
        return self._page_controller

    async def stop(self) -> None:
        await self._engine.stop()
        self._page_controller = None

    async def new_page(self) -> PageController:
        page = await self._engine.new_page()
        return PlaywrightPageController(page)

    @property
    def current_page(self) -> Optional[PageController]:
        if self._page_controller is not None and not self._page_controller.is_closed():
            return self._page_controller
        return None

    @property
    def raw_engine(self) -> BrowserEngine:
        """底层 BrowserEngine(过渡期使用,供 cookies 等直接访问)"""
        return self._engine
