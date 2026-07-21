"""
BrowserPort — 浏览器生命周期抽象

只管启动/停止/新建页面,不管页面操作(那是 PageController 的职责)。
jobsdb/* 和 simulation/* 不直接依赖 BrowserEngine,而是依赖此接口。

v2.0 抽象层:运行时多态(Protocol 结构子类型),类型层不耦合具体实现。
"""

from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.browser.ports.page_controller import PageController


@runtime_checkable
class BrowserPort(Protocol):
    """浏览器抽象接口。"""

    async def start(self) -> "PageController":
        """启动浏览器,返回主页面的 PageController。"""
        ...

    async def stop(self) -> None:
        """停止浏览器,保存 cookies/profile。"""
        ...

    async def new_page(self) -> "PageController":
        """新建标签页,返回其 PageController(自动注入 stealth)。"""
        ...

    @property
    def current_page(self) -> Optional["PageController"]:
        """当前活跃页面的 PageController(未启动返回 None)。"""
        ...
