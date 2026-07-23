"""
questions_step — 附加问题步骤

v1.0 _handle_questions_step 的逻辑:遍历问题,按类型(下拉/文本/单选/复选)填写。
"""

import asyncio

from src.browser.ports.page_controller import PageController
from src.jobsdb.apply.steps.navigation import click_next_or_submit
from src.jobsdb.selectors import ADDITIONAL_QUESTIONS


class QuestionsStep:
    """QUESTIONS 步骤处理器"""

    async def detect(self, page: PageController) -> bool:
        return bool(await page.query_selector(ADDITIONAL_QUESTIONS))

    async def handle(self, page: PageController, human=None) -> bool:
        """处理附加问题(v1.0 _handle_questions_step)"""
        try:
            questions = await page.query_selector_all(ADDITIONAL_QUESTIONS)

            for question in questions:
                # 检查问题类型
                select = await question.query_selector("select")
                if select:
                    # 下拉选择
                    options = await select.query_selector_all("option")
                    # 选第一个非空选项
                    for i, option in enumerate(options):
                        value = await option.get_attribute("value")
                        if value and value.strip():
                            await select.select_option(index=i)
                            break
                    continue

                # 文本输入或文本域
                text_input = await question.query_selector(
                    'input[type="text"], textarea'
                )
                if text_input:
                    # 检测是否 Yes/No 问题
                    label = await question.query_selector("label, .question-label")
                    if label:
                        label_text = await label.text_content() or ""
                        label_lower = label_text.lower()

                        if "year" in label_lower and "experience" in label_lower:
                            await text_input.fill("3")
                        elif "salary" in label_lower or "expected" in label_lower:
                            await text_input.fill("Negotiable")
                        else:
                            await text_input.fill("N/A")
                    else:
                        await text_input.fill("N/A")
                    continue

                # 单选按钮
                radios = await question.query_selector_all('input[type="radio"]')
                if radios:
                    await radios[0].click()
                    continue

                # 复选框
                checkboxes = await question.query_selector_all('input[type="checkbox"]')
                if checkboxes:
                    await checkboxes[0].click()

            await asyncio.sleep(0.5)
            return await click_next_or_submit(page, human)

        except Exception as e:
            from loguru import logger
            logger.warning(f"Questions step error: {e}")
            return False
