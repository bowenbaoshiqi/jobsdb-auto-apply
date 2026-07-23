"""
单元测试: storage/cookies (CookieStore)

文件级 cookie 持久化,无浏览器。
"""

import time

import pytest

from src.storage.cookies import CookieStore


@pytest.fixture
def store(tmp_path):
    return CookieStore(str(tmp_path / "cookies.json"))


class TestCookieStoreSaveLoad:
    def test_save_then_load(self, store):
        cookies = [{"name": "session", "value": "abc", "domain": "hk.jobsdb.com"}]
        store.save(cookies)
        loaded = store.load()
        assert loaded == cookies

    def test_load_returns_empty_when_no_file(self, store):
        """无文件 → 空列表"""
        assert store.load() == []

    def test_save_creates_parent_dir(self, tmp_path):
        """save 自动创建父目录"""
        nested = tmp_path / "nested" / "deep" / "cookies.json"
        store = CookieStore(str(nested))
        store.save([{"name": "x"}])
        assert nested.exists()

    def test_load_corrupt_file_returns_empty(self, store):
        """损坏的 JSON → 空列表(不抛)"""
        store.cookies_file.write_text("{not valid json")
        assert store.load() == []


class TestCookieStoreClear:
    def test_clear_removes_file(self, store):
        store.save([{"name": "x"}])
        assert store.cookies_file.exists()
        store.clear()
        assert not store.cookies_file.exists()

    def test_clear_when_no_file_no_error(self, store):
        """无文件时 clear 不报错"""
        store.clear()  # 不抛


class TestCookieStoreFresh:
    def test_fresh_false_when_no_file(self, store):
        assert store.is_fresh() is False

    def test_fresh_true_when_recent(self, store):
        store.save([{"name": "x"}])
        assert store.is_fresh(max_age_hours=12) is True

    def test_fresh_false_when_old(self, store):
        """过期文件 → False"""
        store.save([{"name": "x"}])
        # 把 mtime 改到 24 小时前
        old_time = time.time() - 24 * 3600
        import os
        os.utime(store.cookies_file, (old_time, old_time))
        assert store.is_fresh(max_age_hours=12) is False
