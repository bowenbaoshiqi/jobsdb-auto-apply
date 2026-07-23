"""
navigation — apply 流程的步骤间导航辅助

v1.0 _click_next_or_submit 的逻辑:优先点 Next,其次 Submit。
被各 step handler 共用。
"""

import asyncio

from src.browser.ports.page_controller import PageController
from src.jobsdb.selectors import (
    CONTINUE_BUTTON,
    NEXT_STEP_BUTTON,
    SUBMIT_APPLICATION_BUTTON,
)


async def click_next_or_submit(page: PageController, human=None) -> bool:
    """点击下一步/继续/提交按钮(v1.0 _click_next_or_submit + Continue)

    优先级: Next > Continue > Submit。返回 True 表示成功点击。

    e2e(2026-07-22):JobsDB 一键申请的求职信等步骤底部是 "Continue"(非 "Next"),
    旧版只试 Next/Submit 会漏掉 Continue → 卡在求职信页。CONTINUE_BUTTON 选择器
    早已定义但从未被调用,此处补进优先级链。
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

    # 其次: Continue 按钮(求职信等步骤的实际前进按钮)
    continue_btn = await page.query_selector(CONTINUE_BUTTON)
    if continue_btn:
        is_visible = await continue_btn.is_visible()
        if is_visible:
            if human:
                await human.mouse.click_element(continue_btn)
            else:
                await continue_btn.click()
            await asyncio.sleep(2)
            return True

    # 最后: Submit 按钮
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
