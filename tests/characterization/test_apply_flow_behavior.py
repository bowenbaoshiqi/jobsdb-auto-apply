"""
特征化测试: jobsdb/apply_flow.py

锁定 ApplyFlow 的核心输入输出行为。用 AsyncMock 造 Page,不起浏览器。
这是阶段3拆分 apply_flow 的安全网 — 拆分后这些测试必须仍绿。

锁定路径:
1. CAPTCHA 检测 → ApplyStatus.CAPTCHA
2. 成功提交 → ApplyStatus.SUBMITTED
3. 步骤失败 → ApplyStatus.FAILED
4. 超过最大步数 → FAILED "Max steps exceeded"
5. _detect_current_step 的各分支识别
6. _check_captcha / _check_success 的判定逻辑
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.jobsdb.apply.detectors import (
    check_captcha,
    check_success,
    detect_current_step,
    get_error_message,
)
from src.jobsdb.apply.flow import ApplyFlow, ApplyStep
from src.storage.models import ApplyStatus


def make_mock_element(visible=True, checked=False, text=None):
    """造一个 mock ElementHandle"""
    elem = AsyncMock()
    elem.is_visible = AsyncMock(return_value=visible)
    elem.is_checked = AsyncMock(return_value=checked)
    elem.text_content = AsyncMock(return_value=text)
    elem.click = AsyncMock()
    elem.get_attribute = AsyncMock(return_value=None)
    return elem


def make_mock_page(selector_map=None, body_text="", query_selector_all_map=None):
    """
    造 mock Page。
    selector_map: {selector: element_or_None} 控制 query_selector 返回
    query_selector_all_map: {selector: [elements]} 控制 query_selector_all 返回
    body_text: body 文本内容(用于 _check_success 的文本匹配)
    """
    selector_map = selector_map or {}
    query_selector_all_map = query_selector_all_map or {}

    page = AsyncMock()

    async def query_selector(sel):
        return selector_map.get(sel)

    async def query_selector_all(sel):
        return query_selector_all_map.get(sel, [])

    page.query_selector = query_selector
    page.query_selector_all = query_selector_all
    page.text_content = AsyncMock(return_value=body_text)
    page.wait_for_selector = AsyncMock()
    page.url = "https://hk.jobsdb.com/job/123/apply"
    return page


# ═══════════════════════════════════════════════════════
#  _check_captcha
# ═══════════════════════════════════════════════════════

class TestCheckCaptcha:
    @pytest.mark.asyncio
    async def test_recaptcha_detected(self):
        """RECAPTCHA_IFRAME 存在 → True"""
        from src.jobsdb.selectors import RECAPTCHA_IFRAME
        page = make_mock_page(selector_map={RECAPTCHA_IFRAME: make_mock_element()})
        flow = ApplyFlow(page)
        assert await check_captcha(page) is True

    @pytest.mark.asyncio
    async def test_no_captcha_returns_false(self):
        """无 captcha 元素 → False"""
        page = make_mock_page(selector_map={})
        flow = ApplyFlow(page)
        assert await check_captcha(page) is False

    @pytest.mark.asyncio
    async def test_hcaptcha_detected(self):
        """hCaptcha 元素存在 → True"""
        page = make_mock_page(selector_map={
            'iframe[src*="hcaptcha"], .h-captcha': make_mock_element()
        })
        flow = ApplyFlow(page)
        assert await check_captcha(page) is True


# ═══════════════════════════════════════════════════════
#  _check_success
# ═══════════════════════════════════════════════════════

class TestCheckSuccess:
    @pytest.mark.asyncio
    async def test_success_message_element_present(self):
        """SUCCESS_MESSAGE 元素存在 → True"""
        from src.jobsdb.selectors import SUCCESS_MESSAGE
        page = make_mock_page(selector_map={SUCCESS_MESSAGE: make_mock_element()})
        flow = ApplyFlow(page)
        assert await check_success(page) is True

    @pytest.mark.asyncio
    async def test_success_modal_present(self):
        """SUCCESS_MODAL 元素存在 → True"""
        from src.jobsdb.selectors import SUCCESS_MODAL
        page = make_mock_page(selector_map={SUCCESS_MODAL: make_mock_element()})
        flow = ApplyFlow(page)
        assert await check_success(page) is True

    @pytest.mark.asyncio
    async def test_success_by_body_text_english(self):
        """body 含 "Application submitted" → True"""
        page = make_mock_page(body_text="Great! Application submitted successfully.")
        flow = ApplyFlow(page)
        assert await check_success(page) is True

    @pytest.mark.asyncio
    async def test_success_by_body_text_chinese(self):
        """body 含 "申请已提交" → True"""
        page = make_mock_page(body_text="您的申请已提交")
        flow = ApplyFlow(page)
        assert await check_success(page) is True

    @pytest.mark.asyncio
    async def test_no_success_indicators_returns_false(self):
        """无任何成功标识 → False"""
        page = make_mock_page(body_text="Some random page content")
        flow = ApplyFlow(page)
        assert await check_success(page) is False


# ═══════════════════════════════════════════════════════
#  _detect_current_step
# ═══════════════════════════════════════════════════════

class TestDetectCurrentStep:
    @pytest.mark.asyncio
    async def test_detects_submitted_when_success(self):
        """已成功(有 SUCCESS_MESSAGE)→ SUBMITTED"""
        from src.jobsdb.selectors import SUCCESS_MESSAGE
        page = make_mock_page(selector_map={SUCCESS_MESSAGE: make_mock_element()})
        flow = ApplyFlow(page)
        step = await detect_current_step(page)
        assert step == ApplyStep.SUBMITTED

    @pytest.mark.asyncio
    async def test_detects_resume_selection_by_element(self):
        """有 RESUME_SELECTION 元素 → RESUME_SELECTION"""
        from src.jobsdb.selectors import RESUME_SELECTION
        page = make_mock_page(selector_map={RESUME_SELECTION: make_mock_element()})
        flow = ApplyFlow(page)
        step = await detect_current_step(page)
        assert step == ApplyStep.RESUME_SELECTION

    @pytest.mark.asyncio
    async def test_detects_cover_letter_by_element(self):
        """有 COVER_LETTER_SECTION → COVER_LETTER"""
        from src.jobsdb.selectors import COVER_LETTER_SECTION
        page = make_mock_page(selector_map={COVER_LETTER_SECTION: make_mock_element()})
        flow = ApplyFlow(page)
        step = await detect_current_step(page)
        assert step == ApplyStep.COVER_LETTER

    @pytest.mark.asyncio
    async def test_detects_review_by_submit_button(self):
        """有可见 SUBMIT_APPLICATION_BUTTON → REVIEW"""
        from src.jobsdb.selectors import SUBMIT_APPLICATION_BUTTON
        page = make_mock_page(selector_map={
            SUBMIT_APPLICATION_BUTTON: make_mock_element(visible=True)
        })
        flow = ApplyFlow(page)
        step = await detect_current_step(page)
        assert step == ApplyStep.REVIEW

    @pytest.mark.asyncio
    async def test_detects_unknown_when_nothing_matches(self):
        """无任何识别元素 → UNKNOWN"""
        page = make_mock_page(selector_map={})
        flow = ApplyFlow(page)
        step = await detect_current_step(page)
        assert step == ApplyStep.UNKNOWN


# ═══════════════════════════════════════════════════════
#  apply() 主流程 — 核心输入输出
# ═══════════════════════════════════════════════════════

class TestApplyMainFlow:
    @pytest.mark.asyncio
    async def test_apply_returns_captcha_when_detected(self):
        """检测到 CAPTCHA → 返回 CAPTCHA 状态"""
        from src.jobsdb.selectors import RECAPTCHA_IFRAME
        page = make_mock_page(selector_map={RECAPTCHA_IFRAME: make_mock_element()})
        flow = ApplyFlow(page)

        result = await flow.apply("job-123")

        assert result.status == ApplyStatus.CAPTCHA
        assert result.job_id == "job-123"
        assert "CAPTCHA" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_apply_returns_submitted_on_success(self):
        """成功提交 → 返回 SUBMITTED"""
        from src.jobsdb.selectors import SUCCESS_MESSAGE
        # 页面已有成功标识
        page = make_mock_page(selector_map={SUCCESS_MESSAGE: make_mock_element()})
        flow = ApplyFlow(page)

        result = await flow.apply("job-456")

        assert result.status == ApplyStatus.SUBMITTED
        assert result.job_id == "job-456"
        assert result.duration_seconds is not None

    @pytest.mark.asyncio
    async def test_apply_max_steps_exceeded(self):
        """超过最大步数 → FAILED "Max steps exceeded" """
        # 页面永远是 UNKNOWN 状态(无可识别元素),会循环到 max_steps
        page = make_mock_page(selector_map={})
        flow = ApplyFlow(page, max_steps=3)

        result = await flow.apply("job-789")

        assert result.status == ApplyStatus.FAILED
        assert "Max steps" in (result.error_message or "")


# ═══════════════════════════════════════════════════════
#  ApplyStep 枚举
# ═══════════════════════════════════════════════════════

class TestApplyStepEnum:
    def test_step_values(self):
        """锁定枚举值(阶段3拆分后枚举保留)"""
        assert ApplyStep.RESUME_SELECTION.value == "resume_selection"
        assert ApplyStep.QUESTIONS.value == "questions"
        assert ApplyStep.COVER_LETTER.value == "cover_letter"
        assert ApplyStep.REVIEW.value == "review"
        assert ApplyStep.SUBMITTED.value == "submitted"
        assert ApplyStep.UNKNOWN.value == "unknown"

    def test_step_count(self):
        """锁定 6 个步骤"""
        assert len(list(ApplyStep)) == 6
