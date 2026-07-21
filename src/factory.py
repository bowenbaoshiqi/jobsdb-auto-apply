"""
factory — ComponentFactory:生产 Orchestrator 所需组件的工厂

解耦 Orchestrator 的 10 个硬编码依赖。
- ComponentFactory:工厂接口(Protocol,10 个 create 方法)
- DefaultFactory:生产真实组件(等价 v1.0 行为)
- FakeFactory:生产内存假组件(Orchestrator 单测用,不起浏览器)

工厂放顶层(跨 browser/db/scheduler/monitor),10 个独立方法一一对应 v1.0 依赖。
"""

from typing import Optional, Protocol, runtime_checkable

from config.settings import AppConfig, JobsDBConfig, SchedulerConfig
from src.browser.fake.fake_browser import FakeBrowser
from src.browser.playwright_browser import PlaywrightBrowser
from src.browser.ports.browser_port import BrowserPort
from src.browser.ports.page_controller import PageController
from src.jobsdb.homepage import HomepageScraper
from src.jobsdb.login import LoginHandler
from src.monitor.tracker import AlertManager, ApplicationTracker, StatsAggregator
from src.scheduler.queue import ApplyQueue, RateLimiter, TimingOptimizer
from src.storage.database import Database


@runtime_checkable
class ComponentFactory(Protocol):
    """生产 Orchestrator 所需组件的工厂。10 个方法对应 v1.0 10 个依赖。"""

    def create_browser(self, account_alias: str) -> BrowserPort: ...
    def create_database(self, db_path: str, account_alias: str = "default") -> Database: ...
    def create_queue_manager(self, db: Database, config: SchedulerConfig) -> ApplyQueue: ...
    def create_rate_limiter(self, config: SchedulerConfig, db: Database) -> RateLimiter: ...
    def create_timing_optimizer(self, config: SchedulerConfig) -> TimingOptimizer: ...
    def create_tracker(self, db: Database) -> ApplicationTracker: ...
    def create_alert_manager(self, alert_on_captcha: bool = True) -> AlertManager: ...
    def create_stats(self, db: Database) -> StatsAggregator: ...
    def create_login_handler(self, page: PageController, config: JobsDBConfig,
                             human, account) -> LoginHandler: ...
    def create_scraper(self, page: PageController, human) -> HomepageScraper: ...


class DefaultFactory:
    """生产真实组件 — 每个方法等价于 v1.0 __init__/_init_browser 里 new 的同一个类。"""

    def __init__(self, config: Optional[AppConfig] = None):
        self._config = config

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            from config.settings import get_config
            self._config = get_config()
        return self._config

    def create_browser(self, account_alias: str) -> BrowserPort:
        # v1.0: BrowserEngine(self.config.browser, account_alias=...)
        return PlaywrightBrowser(self.config.browser, account_alias=account_alias)

    def create_database(self, db_path: str, account_alias: str = "default") -> Database:
        # v1.0: Database(self.config.storage.database_path); db.set_account(alias)
        db = Database(db_path)
        db.set_account(account_alias)
        return db

    def create_queue_manager(self, db: Database, config: SchedulerConfig) -> ApplyQueue:
        return ApplyQueue(db, config)

    def create_rate_limiter(self, config: SchedulerConfig, db: Database) -> RateLimiter:
        return RateLimiter(config, db)

    def create_timing_optimizer(self, config: SchedulerConfig) -> TimingOptimizer:
        return TimingOptimizer(config)

    def create_tracker(self, db: Database) -> ApplicationTracker:
        return ApplicationTracker(db)

    def create_alert_manager(self, alert_on_captcha: bool = True) -> AlertManager:
        return AlertManager(alert_on_captcha)

    def create_stats(self, db: Database) -> StatsAggregator:
        return StatsAggregator(db)

    def create_login_handler(self, page: PageController, config: JobsDBConfig,
                             human, account) -> LoginHandler:
        return LoginHandler(page, config, human, account)

    def create_scraper(self, page: PageController, human) -> HomepageScraper:
        return HomepageScraper(page, human)


class FakeFactory:
    """生产内存假组件 — Orchestrator 单测用,不起浏览器/不落盘。"""

    def __init__(self, config: Optional[AppConfig] = None):
        self._config = config
        # 暴露最后创建的假 browser,供测试预设页面状态
        self.last_browser: Optional[FakeBrowser] = None

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            from config.settings import get_config
            self._config = get_config()
        return self._config

    def create_browser(self, account_alias: str) -> BrowserPort:
        self.last_browser = FakeBrowser()
        return self.last_browser

    def create_database(self, db_path: str, account_alias: str = "default") -> Database:
        # 用内存 DB,不落盘
        db = Database(":memory:")
        db.set_account(account_alias)
        return db

    def create_queue_manager(self, db: Database, config: SchedulerConfig) -> ApplyQueue:
        return ApplyQueue(db, config)

    def create_rate_limiter(self, config: SchedulerConfig, db: Database) -> RateLimiter:
        return RateLimiter(config, db)

    def create_timing_optimizer(self, config: SchedulerConfig) -> TimingOptimizer:
        return TimingOptimizer(config)

    def create_tracker(self, db: Database) -> ApplicationTracker:
        return ApplicationTracker(db)

    def create_alert_manager(self, alert_on_captcha: bool = True) -> AlertManager:
        return AlertManager(alert_on_captcha)

    def create_stats(self, db: Database) -> StatsAggregator:
        return StatsAggregator(db)

    def create_login_handler(self, page: PageController, config: JobsDBConfig,
                             human, account) -> LoginHandler:
        return LoginHandler(page, config, human, account)

    def create_scraper(self, page: PageController, human) -> HomepageScraper:
        return HomepageScraper(page, human)
