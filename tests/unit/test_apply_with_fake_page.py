"""
阶段2.5 示范测试: 用 FakePageController 跑 jobsdb 逻辑,毫秒级,不起浏览器

证明收益: 阶段2 的浏览器抽象层让 apply_flow 的逻辑分支能用纯内存假实现测,
不再需要启动 Chromium。这条测试是阶段3(apply_flow 拆分)的 TDD 基础。

跑法: uv run pytest tests/unit/test_apply_with_fake_page.py -v
"""

import pytest

from src.browser.fake.fake_page import FakeElement, FakePageController
from src.jobsdb.apply.detectors import check_captcha, check_success
from src.jobsdb.apply.flow import ApplyFlow
from src.jobsdb.selectors import RECAPTCHA_IFRAME
from src.storage.models import ApplyStatus


class TestApplyFlowWithFakePage:
    """用 FakePageController 驱动 ApplyFlow — 不起浏览器,毫秒级"""

    @pytest.mark.asyncio
    async def test_captcha_branch_returns_captcha_status(self):
        """预设 RECAPTCHA 元素存在 → apply() 立即返回 CAPTCHA 状态"""
        page = FakePageController()
        page.set_element(RECAPTCHA_IFRAME, FakeElement(visible=True))

        flow = ApplyFlow(page)
        result = await flow.apply("job-123")

        assert result.status is ApplyStatus.CAPTCHA
        assert result.job_id == "job-123"
        assert "CAPTCHA" in result.error_message

    @pytest.mark.asyncio
    async def test_no_captcha_does_not_short_circuit(self):
        """无 CAPTCHA → 不返回 CAPTCHA 状态(继续走 _dismiss_popups 等)"""
        page = FakePageController()
        # 不预设任何元素 → _check_captcha 返回 False
        flow = ApplyFlow(page, max_steps=2)
        result = await flow.apply("job-456")

        # 无 apply form / 无成功标识 → 最终走 UNKNOWN 分支,多次后 FAILED
        assert result.status is not ApplyStatus.CAPTCHA

    @pytest.mark.asyncio
    async def test_check_captcha_directly_with_fake(self):
        """直接调 check_captcha,验证 FakePageController 驱动 jobsdb 内部方法"""
        page = FakePageController()
        ApplyFlow(page)

        # 未预设 → False
        assert await check_captcha(page) is False

        # 预设 reCAPTCHA → True
        page.set_element(RECAPTCHA_IFRAME, FakeElement(visible=True))
        assert await check_captcha(page) is True

    @pytest.mark.asyncio
    async def test_check_success_with_fake_body_text(self):
        """check_success 的文本匹配用 FakePageController.text_content('body') 驱动"""
        page = FakePageController()
        ApplyFlow(page)

        # 未预设 body 文本 → False
        assert await check_success(page) is False

        # 预设成功文案 → True
        page.set_body_text("Application submitted successfully")
        assert await check_success(page) is True

        # 另一种成功文案
        page.set_body_text("Thank you for applying")
        assert await check_success(page) is True

        # 无关文本 → False
        page.set_body_text("Please complete the form")
        assert await check_success(page) is False


class TestFakePageSpeed:
    """验证 FakePageController 驱动的测试是毫秒级(对比 e2e 秒级)"""

    @pytest.mark.asyncio
    async def test_apply_captcha_runs_in_milliseconds(self, benchmark=None):
        """apply(CAPTCHA 分支) 应在 50ms 内完成(实际通常 <5ms)"""
        import time

        page = FakePageController()
        page.set_element(RECAPTCHA_IFRAME, FakeElement(visible=True))
        flow = ApplyFlow(page)

        start = time.perf_counter()
        await flow.apply("job-speed")
        elapsed_ms = (time.perf_counter() - start) * 1000

        # 50ms 上限远高于实际,留余量给 CI/慢机器
        assert elapsed_ms < 50, f"FakePage 测试应毫秒级,实际 {elapsed_ms:.1f}ms"
