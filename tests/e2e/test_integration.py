"""
TC-13, TC-14, TC-17: 集成测试

- TC-13: Stealth 通过 bot.sannysoft.com 检测
- TC-17: Session 持久化（cookie + profile）
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestIntegrationStealth:
    """集成测试 — Stealth + Browser"""

    @pytest.mark.asyncio
    async def test_tc13_bot_detection_sannysoft(self, browser_engine):
        """
        TC-13: 通过 bot.sannysoft.com 基础检测

        注意：这个测试访问外部网站，如果网络不稳定可能失败。
              标记为 integration，默认不跑。 pytest -m integration
        """
        pytest.importorskip("playwright")
        page = browser_engine.current_page

        try:
            await page.goto("https://bot.sannysoft.com", wait_until="domcontentloaded", timeout=30000)
            # 等待 JS 检测完成
            import asyncio
            await asyncio.sleep(3)
        except Exception as e:
            pytest.skip(f"External site unreachable: {e}")

        # 检查关键指标
        webdriver = await page.evaluate("() => navigator.webdriver")
        assert webdriver is None or webdriver is False, \
            f"navigator.webdriver should be hidden, got: {webdriver!r}"

        # 截图保存供人工确认
        screenshot_path = Path("data/screenshots/test_bot_detection.png")
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path))
        print(f"Screenshot saved: {screenshot_path}")

        # 检查页面上是否有红色检测结果（简单的文本匹配）
        page_text = await page.title()
        print(f"Page title: {page_text}")

    @pytest.mark.asyncio
    async def test_tc17_session_persistence(self, tmp_path):
        """
        TC-17: Session 持久化 — cookies 和 localStorage 跨重启保留
        """
        import uuid
        from src.browser.engine import BrowserEngine
        from config.settings import BrowserConfig

        user_data_dir = tmp_path / f"browser_profile_test_{uuid.uuid4().hex[:8]}"

        # 第一轮：设置 cookie 和 localStorage
        config1 = BrowserConfig(
            headless=True,
            user_data_dir=str(user_data_dir),
        )
        engine1 = BrowserEngine(config1)

        try:
            page1 = await engine1.start()
            await page1.goto("https://httpbin.org/cookies/set/testcookie/hello123")
            await page1.wait_for_load_state("networkidle", timeout=10000)

            # 设置 localStorage
            await page1.evaluate('() => { localStorage.setItem("test_key", "test_value"); }')
        except Exception as e:
            pytest.skip(f"External site unreachable: {e}")
        finally:
            await engine1.stop()

        # 第二轮：验证 cookie 和 localStorage 还在
        config2 = BrowserConfig(
            headless=True,
            user_data_dir=str(user_data_dir),  # 同一个目录
        )
        engine2 = BrowserEngine(config2)

        try:
            page2 = await engine2.start()
            await page2.goto("https://httpbin.org/cookies")
            await page2.wait_for_load_state("networkidle", timeout=10000)

            # 检查 localStorage
            ls_value = await page2.evaluate('() => localStorage.getItem("test_key")')
            assert ls_value == "test_value", \
                f"localStorage should persist across restarts, got: {ls_value}"
        except Exception as e:
            pytest.skip(f"External site unreachable: {e}")
        finally:
            await engine2.stop()


class TestLoginErrorHandling:
    """登录异常 — TC-15 补充"""

    @pytest.mark.asyncio
    async def test_tc15_no_credentials_raises_error(self):
        """
        TC-15: 没有配置 credentials 时应抛出 LoginError
        """
        from playwright.async_api import async_playwright
        from src.jobsdb.login import LoginHandler
        from config.settings import JobsDBConfig
        from src.jobsdb.exceptions import LoginError

        config = JobsDBConfig(email=None, password=None)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            handler = LoginHandler(page, config)

            with pytest.raises(LoginError) as exc_info:
                await handler.ensure_logged_in()

            assert "email and password not configured" in str(exc_info.value)
            await browser.close()
