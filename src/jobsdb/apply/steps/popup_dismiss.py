"""
popup_dismiss — 关闭可能的弹窗(前置清理,非状态机 step)

v1.0 _dismiss_popups 的逻辑:逐个尝试关闭 cookie 通知等弹窗。
"""

import asyncio

from src.browser.ports.page_controller import PageController
from src.jobsdb.selectors import COOKIE_BANNER, NOTIFICATION_PROMPT

# v1.0 _dismiss_popups 的弹窗选择器列表(顺序不动)
_POPUP_SELECTORS = [
    COOKIE_BANNER,
    NOTIFICATION_PROMPT,
    'button:has-text("Not now")',
    'button:has-text("Skip")',
    'button:has-text("No thanks")',
]


async def run(page: PageController) -> None:
    """关闭可能的弹窗(v1.0 _dismiss_popups)"""
    for selector in _POPUP_SELECTORS:
        try:
            popup = await page.query_selector(selector)
            if popup:
                await popup.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass
