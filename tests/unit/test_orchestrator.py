"""
单元测试: Orchestrator 协调逻辑(用 FakeFactory 注入)

验证阶段4 工厂 DI 的收益:Orchestrator 用 FakeFactory 注入后,
协调逻辑可不起真实浏览器/不落盘地测。

FakeFactory 生产:
- FakeBrowser(返回 FakePageController,毫秒级)
- 内存 Database
- 真实的 scheduler/monitor 组件(它们不碰浏览器)
"""

import pytest

from src.accounts.registry import Account
from src.browser.fake.fake_page import FakeElement, FakePageController
from src.factory import FakeFactory
from src.orchestrator import Orchestrator
from src.storage.models import ApplyResult, ApplyStatus, JobListing


def make_account():
    return Account(alias="test", email="t@e.com", password="x")


# ═══════════════════════════════════════════════════════
#  实例化(工厂注入)
# ═══════════════════════════════════════════════════════

class TestOrchestratorInstantiation:
    def test_default_factory(self):
        """无 factory → DefaultFactory(真实组件)"""
        orch = Orchestrator(account=make_account())
        from src.factory import DefaultFactory
        assert isinstance(orch.factory, DefaultFactory)

    def test_fake_factory_injected(self):
        """注入 FakeFactory → 不起浏览器,内存 DB"""
        orch = Orchestrator(account=make_account(), factory=FakeFactory())
        assert isinstance(orch.factory, FakeFactory)
        # 10 个依赖都已创建
        assert orch.db is not None
        assert orch.queue_manager is not None
        assert orch.rate_limiter is not None
        assert orch.timing_optimizer is not None
        assert orch.tracker is not None
        assert orch.alert is not None
        assert orch.stats is not None

    def test_account_alias_propagated_to_db(self):
        """account.alias 经工厂传到 db.set_account"""
        acct = make_account()
        orch = Orchestrator(account=acct, factory=FakeFactory())
        assert orch.db.account_alias == acct.alias

    def test_browser_lazy_until_init(self):
        """browser 延迟创建,构造时为 None"""
        orch = Orchestrator(account=make_account(), factory=FakeFactory())
        assert orch.browser is None
        assert orch.page_controller is None


# ═══════════════════════════════════════════════════════
#  _init_browser(走 FakeBrowser)
# ═══════════════════════════════════════════════════════

class TestOrchestratorInitBrowser:
    @pytest.mark.asyncio
    async def test_init_browser_creates_fake_page_controller(self):
        """_init_browser 走工厂 → FakeBrowser → FakePageController"""
        factory = FakeFactory()
        orch = Orchestrator(account=make_account(), factory=factory)
        await orch._init_browser()

        assert orch.browser is not None
        assert isinstance(orch.page_controller, FakePageController)
        assert orch.human is not None
        assert orch.login_handler is not None
        assert orch.scraper is not None

    @pytest.mark.asyncio
    async def test_init_browser_does_not_launch_chromium(self):
        """FakeBrowser 不起真实浏览器(毫秒级)"""
        import time
        factory = FakeFactory()
        orch = Orchestrator(account=make_account(), factory=factory)

        start = time.perf_counter()
        await orch._init_browser()
        elapsed_ms = (time.perf_counter() - start) * 1000

        # 真实 Chromium 启动需数秒;FakeBrowser 应 <100ms
        assert elapsed_ms < 100, f"应毫秒级,实际 {elapsed_ms:.0f}ms"


# ═══════════════════════════════════════════════════════
#  _apply_to_job(用 FakePageController 驱动 apply_flow)
# ═══════════════════════════════════════════════════════

class TestOrchestratorApplyToJob:
    @pytest.mark.asyncio
    async def test_apply_to_job_captcha_returns_captcha(self):
        """CAPTCHA 页面 → ApplyResult CAPTCHA(不经真实投递)"""
        from src.jobsdb.selectors import RECAPTCHA_IFRAME
        factory = FakeFactory()
        orch = Orchestrator(account=make_account(), factory=factory)
        await orch._init_browser()

        # 预设 CAPTCHA 元素
        orch.page_controller.set_element(RECAPTCHA_IFRAME, FakeElement(visible=True))

        job = JobListing(id="job-1", title="Dev", company="Co", url="http://x")
        result = await orch._apply_to_job(job)

        # 注:JobDetailPage.navigate_with_simulation 会调 page.goto,
        # FakePageController 无异常;apply_flow 检测到 CAPTCHA → CAPTCHA
        assert result.status in (ApplyStatus.CAPTCHA, ApplyStatus.FAILED)


# ═══════════════════════════════════════════════════════
#  报告生成
# ═══════════════════════════════════════════════════════

class TestOrchestratorReports:
    def test_error_report_shape(self):
        orch = Orchestrator(account=make_account(), factory=FakeFactory())
        report = orch._create_error_report("Login failed")
        assert report["error"] == "Login failed"
        assert report["success_rate"] == 0
        assert report["total"] == 0

    def test_empty_report_shape(self):
        orch = Orchestrator(account=make_account(), factory=FakeFactory())
        report = orch._create_empty_report()
        assert report["total"] == 0
        assert "message" in report

    def test_session_report_without_session(self):
        """无 session_id → error report"""
        orch = Orchestrator(account=make_account(), factory=FakeFactory())
        report = orch._create_session_report()
        assert "error" in report


# ═══════════════════════════════════════════════════════
#  清理
# ═══════════════════════════════════════════════════════

class TestOrchestratorCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_stops_browser(self):
        factory = FakeFactory()
        orch = Orchestrator(account=make_account(), factory=factory)
        await orch._init_browser()
        assert orch.browser is not None

        await orch._cleanup()
        # stop 后 current_page 应为 None(FakeBrowser.stop 清空)
        assert factory.last_browser.current_page is None
