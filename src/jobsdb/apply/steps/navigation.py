"""
navigation — apply 流程的步骤间导航辅助

v1.0 _click_next_or_submit 的逻辑:优先点 Next,其次 Submit。
被各 step handler 共用。
"""

import asyncio

from src.browser.ports.page_controller import PageController
from src.jobsdb.selectors import NEXT_STEP_BUTTON, SUBMIT_APPLICATION_BUTTON


async def click_next_or_submit(page: PageController, human=None) -> bool:
    """点击下一步或提交按钮(v1.0 _click_next_or_submit)

    优先级: Next > Submit。返回 True 表示成功点击。
    """
    # 优先: Next 按钮
    next_btn = await page.query_selector(NEXT_STEP_BUTTON)
    if next_btn:
        is_visible = await next_btn.is_visible()
        if is_visible:
            if human:
                await human.mouse.click_element(next_btn)
            else:
                await next_btn.click()
            await asyncio.sleep(2)
            return True

    # 其次: Submit 按钮
    submit_btn = await page.query_selector(SUBMIT_APPLICATION_BUTTON)
    if submit_btn:
        is_visible = await submit_btn.is_visible()
        if is_visible:
            if human:
                await human.mouse.click_element(submit_btn)
            else:
                await submit_btn.click()
            await asyncio.sleep(2)
            return True

    return False
