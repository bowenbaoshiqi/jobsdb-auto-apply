"""
cover_letter_step — 求职信步骤

v1.0 _handle_cover_letter_step 的逻辑:检查 textarea 是否必填,必填则填通用求职信。
(纯机械迁移,行为与 v1.0 一致)
"""

import asyncio

from src.browser.ports.page_controller import PageController
from src.jobsdb.apply.steps.navigation import click_next_or_submit
from src.jobsdb.selectors import COVER_LETTER_SECTION, COVER_LETTER_TEXTAREA

# v1.0 _handle_cover_letter_step 的通用求职信内容(不动)
_COVER_LETTER = (
    "Dear Hiring Manager,\n\n"
    "I am excited to apply for this position. "
    "With my relevant experience and skills, I believe I would be a great fit. "
    "I look forward to the opportunity to discuss how I can contribute to your team.\n\n"
    "Best regards"
)


class CoverLetterStep:
    """COVER_LETTER 步骤处理器"""

    async def detect(self, page: PageController) -> bool:
        return bool(await page.query_selector(COVER_LETTER_SECTION))

    async def handle(self, page: PageController, human=None) -> bool:
        """处理求职信(v1.0 _handle_cover_letter_step)"""
        try:
            textarea = await page.query_selector(COVER_LETTER_TEXTAREA)
            if textarea:
                # 检查是否必填
                is_required = await textarea.get_attribute("required")
                if is_required:
                    if human:
                        await human.fill_form_field(textarea, _COVER_LETTER)
                    else:
                        await textarea.fill(_COVER_LETTER)
                    await asyncio.sleep(0.5)

            return await click_next_or_submit(page, human)

        except Exception as e:
            from loguru import logger
            logger.warning(f"Cover letter step error: {e}")
            return False
