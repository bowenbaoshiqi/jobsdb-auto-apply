"""
FakeBrowser — BrowserPort 接口的纯内存假实现

测试专用:不起浏览器,start() 返回 FakePageController。
让 Orchestrator 用 FakeFactory 注入后可单测,不碰真实 Chromium。

用法:
    fake = FakeBrowser()
    page = await fake.start()  # FakePageController,毫秒级
"""

from typing import Optional

from src.browser.fake.fake_page import FakePageController
from src.browser.ports.page_controller import PageController


class FakeBrowser:
    """BrowserPort 的内存假实现(测试专用)。"""

    def __init__(self):
        self._page_controller: Optional[FakePageController] = None
        self._started = False

    async def start(self) -> PageController:
        self._page_controller = FakePageController()
        self._started = True
        return self._page_controller

    async def stop(self) -> None:
        self._started = False
        self._page_controller = None

    async def new_page(self) -> PageController:
        return FakePageController()

    @property
    def current_page(self) -> Optional[PageController]:
        if self._page_controller is not None:
            return self._page_controller
        return None

    @property
    def page_controller(self) -> Optional[FakePageController]:
        """暴露内部 FakePageController(测试预设状态用)"""
        return self._page_controller
