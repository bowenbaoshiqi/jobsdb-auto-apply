"""
单元测试: apply/steps/* StepHandler

每个 StepHandler 用 FakePageController 独立测,不起浏览器(毫秒级)。
这是阶段3拆分的核心收益 — v1.0 测 apply_flow 必须 Chromium,v2.0 毫秒级。
"""

import pytest

from src.browser.fake.fake_page import FakeElement, FakePageController
from src.jobsdb.apply.detectors import (
    check_captcha,
    check_success,
    detect_current_step,
)
from src.jobsdb.apply.flow import ApplyFlow, ApplyStep
from src.jobsdb.apply.steps import (
    CoverLetterStep,
    QuestionsStep,
    ResumeStep,
    ReviewStep,
    SubmitStep,
)
from src.jobsdb.apply.steps.navigation import click_next_or_submit
from src.jobsdb.apply.steps.popup_dismiss import run as dismiss_popups
from src.jobsdb.selectors import (
    ADDITIONAL_QUESTIONS,
    COVER_LETTER_SECTION,
    COVER_LETTER_TEXTAREA,
    DEFAULT_RESUME_RADIO,
    NEXT_STEP_BUTTON,
    RECAPTCHA_IFRAME,
    RESUME_SELECTION,
    SUBMIT_APPLICATION_BUTTON,
    SUCCESS_MESSAGE,
)


# ═══════════════════════════════════════════════════════
#  ResumeStep
# ═══════════════════════════════════════════════════════

class TestResumeStep:
    @pytest.mark.asyncio
    async def test_detect_when_resume_selection_present(self):
        page = FakePageController()
        page.set_element(RESUME_SELECTION, FakeElement())
        step = ResumeStep()
        assert await step.detect(page) is True

    @pytest.mark.asyncio
    async def test_detect_when_absent(self):
        page = FakePageController()
        step = ResumeStep()
        assert await step.detect(page) is False

    @pytest.mark.asyncio
    async def test_handle_clicks_next_when_visible(self):
        """有可见 Next 按钮 → 点击,返回 True"""
        page = FakePageController()
        next_btn = FakeElement(visible=True)
        page.set_element(NEXT_STEP_BUTTON, next_btn)
        step = ResumeStep()
        result = await step.handle(page)
        assert result is True
        assert next_btn.click.call_count == 1

    @pytest.mark.asyncio
    async def test_handle_no_buttons_returns_false(self):
        """无 Next/Submit → False"""
        page = FakePageController()
        step = ResumeStep()
        assert await step.handle(page) is False


# ═══════════════════════════════════════════════════════
#  QuestionsStep
# ═══════════════════════════════════════════════════════

class TestQuestionsStep:
    @pytest.mark.asyncio
    async def test_detect_when_questions_present(self):
        page = FakePageController()
        page.set_element(ADDITIONAL_QUESTIONS, FakeElement())
        step = QuestionsStep()
        assert await step.detect(page) is True

    @pytest.mark.asyncio
    async def test_detect_when_absent(self):
        page = FakePageController()
        step = QuestionsStep()
        assert await step.detect(page) is False

    @pytest.mark.asyncio
    async def test_handle_no_questions_clicks_next(self):
        """无问题但有可见 Next → 点击返回 True"""
        page = FakePageController()
        next_btn = FakeElement(visible=True)
        page.set_element(NEXT_STEP_BUTTON, next_btn)
        step = QuestionsStep()
        assert await step.handle(page) is True


# ═══════════════════════════════════════════════════════
#  CoverLetterStep
# ═══════════════════════════════════════════════════════

class TestCoverLetterStep:
    @pytest.mark.asyncio
    async def test_detect_when_section_present(self):
        page = FakePageController()
        page.set_element(COVER_LETTER_SECTION, FakeElement())
        step = CoverLetterStep()
        assert await step.detect(page) is True

    @pytest.mark.asyncio
    async def test_detect_when_absent(self):
        page = FakePageController()
        step = CoverLetterStep()
        assert await step.detect(page) is False

    @pytest.mark.asyncio
    async def test_handle_optional_cover_letter_clicks_next(self):
        """非必填求职信 → 直接点 Next"""
        page = FakePageController()
        next_btn = FakeElement(visible=True)
        page.set_element(NEXT_STEP_BUTTON, next_btn)
        step = CoverLetterStep()
        assert await step.handle(page) is True


# ═══════════════════════════════════════════════════════
#  ReviewStep
# ═══════════════════════════════════════════════════════

class TestReviewStep:
    @pytest.mark.asyncio
    async def test_detect_when_submit_visible(self):
        page = FakePageController()
        page.set_element(SUBMIT_APPLICATION_BUTTON, FakeElement(visible=True))
        step = ReviewStep()
        assert await step.detect(page) is True

    @pytest.mark.asyncio
    async def test_detect_when_submit_hidden(self):
        page = FakePageController()
        page.set_element(SUBMIT_APPLICATION_BUTTON, FakeElement(visible=False))
        step = ReviewStep()
        assert await step.detect(page) is False

    @pytest.mark.asyncio
    async def test_handle_no_submit_button_returns_false(self):
        """无提交按钮 → False"""
        page = FakePageController()
        step = ReviewStep()
        assert await step.handle(page) is False

    @pytest.mark.asyncio
    async def test_handle_clicks_submit_and_checks_success(self):
        """有可见提交按钮 → 点击,返回 check_success 结果"""
        page = FakePageController()
        submit_btn = FakeElement(visible=True)
        page.set_element(SUBMIT_APPLICATION_BUTTON, submit_btn)
        # 预设成功 → check_success 返回 True
        page.set_element(SUCCESS_MESSAGE, FakeElement())
        step = ReviewStep()
        result = await step.handle(page)
        assert submit_btn.click.call_count == 1
        assert result is True


