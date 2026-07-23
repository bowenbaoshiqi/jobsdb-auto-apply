"""
单元测试: 求职信步骤选 "Don't include a cover letter"

e2e(2026-07-22)暴露的回归:JobsDB 一键申请的求职信步骤是一页式单选表单,
label[for] radio id 动态(如 id-_r_2d_),无固定选择器。旧版 CoverLetterStep
只填 textarea + 点 Next,对不上真实 DOM → 流程卡死在求职信页。

本测试锁定修复后的行为:
1. detect:按 label 文本含 "cover letter" 识别(evaluate JS)
2. handle:点 "Don't include a cover letter"(evaluate JS),再点 Continue 前进
3. detect_current_step:真实单选页(无 COVER_LETTER_SECTION)→ COVER_LETTER(非 UNKNOWN)
4. click_next_or_submit:Next 缺席时点 Continue(真实页底部按钮)

用 FakePageController.evaluate 按 JS 表达式字符串预设返回值,不起浏览器。
"""

import pytest

from src.browser.fake.fake_page import FakeElement, FakePageController
from src.jobsdb.apply.detectors import detect_current_step
from src.jobsdb.apply.step_base import ApplyStep
from src.jobsdb.apply.steps import CoverLetterStep
from src.jobsdb.apply.steps.cover_letter_js import (
    _CLICK_NO_COVER_LETTER_JS,
    _HAS_COVER_LETTER_JS,
)
from src.jobsdb.apply.steps.navigation import click_next_or_submit
from src.jobsdb.selectors import CONTINUE_BUTTON, NEXT_STEP_BUTTON


def _make_page() -> FakePageController:
    return FakePageController(url="https://hk.jobsdb.com/job/123/apply")


# ═══════════════════════════════════════════════════════
#  CoverLetterStep.detect: 真实单选页(按 label 文本)
# ═══════════════════════════════════════════════════════

class TestCoverLetterDetect:
    @pytest.mark.asyncio
    async def test_detect_real_radio_page_by_text(self):
        """真实求职信单选页(evaluate 命中 "cover letter")→ True

        真实 DOM 无 COVER_LETTER_SECTION 属性,靠 label 文本识别。
        """
        page = _make_page()
        page.set_eval_result(_HAS_COVER_LETTER_JS, True)
        step = CoverLetterStep()
        assert await step.detect(page) is True

    @pytest.mark.asyncio
    async def test_detect_non_cover_letter_page(self):
        """非求职信页(evaluate 不命中)→ False"""
        page = _make_page()
        page.set_eval_result(_HAS_COVER_LETTER_JS, False)
        step = CoverLetterStep()
        assert await step.detect(page) is False

    @pytest.mark.asyncio
    async def test_detect_falls_back_to_section_selector(self):
        """旧 DOM 变体(有 COVER_LETTER_SECTION)→ True(兜底选择器)"""
        from src.jobsdb.selectors import COVER_LETTER_SECTION
        page = _make_page()
        page.set_element(COVER_LETTER_SECTION, FakeElement())
        # 即使 evaluate 未预设(None→ falsy),兜底选择器命中即 True
        step = CoverLetterStep()
        assert await step.detect(page) is True


# ═══════════════════════════════════════════════════════
#  CoverLetterStep.handle: 点 "Don't include a cover letter" → Continue
# ═══════════════════════════════════════════════════════

class TestCoverLetterHandle:
    @pytest.mark.asyncio
    async def test_handle_clicks_no_cover_letter_then_continue(self):
        """核心修复:选 "Don't include a cover letter" + 点 Continue → True

        真实单选页:evaluate 点击 JS 返回 True,Continue 可见 → 点击前进。
        """
        page = _make_page()
        page.set_eval_result(_CLICK_NO_COVER_LETTER_JS, True)
        continue_btn = FakeElement(visible=True)
        page.set_element(CONTINUE_BUTTON, continue_btn)

        step = CoverLetterStep()
        result = await step.handle(page)

        assert result is True
        assert continue_btn.click.call_count == 1

    @pytest.mark.asyncio
    async def test_handle_falls_back_to_textarea_when_no_radio(self):
        """职位强制要求求职信(无 "Don't include" 选项)→ fallback 填 textarea

        点击 JS 返回 False 时,找 textarea 写通用求职信,再点 Continue 前进。
        """
        from src.jobsdb.selectors import COVER_LETTER_TEXTAREA
        page = _make_page()
        page.set_eval_result(_CLICK_NO_COVER_LETTER_JS, False)
        textarea = FakeElement(visible=True)
        page.set_element(COVER_LETTER_TEXTAREA, textarea)
        continue_btn = FakeElement(visible=True)
        page.set_element(CONTINUE_BUTTON, continue_btn)

        step = CoverLetterStep()
        result = await step.handle(page)

        assert result is True
        assert textarea.fill.call_count == 1
        assert continue_btn.click.call_count == 1

    @pytest.mark.asyncio
    async def test_handle_returns_false_when_no_way_forward(self):
        """选不上且无 Continue/Next/Submit → False"""
        page = _make_page()
        page.set_eval_result(_CLICK_NO_COVER_LETTER_JS, False)
        # 不预设 textarea,也不预设任何前进按钮
        step = CoverLetterStep()
        result = await step.handle(page)
        assert result is False


# ═══════════════════════════════════════════════════════
#  click_next_or_submit: Continue 优先级
# ═══════════════════════════════════════════════════════

class TestClickNextOrSubmitContinue:
    @pytest.mark.asyncio
    async def test_clicks_continue_when_no_next(self):
        """无 Next 但有 Continue → 点 Continue(真实求职信页场景)"""
        page = _make_page()
        continue_btn = FakeElement(visible=True)
        page.set_element(CONTINUE_BUTTON, continue_btn)
        assert await click_next_or_submit(page) is True
        assert continue_btn.click.call_count == 1

    @pytest.mark.asyncio
    async def test_next_takes_priority_over_continue(self):
        """Next 和 Continue 都在 → 优先 Next(优先级链 Next > Continue > Submit)"""
        page = _make_page()
        next_btn = FakeElement(visible=True)
        continue_btn = FakeElement(visible=True)
        page.set_element(NEXT_STEP_BUTTON, next_btn)
        page.set_element(CONTINUE_BUTTON, continue_btn)
        assert await click_next_or_submit(page) is True
        assert next_btn.click.call_count == 1
        assert continue_btn.click.call_count == 0


# ═══════════════════════════════════════════════════════
#  detect_current_step: 真实单选页 → COVER_LETTER(非 UNKNOWN)
# ═══════════════════════════════════════════════════════

class TestDetectCurrentStepCoverLetter:
    @pytest.mark.asyncio
    async def test_real_radio_page_detected_as_cover_letter(self):
        """e2e 回归:真实求职信单选页 → COVER_LETTER,不再判 UNKNOWN 卡死

        旧版 detect_current_step 只认 COVER_LETTER_SECTION 选择器(真实页无此属性)
        → 误判 UNKNOWN → 流程循环不前。修复后按 label 文本识别。
        """
        page = _make_page()
        page.set_eval_result(_HAS_COVER_LETTER_JS, True)
        step = await detect_current_step(page)
        assert step is ApplyStep.COVER_LETTER

    @pytest.mark.asyncio
    async def test_non_cover_page_not_cover_letter(self):
        """非求职信页 → 不判 COVER_LETTER"""
        page = _make_page()
        page.set_eval_result(_HAS_COVER_LETTER_JS, False)
        step = await detect_current_step(page)
        assert step is not ApplyStep.COVER_LETTER
