"""
单元测试: FakePageController

验证纯内存假实现的预设/查询逻辑,不起任何浏览器。
"""

import pytest

from src.browser.fake.fake_page import FakeElement, FakePageController


class TestFakeElement:
    @pytest.mark.asyncio
    async def test_default_text_content(self):
        elem = FakeElement(text="hello")
        assert await elem.text_content() == "hello"

    @pytest.mark.asyncio
    async def test_default_is_visible(self):
        elem = FakeElement(visible=True)
        assert await elem.is_visible() is True

    @pytest.mark.asyncio
    async def test_is_checked(self):
        elem = FakeElement(checked=True)
        assert await elem.is_checked() is True

    @pytest.mark.asyncio
    async def test_get_attribute_default_none(self):
        elem = FakeElement()
        assert await elem.get_attribute("href") is None

    @pytest.mark.asyncio
    async def test_set_attribute(self):
        elem = FakeElement()
        elem.set_attribute("href", "http://x")
        assert await elem.get_attribute("href") == "http://x"

    @pytest.mark.asyncio
    async def test_click_records(self):
        elem = FakeElement()
        await elem.click()
        assert elem.click.call_count == 1


class TestFakePageControllerQuery:
    @pytest.mark.asyncio
    async def test_query_selector_returns_none_by_default(self):
        page = FakePageController()
        assert await page.query_selector(".x") is None

    @pytest.mark.asyncio
    async def test_set_element_then_query(self):
        page = FakePageController()
        elem = FakeElement(text="hi")
        page.set_element(".x", elem)
        assert await page.query_selector(".x") is elem

    @pytest.mark.asyncio
    async def test_set_element_none_removes(self):
        page = FakePageController()
        page.set_element(".x", FakeElement())
        page.set_element(".x", None)
        assert await page.query_selector(".x") is None

    @pytest.mark.asyncio
    async def test_get_text_returns_none_when_no_element(self):
        page = FakePageController()
        assert await page.get_text(".x") is None

    @pytest.mark.asyncio
    async def test_get_text_returns_text(self):
        page = FakePageController()
        page.set_text(".x", "hello")
        assert await page.get_text(".x") == "hello"

    @pytest.mark.asyncio
    async def test_set_visible(self):
        page = FakePageController()
        page.set_visible(".x", True)
        assert await page.is_visible(".x") is True
        assert await page.is_visible(".y") is False  # 未设置

    @pytest.mark.asyncio
    async def test_count_returns_list_length(self):
        page = FakePageController()
        page.set_elements(".item", [FakeElement(), FakeElement(), FakeElement()])
        assert await page.count(".item") == 3

    @pytest.mark.asyncio
    async def test_query_selector_all_default_empty(self):
        page = FakePageController()
        assert await page.query_selector_all(".x") == []


class TestFakePageControllerInteract:
    @pytest.mark.asyncio
    async def test_click_on_set_element(self):
        page = FakePageController()
        elem = FakeElement()
        page.set_element(".btn", elem)
        await page.click(".btn")
        assert elem.click.call_count == 1

    @pytest.mark.asyncio
    async def test_click_on_missing_element_no_error(self):
        """点不存在的元素不报错"""
        page = FakePageController()
        await page.click(".missing")  # 不抛异常

    @pytest.mark.asyncio
    async def test_fill_on_set_element(self):
        page = FakePageController()
        elem = FakeElement()
        page.set_element("#input", elem)
        await page.fill("#input", "value")
        assert elem.fill.call_count == 1

    @pytest.mark.asyncio
    async def test_type_text_no_error(self):
        page = FakePageController()
        await page.type_text("#input", "abc")  # 不抛

    @pytest.mark.asyncio
    async def test_wait_methods_no_error(self):
        page = FakePageController()
        await page.wait_for_selector(".x")
        await page.wait_for_timeout(100)


class TestFakePageControllerNav:
    @pytest.mark.asyncio
    async def test_goto_updates_url(self):
        page = FakePageController()
        await page.goto("http://new")
        assert page.url == "http://new"

    @pytest.mark.asyncio
    async def test_goto_records_calls(self):
        page = FakePageController()
        await page.goto("http://a")
        await page.goto("http://b")
        assert page._goto_calls == ["http://a", "http://b"]

    @pytest.mark.asyncio
    async def test_screenshot_records_path(self):
        page = FakePageController()
        await page.screenshot("/tmp/x.png")
        assert "/tmp/x.png" in page._screenshot_paths

    @pytest.mark.asyncio
    async def test_evaluate_returns_preset(self):
        page = FakePageController()
        page.set_eval_result("1+1", 2)
        assert await page.evaluate("1+1") == 2

    @pytest.mark.asyncio
    async def test_evaluate_returns_none_when_not_set(self):
        page = FakePageController()
        assert await page.evaluate("x") is None

    def test_is_closed_default_false(self):
        page = FakePageController()
        assert page.is_closed() is False

    @pytest.mark.asyncio
    async def test_text_content_body_returns_preset(self):
        page = FakePageController()
        page.set_body_text("Application submitted")
        assert await page.text_content("body") == "Application submitted"