# ═══════════════════════════════════════════════════════
#  SubmitStep
# ═══════════════════════════════════════════════════════

class TestSubmitStep:
    @pytest.mark.asyncio
    async def test_detect_when_success(self):
        page = FakePageController()
        page.set_element(SUCCESS_MESSAGE, FakeElement())
        step = SubmitStep()
        assert await step.detect(page) is True

    @pytest.mark.asyncio
    async def test_detect_when_not_success(self):
        page = FakePageController()
        step = SubmitStep()
        assert await step.detect(page) is False

    @pytest.mark.asyncio
    async def test_handle_returns_true(self):
        """已提交,handle 无操作返回 True"""
        page = FakePageController()
        step = SubmitStep()
        assert await step.handle(page) is True


# ═══════════════════════════════════════════════════════
#  navigation (click_next_or_submit)
# ═══════════════════════════════════════════════════════

class TestClickNextOrSubmit:
    @pytest.mark.asyncio
    async def test_clicks_next_when_visible(self):
        page = FakePageController()
        next_btn = FakeElement(visible=True)
        page.set_element(NEXT_STEP_BUTTON, next_btn)
        assert await click_next_or_submit(page) is True
        assert next_btn.click.call_count == 1

    @pytest.mark.asyncio
    async def test_clicks_submit_when_no_next(self):
        page = FakePageController()
        submit_btn = FakeElement(visible=True)
        page.set_element(SUBMIT_APPLICATION_BUTTON, submit_btn)
        assert await click_next_or_submit(page) is True
        assert submit_btn.click.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_false_when_neither_visible(self):
        page = FakePageController()
        assert await click_next_or_submit(page) is False


# ═══════════════════════════════════════════════════════
#  popup_dismiss
# ═══════════════════════════════════════════════════════

class TestPopupDismiss:
    @pytest.mark.asyncio
    async def test_no_popups_no_error(self):
        """无弹窗 → 不报错"""
        page = FakePageController()
        await dismiss_popups(page)  # 不抛

    @pytest.mark.asyncio
    async def test_clicks_existing_popup(self):
        """有弹窗元素 → 点击它"""
        from src.jobsdb.selectors import COOKIE_BANNER
        page = FakePageController()
        banner = FakeElement()
        page.set_element(COOKIE_BANNER, banner)
        await dismiss_popups(page)
        assert banner.click.call_count == 1


# ═══════════════════════════════════════════════════════
#  detectors(经 FakePage 驱动,毫秒级)
# ═══════════════════════════════════════════════════════

class TestDetectorsWithFake:
    @pytest.mark.asyncio
    async def test_check_captcha_recaptcha(self):
        page = FakePageController()
        page.set_element(RECAPTCHA_IFRAME, FakeElement())
        assert await check_captcha(page) is True

    @pytest.mark.asyncio
    async def test_check_captcha_none(self):
        page = FakePageController()
        assert await check_captcha(page) is False

    @pytest.mark.asyncio
    async def test_check_success_by_text(self):
        page = FakePageController()
        page.set_body_text("Application submitted")
        assert await check_success(page) is True

    @pytest.mark.asyncio
    async def test_detect_current_step_submitted(self):
        page = FakePageController()
        page.set_element(SUCCESS_MESSAGE, FakeElement())
        assert await detect_current_step(page) == ApplyStep.SUBMITTED

    @pytest.mark.asyncio
    async def test_detect_current_step_unknown(self):
        page = FakePageController()
        assert await detect_current_step(page) == ApplyStep.UNKNOWN


# ═══════════════════════════════════════════════════════
#  ApplyFlow 集成(用 FakePage,毫秒级)
# ═══════════════════════════════════════════════════════

class TestApplyFlowIntegration:
    @pytest.mark.asyncio
    async def test_apply_captcha_short_circuits(self):
        """CAPTCHA → 立即返回 CAPTCHA 状态"""
        page = FakePageController()
        page.set_element(RECAPTCHA_IFRAME, FakeElement())
        flow = ApplyFlow(page)
        result = await flow.apply("job-1")
        from src.storage.models import ApplyStatus
        assert result.status is ApplyStatus.CAPTCHA

    @pytest.mark.asyncio
    async def test_apply_max_steps_exceeded(self):
        """无任何识别元素 → 超过 max_steps → FAILED 'Max steps exceeded'"""
        page = FakePageController()
        flow = ApplyFlow(page, max_steps=1)
        result = await flow.apply("job-2")
        from src.storage.models import ApplyStatus
        assert result.status is ApplyStatus.FAILED
        assert "Max steps exceeded" in result.error_message
