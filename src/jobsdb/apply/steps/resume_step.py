"""
resume_step — 简历选择步骤

v1.0 _handle_resume_step 的逻辑:确认默认简历选中(单选/下拉),点 Next/Submit。
"""

import asyncio

from src.browser.ports.page_controller import PageController
from src.jobsdb.apply.steps.navigation import click_next_or_submit
from src.jobsdb.selectors import DEFAULT_RESUME_RADIO, RESUME_DROPDOWN, RESUME_SELECTION


class ResumeStep:
    """RESUME_SELECTION 步骤处理器"""

    async def detect(self, page: PageController) -> bool:
        # 由 detectors.detect_current_step 判定;此处保留接口一致性
        return bool(await page.query_selector(RESUME_SELECTION))

    async def handle(self, page: PageController, human=None) -> bool:
        """处理简历选择(v1.0 _handle_resume_step)"""
        try:
            # 检查默认简历是否选中
            default_radio = await page.query_selector(DEFAULT_RESUME_RADIO)
            if default_radio:
                is_checked = await default_radio.is_checked()
                if not is_checked:
                    if human:
                        await human.mouse.click_element(default_radio)
                    else:
                        await default_radio.click()
                    await asyncio.sleep(0.5)
            else:
                # 尝试下拉
                dropdown = await page.query_selector(RESUME_DROPDOWN)
                if dropdown:
                    options = await dropdown.query_selector_all("option")
                    if len(options) > 0:
                        await dropdown.select_option(index=0)
                        await asyncio.sleep(0.5)

            # 点击下一步按钮
            return await click_next_or_submit(page, human)

        except Exception as e:
            from loguru import logger
            logger.warning(f"Resume step error: {e}")
            return False
