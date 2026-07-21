"""
单元测试: utils/screenshot (capture_screenshot / save_page_html)

用 FakePageController 测,不起浏览器。
"""

import pytest

from src.browser.fake.fake_page import FakePageController
from src.utils.screenshot import capture_screenshot, generate_session_id, save_page_html


class TestCaptureScreenshot:
    @pytest.mark.asyncio
    async def test_returns_filepath(self, tmp_path):
        page = FakePageController()
        path = await capture_screenshot(page, "test_shot.png", screenshots_dir=str(tmp_path))
        assert "test_shot" in path

    @pytest.mark.asyncio
    async def test_creates_directory(self, tmp_path):
        """目录不存在时自动创建"""
        page = FakePageController()
        nested = tmp_path / "deep" / "shots"
        await capture_screenshot(page, "x.png", screenshots_dir=str(nested))
        assert nested.exists()

    @pytest.mark.asyncio
    async def test_default_filename_uses_timestamp(self, tmp_path):
        """无 filename → 生成时间戳文件名"""
        page = FakePageController()
        path = await capture_screenshot(page, screenshots_dir=str(tmp_path))
        assert "screenshot_" in path
        assert path.endswith(".png")

    @pytest.mark.asyncio
    async def test_screenshot_failure_returns_empty(self, tmp_path):
        """截图抛异常 → 返回空串(不中断)"""
        page = FakePageController()

        async def raise_screenshot(*a, **kw):
            raise RuntimeError("disk full")

        page.screenshot = raise_screenshot
        path = await capture_screenshot(page, "x", screenshots_dir=str(tmp_path))
        assert path == ""


class TestSavePageHtml:
    @pytest.mark.asyncio
    async def test_saves_html_content(self, tmp_path):
        page = FakePageController()
        page.set_body_text("<html>hello</html>")
        path = await save_page_html(page, "page1.html", data_dir=str(tmp_path))
        assert path.endswith("page1.html")
        with open(path) as fh:
            content = fh.read()
        assert "hello" in content

    @pytest.mark.asyncio
    async def test_failure_returns_empty(self, tmp_path):
        page = FakePageController()

        async def raise_content():
            raise RuntimeError("fail")

        page.content = raise_content
        path = await save_page_html(page, "x.html", data_dir=str(tmp_path))
        assert path == ""


class TestGenerateSessionId:
    def test_returns_string(self):
        sid = generate_session_id()
        assert isinstance(sid, str)
        assert len(sid) > 0

    def test_with_account_prefix(self):
        sid = generate_session_id("myaccount")
        assert sid.startswith("myaccount_")

    def test_unique(self):
        """连续调用产生不同 ID"""
        a = generate_session_id()
        b = generate_session_id()
        assert a != b
