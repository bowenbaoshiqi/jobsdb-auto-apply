"""
账户注册表

支持多账户隔离：
1. 每个账户独立凭证（accounts/<alias>.json）
2. .env 单账户向后兼容（alias="default"）
3. 读取时优先用 --account 参数，其次用 .env，其次用 .active_account 文件
"""

import json
from pathlib import Path
from typing import Optional

from loguru import logger

from config.settings import get_config


class Account:
    """账户凭证（内存对象，可序列化到 JSON）"""

    def __init__(
        self,
        alias: str,
        email: str,
        password: str,
        notes: Optional[str] = None,
    ):
        self.alias = alias
        self.email = email
        self.password = password
        self.notes = notes or ""

    def to_dict(self) -> dict:
        return {
            "alias": self.alias,
            "email": self.email,
            "password": self.password,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Account":
        return cls(
            alias=data["alias"],
            email=data["email"],
            password=data["password"],
            notes=data.get("notes"),
        )

    def __repr__(self) -> str:
        return f"Account(alias={self.alias}, email={self.email})"


class AccountRegistry:
    """账户注册表 — 管理 accounts/ 目录下的 JSON 凭证文件"""

    def __init__(self, accounts_dir: Optional[Path] = None):
        self.accounts_dir = accounts_dir or Path("accounts")
        self.accounts_dir.mkdir(parents=True, exist_ok=True)
        self._active_file = Path("data") / ".active_account"

    # ---- 读取 / 解析 ----

    def list_all(self) -> list[Account]:
        """列出 accounts/ 下所有已注册账户"""
        accounts = []
        for json_file in sorted(self.accounts_dir.glob("*.json")):
            if json_file.name == "example.json":
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                accounts.append(Account.from_dict(data))
            except Exception as e:
                logger.warning(f"跳过损坏的账户文件 {json_file}: {e}")
        return accounts

    def get(self, alias: str) -> Optional[Account]:
        """读取指定别名的账户"""
        path = self.accounts_dir / f"{alias}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Account.from_dict(data)
        except Exception as e:
            logger.error(f"无法读取账户 {alias}: {e}")
            return None

    def resolve_active(
        self,
        preferred: Optional[str] = None,
        allow_placeholder: bool = False,
    ) -> Account:
        """
        解析当前应使用的账户。

        优先级：
        1. CLI 传了 --account -> 读 accounts/<preferred>.json
        2. .env 中有 JOBSDB_EMAIL / JOBSDB_PASSWORD -> 构造 default 账户（向后兼容）
        3. data/.active_account 有记录 -> 读该别名
        4. 读 accounts/ 下唯一的账户文件
        5. allow_placeholder=True -> 返回空凭证占位账户(manual 模式,无需凭证)
        6. 报错

        allow_placeholder 供 manual 登录模式用:持久化 profile 即凭证,不要求 email/password。
        """
        if preferred:
            acc = self.get(preferred)
            if acc:
                logger.info(f"使用指定账户: {acc.alias}")
                return acc
            raise ValueError(
                f"未找到账户 '{preferred}'。请先用 `python -m src.main account add {preferred}` 添加"  # noqa: E501
            )

        # 向后兼容：.env 单账户
        config = get_config()
        if config.jobsdb.email and config.jobsdb.password:
            logger.debug("从 .env 构建 default 账户（向后兼容）")
            return Account(
                alias="default",
                email=config.jobsdb.email,
                password=config.jobsdb.password,
                notes="从 .env 自动迁移",
            )

        # 读 .active_account 文件
        if self._active_file.exists():
            alias = self._active_file.read_text(encoding="utf-8").strip()
            if alias:
                acc = self.get(alias)
                if acc:
                    logger.info(f"使用活跃账户: {acc.alias}")
                    return acc

        # 如果 accounts/ 下只有一个账户，直接用
        all_accounts = self.list_all()
        if len(all_accounts) == 1:
            return all_accounts[0]

        # manual 模式兜底:无需凭证,返回占位账户(持久化 profile 即凭证)
        if allow_placeholder:
            logger.info("无账户配置,返回占位账户(manual 模式,无需凭证)")
            return Account(alias="default", email="", password="",
                           notes="manual 模式占位账户,不持有凭证")

        raise ValueError(
            "没有可用账户。请先添加账户：\n"
            "  python -m src.main account add <alias> --email xxx\n"
            "或在 .env 中设置 JOBSDB_EMAIL + JOBSDB_PASSWORD"
        )

    # ---- 写册 / 删除 ----

    def save(self, account: Account) -> None:
        """保存账户到 accounts/<alias>.json"""
        path = self.accounts_dir / f"{account.alias}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(account.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"账户已保存: {account.alias}")

    def delete(self, alias: str) -> bool:
        """删除 accounts/<alias>.json"""
        path = self.accounts_dir / f"{alias}.json"
        if path.exists():
            path.unlink()
            logger.info(f"已删除账户: {alias}")
            return True
        logger.warning(f"账户不存在，无法删除: {alias}")
        return False

    def set_active(self, alias: str) -> None:
        """将 alias 写入 data/.active_account"""
        # 先校验存在性
        if not self.get(alias):
            raise ValueError(f"账户 {alias} 不存在")
        self._active_file.parent.mkdir(parents=True, exist_ok=True)
        self._active_file.write_text(alias, encoding="utf-8")
        logger.info(f"活跃账户已切换为: {alias}")

    def get_active_alias(self) -> Optional[str]:
        """返回当前活跃账户别名"""
        if self._active_file.exists():
            return self._active_file.read_text(encoding="utf-8").strip()
        return None

    # ---- 辅助 ----

    @staticmethod
    def mask_email(email: str) -> str:
        """邮箱脱敏：显示前 3 位（或全部如果太短）"""
        local, domain = email.split("@", 1)
        shown = local[:3] if len(local) > 3 else local
        if len(local) > 3:
            return f"{shown}***@{domain}"
        return f"{shown}***@{domain}" if len(local) > 1 else email
