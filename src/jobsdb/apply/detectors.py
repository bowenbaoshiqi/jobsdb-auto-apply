"""
detectors — apply 流程的纯查询逻辑(无副作用)

从 v1.0 apply_flow.py 抽出的只读判定函数:当前步骤/成功/验证码/错误。
每个函数接收 PageController,返回判定结果。可独立用 FakePageController 单测。

逻辑与 v1.0 完全一致(机械迁移),selectors 不动。
"""

from typing import Optional

from src.browser.ports.page_controller import PageController
from src.jobsdb.apply.step_base import ApplyStep
from src.jobsdb.selectors import (
    ADDITIONAL_QUESTIONS,
    CONFIRM_SUBMIT_BUTTON,
    COVER_LETTER_SECTION,
    ERROR_MESSAGE,
    FORM_VALIDATION_ERROR,
    LOADING_SPINNER,
    RECAPTCHA_IFRAME,
    RESUME_SELECTION,
    STEP_INDICATOR,
    SUBMIT_APPLICATION_BUTTON,
    SUCCESS_MESSAGE,
    SUCCESS_MODAL,
)

# 成功文案(v1.0 _check_success 的 6 个指标,顺序不动)
_SUCCESS_INDICATORS = (
    "Application submitted",
    "successfully submitted",
    "Thank you for applying",
    "Application received",
    "申请已提交",
    "已成功提交",
)

# 登录态 cookie 名(v1.0 _check_login_status 用,login.py 保留)
LOGIN_COOKIE_NAMES = (
    "AccessToken", "RefreshToken", "JSESSIONID", "session_id",
    "auth_st", "user_status", "jsessionid", "access_token",
)


async def check_captcha(page: PageController) -> bool:
    """检查是否有 CAPTCHA(v1.0 _check_captcha)"""
    try:
        captcha = await page.query_selector(RECAPTCHA_IFRAME)
        if captcha:
            return True

        hcaptcha = await page.query_selector(
            'iframe[src*="hcaptcha"], .h-captcha'
        )
        if hcaptcha:
            return True

        return False
    except Exception:
        return False


async def check_success(page: PageController) -> bool:
    """检查是否提交成功(v1.0 _check_success)"""
    try:
        success = await page.query_selector(SUCCESS_MESSAGE)
        if success:
            return True

        success_modal = await page.query_selector(SUCCESS_MODAL)
        if success_modal:
            return True

        # 检查页面文本
        page_text = await page.text_content("body")
        if page_text and any(indicator in page_text for indicator in _SUCCESS_INDICATORS):
            return True

        return False
    except Exception:
        return False


async def detect_current_step(page: PageController) -> ApplyStep:
    """检测当前阶段(v1.0 _detect_current_step)"""
    # 先检查成功状态
    if await check_success(page):
        return ApplyStep.SUBMITTED

    # 检查阶段指示器
    step_indicator = await page.query_selector(STEP_INDICATOR)
    if step_indicator:
        try:
            current_step_text = await step_indicator.text_content()
            if current_step_text:
                text_lower = current_step_text.lower()
                if "resume" in text_lower:
                    return ApplyStep.RESUME_SELECTION
                elif "question" in text_lower:
                    return ApplyStep.QUESTIONS
                elif "cover" in text_lower:
                    return ApplyStep.COVER_LETTER
                elif "review" in text_lower:
                    return ApplyStep.REVIEW
        except Exception:
            pass

    # 按表单元素判定
    if await page.query_selector(RESUME_SELECTION):
        return ApplyStep.RESUME_SELECTION

    if await page.query_selector(ADDITIONAL_QUESTIONS):
        return ApplyStep.QUESTIONS

    if await page.query_selector(COVER_LETTER_SECTION):
        return ApplyStep.COVER_LETTER

    # 可提交状态(Submit 按钮可见,但尚未提交)
    submit_btn = await page.query_selector(SUBMIT_APPLICATION_BUTTON)
    if submit_btn:
        is_visible = await submit_btn.is_visible()
        if is_visible:
            # 检查是否最终审核阶段
            if await page.query_selector(CONFIRM_SUBMIT_BUTTON):
                return ApplyStep.REVIEW
            # 可能是一页式申请表,需检查是否还有其他步骤
            return ApplyStep.REVIEW

    # 检查是否错误页
    error = await page.query_selector(ERROR_MESSAGE)
    if error:
        return ApplyStep.UNKNOWN

    # 检查加载中
    loading = await page.query_selector(LOADING_SPINNER)
    if loading:
        import asyncio
        await asyncio.sleep(2)
        return await detect_current_step(page)

    return ApplyStep.UNKNOWN


async def get_error_message(page: PageController) -> Optional[str]:
    """获取错误信息(v1.0 _get_error_message)"""
    try:
        error = await page.query_selector(ERROR_MESSAGE)
        if error:
            text = await error.text_content()
            return text.strip() if text else None

        validation = await page.query_selector(FORM_VALIDATION_ERROR)
        if validation:
            text = await validation.text_content()
            return text.strip() if text else None
    except Exception:
        pass
    return None
