"""
特征化测试: accounts/registry.py

锁定多账户管理行为:save/get/list_all/delete/set_active/resolve_active/mask_email。
用 tmp_path 隔离 accounts 目录,不碰真实凭证。
"""

import json
from unittest.mock import patch

import pytest

from src.accounts.registry import Account, AccountRegistry


@pytest.fixture
def registry(tmp_path):
    """用 tmp_path 隔离的 registry,不碰真实 accounts/"""
    acc_dir = tmp_path / "accounts"
    active_file = tmp_path / "data" / ".active_account"
    reg = AccountRegistry(accounts_dir=acc_dir)
    reg._active_file = active_file  # 重定向到 tmp
    return reg


# ═══════════════════════════════════════════════════════
#  Account 数据对象
# ═══════════════════════════════════════════════════════

class TestAccount:
    def test_to_dict_roundtrip(self):
        """to_dict → from_dict 往返一致"""
        acc = Account(alias="work", email="a@b.com", password="secret", notes="n")
        d = acc.to_dict()
        assert d == {
            "alias": "work", "email": "a@b.com", "password": "secret", "notes": "n"
        }
        restored = Account.from_dict(d)
        assert restored.alias == "work"
        assert restored.email == "a@b.com"
        assert restored.password == "secret"
        assert restored.notes == "n"

    def test_notes_defaults_to_empty(self):
        """notes 未传时默认空串"""
        acc = Account(alias="x", email="x@y.com", password="p")
        assert acc.notes == ""

    def test_repr_shows_alias_and_email_not_password(self):
        """repr 不暴露密码"""
        acc = Account(alias="x", email="x@y.com", password="secret123")
        r = repr(acc)
        assert "x@y.com" in r
        assert "secret123" not in r


# ═══════════════════════════════════════════════════════
#  save / get
# ═══════════════════════════════════════════════════════

class TestSaveGet:
    def test_save_creates_json_file(self, registry):
        acc = Account(alias="work", email="a@b.com", password="p")
        registry.save(acc)
        path = registry.accounts_dir / "work.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["alias"] == "work"
        assert data["email"] == "a@b.com"

    def test_get_returns_account(self, registry):
        acc = Account(alias="work", email="a@b.com", password="p")
        registry.save(acc)
        retrieved = registry.get("work")
        assert retrieved is not None
        assert retrieved.alias == "work"
        assert retrieved.email == "a@b.com"

    def test_get_nonexistent_returns_none(self, registry):
        assert registry.get("nonexistent") is None

    def test_save_overwrites_existing(self, registry):
        """同 alias 再 save 会覆盖"""
        registry.save(Account(alias="x", email="old@b.com", password="p"))
        registry.save(Account(alias="x", email="new@b.com", password="p2"))
        acc = registry.get("x")
        assert acc.email == "new@b.com"
        assert acc.password == "p2"


# ═══════════════════════════════════════════════════════
#  list_all
# ═══════════════════════════════════════════════════════

class TestListAll:
    def test_lists_all_saved_accounts(self, registry):
        registry.save(Account(alias="a", email="a@x.com", password="p"))
        registry.save(Account(alias="b", email="b@x.com", password="p"))
        accounts = registry.list_all()
        aliases = [a.alias for a in accounts]
        assert set(aliases) == {"a", "b"}

    def test_list_all_skips_example_json(self, registry):
        """example.json 被跳过(模板文件)"""
        (registry.accounts_dir / "example.json").write_text(
            json.dumps({"alias": "example", "email": "e@x.com", "password": "p"})
        )
        registry.save(Account(alias="real", email="r@x.com", password="p"))
        aliases = [a.alias for a in registry.list_all()]
        assert "example" not in aliases
        assert "real" in aliases

    def test_list_all_empty_when_no_accounts(self, registry):
        assert registry.list_all() == []

    def test_list_all_skips_corrupt_file(self, registry):
        """损坏的 JSON 文件被跳过,不抛异常"""
        (registry.accounts_dir / "bad.json").write_text("not valid json{{{")
        registry.save(Account(alias="good", email="g@x.com", password="p"))
        accounts = registry.list_all()
        aliases = [a.alias for a in accounts]
        assert "good" in aliases
        assert "bad" not in aliases


# ═══════════════════════════════════════════════════════
#  delete
# ═══════════════════════════════════════════════════════

class TestDelete:
    def test_delete_existing_returns_true(self, registry):
        registry.save(Account(alias="x", email="x@y.com", password="p"))
        assert registry.delete("x") is True
        assert not (registry.accounts_dir / "x.json").exists()

    def test_delete_nonexistent_returns_false(self, registry):
        assert registry.delete("nonexistent") is False


# ═══════════════════════════════════════════════════════
#  set_active / get_active_alias
# ═══════════════════════════════════════════════════════

class TestSetActive:
    def test_set_active_writes_file(self, registry):
        registry.save(Account(alias="work", email="w@x.com", password="p"))
        registry.set_active("work")
        assert registry.get_active_alias() == "work"

    def test_set_active_nonexistent_raises(self, registry):
        with pytest.raises(ValueError, match="不存在"):
            registry.set_active("nonexistent")

    def test_get_active_alias_none_when_not_set(self, registry):
        assert registry.get_active_alias() is None


# ═══════════════════════════════════════════════════════
#  resolve_active 优先级
# ═══════════════════════════════════════════════════════

class TestResolveActive:
    def test_preferred_alias_takes_priority(self, registry):
        """CLI --account 优先级最高"""
        registry.save(Account(alias="a", email="a@x.com", password="p"))
        registry.save(Account(alias="b", email="b@x.com", password="p"))
        acc = registry.resolve_active(preferred="b")
        assert acc.alias == "b"

    def test_preferred_nonexistent_raises(self, registry):
        with pytest.raises(ValueError, match="未找到账户"):
            registry.resolve_active(preferred="nonexistent")

    def test_single_account_auto_selected(self, registry):
        """accounts/ 下唯一账户自动选用(无 preferred + 无 .env)"""
        registry.save(Account(alias="only", email="o@x.com", password="p"))
        # mock get_config 返回无 .env 凭证
        with patch("src.accounts.registry.get_config") as mock_cfg:
            mock_cfg.return_value.jobsdb.email = None
            mock_cfg.return_value.jobsdb.password = None
            acc = registry.resolve_active()
        assert acc.alias == "only"

    def test_no_accounts_raises(self, registry):
        """无任何可用账户时报错"""
        with patch("src.accounts.registry.get_config") as mock_cfg:
            mock_cfg.return_value.jobsdb.email = None
            mock_cfg.return_value.jobsdb.password = None
            with pytest.raises(ValueError, match="没有可用账户"):
                registry.resolve_active()


# ═══════════════════════════════════════════════════════
#  mask_email 脱敏
# ═══════════════════════════════════════════════════════

class TestMaskEmail:
    def test_long_local_part_masked(self):
        """长本地名:显示前3位 + ***"""
        masked = AccountRegistry.mask_email("bowenbao@example.com")
        assert masked.startswith("bow")
        assert "***" in masked
        assert "example.com" in masked
        assert "bowenbao" not in masked  # 完整本地名不出现

    def test_short_local_part(self):
        """短本地名(≤3)"""
        masked = AccountRegistry.mask_email("ab@example.com")
        assert "example.com" in masked
