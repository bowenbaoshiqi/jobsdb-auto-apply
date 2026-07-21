"""
单元测试: ComponentFactory + DefaultFactory

验证工厂接口的 10 个 create 方法齐全,DefaultFactory 生产真实组件。
FakeFactory 生产内存假组件(供 Orchestrator 单测)。
"""

import inspect

import pytest

from src.factory import ComponentFactory, DefaultFactory, FakeFactory


# ═══════════════════════════════════════════════════════
#  ComponentFactory 接口(10 个 create 方法)
# ═══════════════════════════════════════════════════════

class TestComponentFactoryInterface:
    """验证工厂接口有 10 个独立 create 方法(对应 v1.0 10 个依赖)"""

    EXPECTED_METHODS = [
        "create_browser",
        "create_database",
        "create_queue_manager",
        "create_rate_limiter",
        "create_timing_optimizer",
        "create_tracker",
        "create_alert_manager",
        "create_stats",
        "create_login_handler",
        "create_scraper",
    ]

    def test_all_methods_exist(self):
        for method in self.EXPECTED_METHODS:
            assert hasattr(ComponentFactory, method), f"缺少 {method}"

    def test_exactly_ten_methods(self):
        """不多不少 10 个 create 方法(不过度抽象)"""
        create_methods = [m for m in dir(ComponentFactory) if m.startswith("create_")]
        assert len(create_methods) == 10


# ═══════════════════════════════════════════════════════
#  DefaultFactory(生产真实组件)
# ═══════════════════════════════════════════════════════

class TestDefaultFactory:
    def setup_method(self):
        self.factory = DefaultFactory()

    def test_implements_all_methods(self):
        for method in TestComponentFactoryInterface.EXPECTED_METHODS:
            assert callable(getattr(self.factory, method)), f"未实现 {method}"

    def test_create_database_returns_database(self):
        from src.storage.database import Database
        db = self.factory.create_database(":memory:")
        assert isinstance(db, Database)

    def test_create_database_sets_account(self):
        """create_database 应接受 account_alias 并隔离"""
        db = self.factory.create_database(":memory:", account_alias="test_acct")
        assert db.account_alias == "test_acct"

    def test_create_timing_optimizer(self):
        from src.scheduler.queue import TimingOptimizer
        from config.settings import SchedulerConfig
        opt = self.factory.create_timing_optimizer(SchedulerConfig())
        assert isinstance(opt, TimingOptimizer)

    def test_create_tracker(self):
        from src.monitor.tracker import ApplicationTracker
        from src.storage.database import Database
        db = Database(":memory:")
        db.set_account("x")
        tracker = self.factory.create_tracker(db)
        assert isinstance(tracker, ApplicationTracker)

    def test_create_stats(self):
        from src.monitor.tracker import StatsAggregator
        from src.storage.database import Database
        db = Database(":memory:")
        db.set_account("x")
        stats = self.factory.create_stats(db)
        assert isinstance(stats, StatsAggregator)

    def test_create_alert_manager(self):
        from src.monitor.tracker import AlertManager
        alert = self.factory.create_alert_manager(alert_on_captcha=True)
        assert isinstance(alert, AlertManager)


# ═══════════════════════════════════════════════════════
#  FakeFactory(生产内存假组件,供 Orchestrator 单测)
# ═══════════════════════════════════════════════════════

class TestFakeFactory:
    def setup_method(self):
        self.factory = FakeFactory()

    def test_implements_all_methods(self):
        for method in TestComponentFactoryInterface.EXPECTED_METHODS:
            assert callable(getattr(self.factory, method)), f"未实现 {method}"

    def test_create_database_returns_in_memory(self):
        """FakeFactory 的 database 不落盘(内存)"""
        db = self.factory.create_database(":memory:", account_alias="fake")
        # 应能正常用,不依赖文件
        assert db is not None

    def test_create_browser_returns_fake(self):
        """FakeFactory 的 browser 是 FakeBrowser(不起真实浏览器)"""
        from src.browser.ports.browser_port import BrowserPort
        browser = self.factory.create_browser("fake_acct")
        assert isinstance(browser, BrowserPort)
