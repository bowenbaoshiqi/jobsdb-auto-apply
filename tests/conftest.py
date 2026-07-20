"""
conftest.py — 测试共享 fixtures
"""

import asyncio
import pathlib
import uuid
from datetime import datetime

import pytest
import pytest_asyncio

# 确保项目根目录在 path 中（便于 import）
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config.settings import AppConfig, BrowserConfig, StorageConfig
from src.accounts.registry import Account
from src.storage.database import Database
from src.storage.models import JobListing, ApplyResult, ApplyStatus, SessionRecord, SessionStatus
from src.browser.engine import BrowserEngine


@pytest.fixture(scope="session")
def event_loop():
    """覆盖默认 event_loop fixture，使用 session scope"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def browser_engine():
    """
    启动测试浏览器，结束后自动关闭

    使用 headed=False（无头模式）以加快测试速度。
    注意：涉及截图/鼠标移动的测试可能需要 headed 模式，
          可在具体测试中覆盖。
    """
    config = BrowserConfig(
        headless=True,
        user_data_dir=f"./data/browser_profile_test_{uuid.uuid4().hex[:8]}",
    )
    engine = BrowserEngine(config)
    try:
        page = await engine.start()
        yield engine
    finally:
        await engine.stop()


@pytest_asyncio.fixture(scope="function")
async def mock_page(browser_engine):
    """提供已注入 stealth patches 的空 page"""
    page = browser_engine.current_page
    # 加载一个空白页面，确保 stealth patches 已注入
    await page.goto("about:blank")
    yield page


@pytest.fixture(scope="function")
def temp_database(tmp_path):
    """
    提供临时数据库（每个测试独立）

    使用 pytest 的 tmp_path fixture 确保每个测试有自己的 DB 文件。
    """
    db_path = tmp_path / "test_jobsdb.db"
    db = Database(str(db_path))
    yield db
    # 清理（可选，tmp_path 会自动清理）
    db_path.unlink(missing_ok=True)


@pytest.fixture
def sample_jobs():
    """提供 5 个测试职位列表"""
    return [
        JobListing(
            id="12345",
            title="Software Engineer",
            company="ABC Tech",
            location="Hong Kong",
            salary="HKD 30K-50K",
            url="https://www.jobsdb.com/hk/job/12345",
            posted_date="Today",
        ),
        JobListing(
            id="12346",
            title="Senior Developer",
            company="XYZ Corp",
            location="Kowloon",
            salary="HKD 40K-60K",
            url="https://www.jobsdb.com/hk/job/12346",
            posted_date="1 day ago",
        ),
        JobListing(
            id="12347",
            title="Full Stack Engineer",
            company="Startup Inc",
            location="Remote",
            salary=None,
            url="https://www.jobsdb.com/hk/job/12347",
            posted_date="2 days ago",
        ),
    ]


@pytest.fixture
def sample_config():
    """提供测试友好的配置"""
    return AppConfig(
        browser=BrowserConfig(
            headless=True,
            user_data_dir="./data/browser_profile_test",
        ),
        storage=StorageConfig(
            database_path="./data/test_jobsdb.db",
        ),
    )


@pytest.fixture
def sample_account():
    """提供测试账户"""
    return Account(alias="test_account", email="test@example.com", password="secret")


@pytest.fixture
def mock_apply_html():
    """
    提供 mock 投递表单 HTML 字符串
    用于 TC-20: 完整 E2E 投递流程测试
    """
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Mock Apply Page</title></head>
    <body>
        <div id="step-indicator">Step 1 of 4</div>

        <!-- Step 1: Resume Selection -->
        <div data-automation="resume-selection">
            <input type="radio" name="resume" value="default" checked>
            <label>Default Resume</label>
        </div>

        <button data-automation="next-step">Next</button>
    </body>
    </html>
    """
