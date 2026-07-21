"""
TC-Account: 账户注册表测试
"""

import shutil

import pytest

from src.accounts.registry import Account, AccountRegistry


class TestAccountRegistry:
    """账户注册表 — P1 核心测试"""

    @pytest.fixture(autouse=True)
    def clean_accounts_dir(self, tmp_path):
        """每个测试开始前清理 accounts/ 临时目录"""
        registry = AccountRegistry(accounts_dir=tmp_path / "accounts_test")
        yield registry
        if registry.accounts_dir.exists():
            shutil.rmtree(registry.accounts_dir)

    def test_add_and_get(self, clean_accounts_dir):
        """添加和读取账户"""
        registry = clean_accounts_dir
        acc = Account(alias="personal", email="me@test.com", password="secret")
        registry.save(acc)

        loaded = registry.get("personal")
        assert loaded is not None
        assert loaded.alias == "personal"
        assert loaded.email == "me@test.com"
        assert loaded.password == "secret"

    def test_list_all(self, clean_accounts_dir):
        """列出所有账户"""
        registry = clean_accounts_dir
        registry.save(Account(alias="a", email="a@test.com", password="x"))
        registry.save(Account(alias="b", email="b@test.com", password="y"))

        accounts = registry.list_all()
        aliases = {a.alias for a in accounts}
        assert aliases == {"a", "b"}

    def test_delete(self, clean_accounts_dir):
        """删除账户"""
        registry = clean_accounts_dir
        registry.save(Account(alias="to_delete", email="x@test.com", password="x"))
        assert registry.delete("to_delete") is True
        assert registry.get("to_delete") is None
        assert registry.delete("to_delete") is False

    def test_resolve_active_from_file(self, clean_accounts_dir):
        """resolve_active 优先读 accounts/<alias>.json"""
        registry = clean_accounts_dir
        registry.save(Account(alias="work", email="work@test.com", password="secret"))
        registry.save(Account(alias="personal", email="personal@test.com", password="secret2"))

        # 没有 .env 时，传入 preferred 必须命中
        result = registry.resolve_active(preferred="work")
        assert result.alias == "work"

    def test_resolve_active_single_account(self, clean_accounts_dir):
        """只有一个账户时，缺省选它"""
        registry = clean_accounts_dir
        registry.save(Account(alias="only", email="only@test.com", password="secret"))

        result = registry.resolve_active()
        assert result.alias == "only"

    def test_resolve_active_no_account(self, clean_accounts_dir):
        """没有账户时报错"""
        registry = clean_accounts_dir
        with pytest.raises(ValueError):
            registry.resolve_active()

    def test_mask_email(self):
        """邮箱脱敏"""
        assert AccountRegistry.mask_email("hello@example.com") == "hel***@example.com"
        assert AccountRegistry.mask_email("ab@test.org") == "ab***@test.org"
