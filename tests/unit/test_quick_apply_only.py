"""
单元测试: 只投 Quick Apply 职位(标准 Apply 直接跳过)

v1.0 策略:JobsDB 职位只投 Quick/Easy Apply 的(一键申请,站内完成);
标准 "Apply"/"Apply now" 常跳外部站点或需手动填长表,不在自动投递范围。
v1.0 的 get_apply_button 用选择器优先级软实现(easy/quick 排前),
v2.0 强化为硬过滤:get_apply_button 只认 QUICK_APPLY_BUTTON / EASY_APPLY_BUTTON,
两者都没有 → orchestrator 判 SKIPPED(reason=not_quick_apply),非 FAILED。

e2e(2026-07-22)暴露的回归:旧版把 "找不到 quick-apply 按钮" 判 FAILED,
连续 2 个标准 apply 职位就触发 detection 阈值(=2)中止会话,0 成功。
SKIPPED 不进 consecutive_failures,不误触中止阈值。

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
    JOB_DETAIL_APPLY_LINK,
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
#  JobDetailPage.get_apply_button: 真实 DOM(统一 job-detail-apply 入口)
#
# e2e(2026-07-22)发现:当前 JobsDB quick/standard apply 共用同一个
#   <a data-automation="job-detail-apply"> 入口,区别只在按钮文案。
# 以下测试锁定这个真实行为的文案判定逻辑。
# ═══════════════════════════════════════════════════════

class TestGetApplyButtonUnifiedLink:
    @pytest.mark.asyncio
    async def test_unified_link_with_quick_apply_text_returned(self):
        """job-detail-apply 文案 "Quick apply" → 返回(真实 quick-apply 职位)"""
        page = _make_page()
        page.set_element(
            JOB_DETAIL_APPLY_LINK,
            FakeElement(text="Quick apply", visible=True),
        )
        detail = JobDetailPage(page)

        btn = await detail.get_apply_button()

        assert btn is not None

    @pytest.mark.asyncio
    async def test_unified_link_with_standard_apply_text_not_returned(self):
        """job-detail-apply 文案 "Apply" → None(标准 apply,跳过)

        这是 e2e 暴露的核心回归:之前统一入口的文案是 "Apply" 也被当 quick,
        或反过来 "Quick apply" 找不到选择器而 SKIPPED。
        """
        page = _make_page()
        page.set_element(
            JOB_DETAIL_APPLY_LINK,
            FakeElement(text="Apply", visible=True),
        )
        detail = JobDetailPage(page)

        btn = await detail.get_apply_button()

        assert btn is None

    @pytest.mark.asyncio
    async def test_unified_link_chinese_quick_apply_returned(self):
        """job-detail-apply 文案 "快速申請"(繁中)→ 返回"""
        page = _make_page()
        page.set_element(
            JOB_DETAIL_APPLY_LINK,
            FakeElement(text="快速申請", visible=True),
        )
        detail = JobDetailPage(page)

        btn = await detail.get_apply_button()

        assert btn is not None

    @pytest.mark.asyncio
    async def test_unified_link_invisible_returns_none(self):
        """job-detail-apply 存在但不可见 → None(等价于无按钮)"""
        page = _make_page()
        page.set_element(
            JOB_DETAIL_APPLY_LINK,
            FakeElement(text="Quick apply", visible=False),
        )
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
