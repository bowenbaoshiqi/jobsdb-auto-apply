"""
review_step — 审核与提交步骤

v1.0 _handle_review_step 的逻辑:找提交按钮,点击,等待,确认成功。
这是最关键的动作(真正提交申请)。
"""

import asyncio

from loguru import logger

from src.browser.ports.page_controller import PageController
from src.jobsdb.apply.detectors import check_success
from src.jobsdb.selectors import CONFIRM_SUBMIT_BUTTON, SUBMIT_APPLICATION_BUTTON


class ReviewStep:
    """REVIEW 步骤处理器(点击提交)"""

    async def detect(self, page: PageController) -> bool:
        # 由 detectors 判定(Submit 按钮可见 → REVIEW)
        submit_btn = await page.query_selector(SUBMIT_APPLICATION_BUTTON)
        if submit_btn:
            return await submit_btn.is_visible()
        return False

    async def handle(self, page: PageController, human=None) -> bool:
        """处理审核与提交(v1.0 _handle_review_step)"""
        try:
            # 找提交按钮
            submit_btn = await page.query_selector(SUBMIT_APPLICATION_BUTTON)
            if not submit_btn:
                submit_btn = await page.query_selector(CONFIRM_SUBMIT_BUTTON)

            if not submit_btn:
                logger.error("Submit button not found")
                return False

            # 检查是否可点击
            is_visible = await submit_btn.is_visible()
            if not is_visible:
                logger.error("Submit button not visible")
                return False

            # 点击提交(最关键动作,加较长等待)
            logger.info("Clicking submit button")

            if human:
                await human.click_apply_button(submit_btn)
            else:
                await submit_btn.click()

            # 等待提交响应
            await asyncio.sleep(3)

            # 检查成功状态
            return await check_success(page)

        except Exception as e:
            logger.warning(f"Review step error: {e}")
            return False
