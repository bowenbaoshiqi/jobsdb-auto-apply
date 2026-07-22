"""
单元测试: 只投 Quick Apply 职位(标准 Apply 直接跳过)

e2e 暴露(2026-07-22):JobsDB 职位详情页的标准 "Apply" 按钮选择器对不上新版 DOM,
导致连续 2 个职位 "Apply button not found" → FAILED → 触发 detection 阈值中止会话。
但用户只要 Quick Apply 的职位,标准 Apply 的本就不该投(会跳到外部站点/需手动填表)。

决策:把 "找不到 quick-apply 按钮" 从 FAILED 降级为 SKIPPED(reason=not_quick_apply),
不进连续失败计数,不会误触中止阈值。get_apply_button 只认 quick-apply/easy-apply,
不再认标准 APPLY_BUTTON / APPLY_NOW_BUTTON。

用 FakePageController 注入,不起浏览器。QUICK_APPLY_BUTTON 选择器存在 = quick-apply 职位。
"""

import pytest

from src.browser.fake.fake_page import FakeElement, FakePageController
from src.factory import FakeFactory
from src.jobsdb.job_detail import JobDetailPage
from src.jobsdb.selectors import (
    APPLY_BUTTON,
    APPLY_NOW_BUTTON,
    EASY_APPLY_BUTTON,
    JOB_DETAIL_TITLE,
    QUICK_APPLY_BUTTON,
)
from src.orchestrator import Orchestrator
from src.storage.models import ApplyStatus, JobListing


def _make_page() -> FakePageController:
    return FakePageController(url="https://hk.jobsdb.com/job/123")


def _make_orch() -> Orchestrator:
    """FakeFactory 注入的 Orchestrator,已 _init_browser(page_controller 可用)"""
    from src.accounts.registry import Account
    orch = Orchestrator(
        account=Account(alias="test", email="t@e.com", password="x"),
        factory=FakeFactory(),
    )
    return orch


def _preset_job_title(orch: Orchestrator) -> None:
    """预设 JOB_DETAIL_TITLE 元素,让 navigate_with_simulation 通过 _get_job_title 检查

    JobDetailPage.navigate_with_simulation 导航后会查标题,无标题 → JobNotFoundError。
    测试只关心 apply 按钮分支,所以给个标题让导航不报错。
    """
    orch.page_controller.set_element(
        JOB_DETAIL_TITLE, FakeElement(text="Some Job Title", visible=True)
    )


# ═══════════════════════════════════════════════════════
#  JobDetailPage.get_apply_button: 只认 quick/easy apply
# ═══════════════════════════════════════════════════════

class TestGetApplyButtonQuickApplyOnly:
    @pytest.mark.asyncio
    async def test_quick_apply_button_returned(self):
        """有 QUICK_APPLY_BUTTON 元素 → 返回它"""
        page = _make_page()
        page.set_element(QUICK_APPLY_BUTTON, FakeElement(visible=True))
        detail = JobDetailPage(page)

        btn = await detail.get_apply_button()

        assert btn is not None

    @pytest.mark.asyncio
    async def test_easy_apply_button_returned(self):
        """有 EASY_APPLY_BUTTON 元素 → 返回它(easy apply 也算一键投递)"""
        page = _make_page()
        page.set_element(EASY_APPLY_BUTTON, FakeElement(visible=True))
        detail = JobDetailPage(page)

        btn = await detail.get_apply_button()

        assert btn is not None

    @pytest.mark.asyncio
    async def test_standard_apply_button_not_returned(self):
        """只有标准 APPLY_BUTTON(无 quick/easy) → 不返回(标准 apply 不投)"""
        page = _make_page()
        page.set_element(APPLY_BUTTON, FakeElement(visible=True))
        detail = JobDetailPage(page)

        btn = await detail.get_apply_button()

        assert btn is None  # 标准 apply 不算 quick-apply

    @pytest.mark.asyncio
    async def test_apply_now_button_not_returned(self):
        """只有 APPLY_NOW_BUTTON(无 quick/easy) → 不返回(Apply now 常跳外部)"""
        page = _make_page()
        page.set_element(APPLY_NOW_BUTTON, FakeElement(visible=True))
        detail = JobDetailPage(page)

        btn = await detail.get_apply_button()

        assert btn is None

    @pytest.mark.asyncio
    async def test_no_apply_button_returns_none(self):
        """页面无任何 apply 按钮 → None"""
        page = _make_page()
        detail = JobDetailPage(page)

        btn = await detail.get_apply_button()

        assert btn is None


# ═══════════════════════════════════════════════════════
#  Orchestrator._apply_to_job: 无 quick-apply → SKIPPED(非 FAILED)
# ═══════════════════════════════════════════════════════

class TestApplyToJobSkipsNonQuickApply:
    @pytest.mark.asyncio
    async def test_standard_apply_job_is_skipped_not_failed(self):
        """标准 Apply 职位(无 quick-apply 按钮)→ SKIPPED,reason=not_quick_apply

        关键回归保护:之前是 FAILED,连续 2 个就触发 detection 中止。
        """
        orch = _make_orch()
        await orch._init_browser()
        _preset_job_title(orch)
        # 预设标准 APPLY_BUTTON 存在(模拟旧版 DOM / 外部跳转职位),
        # 但无 QUICK_APPLY / EASY_APPLY
        orch.page_controller.set_element(APPLY_BUTTON, FakeElement(visible=True))

        job = JobListing(id="job-std", title="Std Role", company="Co",
                         url="https://hk.jobsdb.com/job/std")
        result = await orch._apply_to_job(job)

        assert result.status is ApplyStatus.SKIPPED
        assert result.reason == "not_quick_apply"

    @pytest.mark.asyncio
    async def test_no_button_job_is_skipped_not_failed(self):
        """页面找不到任何 apply 按钮 → SKIPPED(非 FAILED)"""
        orch = _make_orch()
        await orch._init_browser()
        _preset_job_title(orch)
        # 不预设任何按钮元素

        job = JobListing(id="job-none", title="NoBtn", company="Co",
                         url="https://hk.jobsdb.com/job/none")
        result = await orch._apply_to_job(job)

        assert result.status is ApplyStatus.SKIPPED
        assert result.reason == "not_quick_apply"

    @pytest.mark.asyncio
    async def test_skip_does_not_increment_consecutive_failures(self):
        """SKIPPED(非 quick-apply)不计入连续失败 → 不触发 detection 中止

        端到端验证用户场景:连续多个标准 apply 职位不应误触中止阈值。
        """
        orch = _make_orch()
        await orch._init_browser()
        _preset_job_title(orch)
        orch.page_controller.set_element(APPLY_BUTTON, FakeElement(visible=True))

        job = JobListing(id="job-std", title="Std", company="Co",
                         url="https://hk.jobsdb.com/job/std")
        result = await orch._apply_to_job(job)

        assert result.status is ApplyStatus.SKIPPED
        # SKIPPED 不应让 consecutive_failures 增长
        assert orch.consecutive_failures == 0
