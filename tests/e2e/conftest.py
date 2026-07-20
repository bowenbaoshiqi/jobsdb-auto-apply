"""
conftest.py — e2e 测试专用 fixtures

仅当运行 -m e2e (或显式收集 tests/e2e/) 时加载。
提供真实浏览器 fixture,单元测试不会触发。

v2.0: 通过 pytest_collection_modifyitems 自动给本目录所有测试打 e2e marker,
      无需在每个测试文件里手动加 @pytest.mark.e2e。
"""

import asyncio
import uuid

import pytest
import pytest_asyncio

from config.settings import BrowserConfig
from src.browser.engine import BrowserEngine


def pytest_collection_modifyitems(items):
    """自动给 tests/e2e/ 下所有收集到的测试打上 e2e marker。"""
    for item in items:
        # 只给本目录(path 在 e2e/ 下)的测试打标
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


@pytest_asyncio.fixture(scope="function")
async def browser_engine():
    """
    启动测试浏览器，结束后自动关闭

    使用 headless=True 以加快测试速度。
    注意：涉及截图/鼠标移动的测试可能需要 headed 模式，
          可在具体测试中覆盖。
    """
    config = BrowserConfig(
        headless=True,
        user_data_dir=f"./data/browser_profile_test_{uuid.uuid4().hex[:8]}",
    )
    engine = BrowserEngine(config)
    try:
        await engine.start()
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
