from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BrowserConfig(BaseModel):
    """浏览器配置"""
    headless: bool = False
    window_width: int = 1920
    window_height: int = 1080
    user_data_dir: str = "./data/browser_profile"
    locale: str = "zh-HK"
    timezone_id: str = "Asia/Hong_Kong"
    geolocation: dict = Field(default_factory=lambda: {
        "latitude": 22.3193,
        "longitude": 114.1694,
    })
    viewport: dict = Field(default_factory=lambda: {
        "width": 1920,
        "height": 1080,
    })
    proxy: Optional[str] = None  # e.g., "http://127.0.0.1:7890"


class JobsDBConfig(BaseModel):
    """JobsDB 平台配置"""
    login_url: str = "https://hk.jobsdb.com/"
    homepage_url: str = "https://hk.jobsdb.com/"
    email: Optional[str] = None
    password: Optional[str] = None


class LoginConfig(BaseModel):
    """登录策略配置

    mode:
    - "auto":   自动填邮箱密码登录(需要真实凭证,可能触发风控/验证码)
    - "manual": 打开浏览器等用户手动登录(可自己过验证码),
                登录态由 Chromium 持久化 profile 保存,一次登录长期复用
    """
    mode: str = "auto"
    manual_wait_minutes: int = 30      # manual 模式等待用户登录的最大时长
    poll_interval_seconds: float = 7.5  # manual 模式轮询登录态的间隔

    @validator("mode")
    def validate_mode(cls, v):
        if v not in ("auto", "manual"):
            raise ValueError("login.mode must be 'auto' or 'manual'")
        return v


class AccountConfig(BaseModel):
    """账户配置（多账户支持）"""
    alias: str                    # 账户别名，如 "personal" / "work"
    email: str
    password: str                 # 从 accounts/<alias>.json 读取
    notes: Optional[str] = None


class SimulationConfig(BaseModel):
    """人类行为模拟配置"""
    typing_typo_probability: float = 0.04
    typing_base_delay_ms: float = 80.0
    typing_delay_variance_ms: float = 40.0
    mouse_bezier_points: int = 25
    mouse_movement_speed_mean_ms: float = 10.0
    mouse_movement_speed_std_ms: float = 3.0
    scroll_min_duration_ms: float = 800.0
    scroll_max_duration_ms: float = 1400.0

    @validator("typing_typo_probability")
    def validate_typo_prob(cls, v):
        if not 0 <= v <= 1:
            raise ValueError("typo_probability must be between 0 and 1")
        return v


class SchedulerConfig(BaseModel):
    """调度策略配置"""
    max_applies_per_session: int = 10
    max_per_hour: int = 10
    max_per_day: int = 30
    min_delay_between_seconds: float = 60.0  # 1 minute + 抖动(测试用,原 v1.0 为 180s 保守值)
    session_min_duration_minutes: float = 15.0
    # 高峰时段排除（香港时间）
    peak_hours_exclude: list = Field(default_factory=lambda: [
        {"start": 9, "end": 11},   # 早上
        {"start": 14, "end": 16},  # 下午
    ])


class StorageConfig(BaseModel):
    """数据存储配置"""
    database_path: str = "./data/jobsdb.db"
    screenshots_dir: str = "./data/screenshots"
    cookies_file: str = "./data/cookies.json"


class MonitoringConfig(BaseModel):
    """监控与日志配置"""
    log_level: str = "INFO"
    log_file: str = "./data/logs/jobsdb_{time}.log"
    log_rotation: str = "1 week"
    log_retention: str = "1 month"
    screenshot_on_error: bool = True
    alert_on_captcha: bool = True
    # 检测怀疑阈值：连续失败多少次后触发降级
    suspicion_threshold: int = 2


class AppConfig(BaseSettings):
    """应用总配置"""
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    active_account: str = "default"  # 当前活跃账户别名
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    jobsdb: JobsDBConfig = Field(default_factory=JobsDBConfig)
    login: LoginConfig = Field(default_factory=LoginConfig)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)

    def ensure_directories(self) -> None:
        """确保所有数据目录存在"""
        Path(self.storage.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.storage.screenshots_dir).mkdir(parents=True, exist_ok=True)
        Path(self.monitoring.log_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.browser.user_data_dir).mkdir(parents=True, exist_ok=True)


# 全局配置实例（lazy load）
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = AppConfig()
        _config.ensure_directories()
    return _config


def set_config(config: AppConfig) -> None:
    """设置全局配置（主要用于测试）"""
    global _config
    _config = config
