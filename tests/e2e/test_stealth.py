"""
TC-01, TC-02: Stealth 反指纹测试
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestStealthPatches:
    """Stealth 反指纹 — P0 核心测试"""

    @pytest.mark.asyncio
    async def test_tc01_navigator_webdriver_is_undefined(self, mock_page):
        """
        TC-01: 验证 navigator.webdriver 为 undefined

        反检测的基础：如果 navigator.webdriver !== undefined，
        网站立刻知道这是自动化浏览器。
        """
        result = await mock_page.evaluate("() => navigator.webdriver")
        assert result is None or result is False or result == {}, \
            f"navigator.webdriver should be undefined, got: {result!r} (type: {type(result)})"

    @pytest.mark.asyncio
    async def test_tc01_navigator_webdriver_not_present_in_keys(self, mock_page):
        """
        TC-01 补充：检查 'webdriver' 不在 navigator 的可枚举属性中
        """
        result = await mock_page.evaluate("""
            () => {
                const keys = Object.keys(navigator);
                return keys.includes('webdriver');
            }
        """)
        assert result is False, "navigator.webdriver should not be enumerable"

    @pytest.mark.asyncio
    async def test_tc02_webgl_vendor_is_not_google(self, mock_page):
        """
        TC-02: 验证 WebGL vendor 被伪装

        Playwright 默认 WebGL vendor 是 "Google Inc. (NVIDIA)"，
        我们需要伪装成 Intel Inc.。
        """
        result = await mock_page.evaluate("""
            () => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl');
                if (!gl) return null;
                return gl.getParameter(0x9245);  // UNMASKED_VENDOR_WEBGL
            }
        """)
        print(f"WebGL Vendor: {result}")
        # 允许 Intel 或任何非 Google 的值
        if result:
            assert "Google" not in str(result), \
                f"WebGL vendor should not contain 'Google', got: {result}"

    @pytest.mark.asyncio
    async def test_tc02_webgl_renderer_is_set(self, mock_page):
        """
        TC-02 补充：验证 WebGL renderer 不是空值
        """
        result = await mock_page.evaluate("""
            () => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl');
                if (!gl) return null;
                return gl.getParameter(0x9246);  // UNMASKED_RENDERER_WEBGL
            }
        """)
        print(f"WebGL Renderer: {result}")
        assert result is not None and result != "", \
            "WebGL renderer should not be empty for stealth"

    @pytest.mark.asyncio
    async def test_plugins_array_not_empty(self, mock_page):
        """
        TC-02 补充：验证 navigator.plugins 不是空数组

        真实浏览器有插件（如 PDF viewer），自动化浏览器通常是空的。
        """
        result = await mock_page.evaluate("""
            () => {
                return {
                    length: navigator.plugins.length,
                    names: Array.from(navigator.plugins).map(p => p.name)
                };
            }
        """)
        assert result["length"] > 0, \
            f"navigator.plugins should not be empty, got: {result}"

    @pytest.mark.asyncio
    async def test_navigator_languages_realistic(self, mock_page):
        """
        TC-02 补充：验证 navigator.languages 设置合理
        """
        result = await mock_page.evaluate("() => navigator.languages")
        assert result and len(result) > 0, "navigator.languages should not be empty"
        assert any("zh" in str(lang) for lang in result) or any("en" in str(lang) for lang in result), \
            f"Should contain zh or en languages, got: {result}"
