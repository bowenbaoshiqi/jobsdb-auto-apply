import json
from pathlib import Path

from loguru import logger


class CookieStore:
    """Playwright Cookie 持久化管理"""

    def __init__(self, cookies_file: str = "./data/cookies.json"):
        self.cookies_file = Path(cookies_file)
        self.cookies_file.parent.mkdir(parents=True, exist_ok=True)

    def save(self, cookies: list[dict]) -> None:
        """保存 cookies 到文件"""
        try:
            with open(self.cookies_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            logger.debug(f"Saved {len(cookies)} cookies to {self.cookies_file}")
        except Exception as e:
            logger.warning(f"Failed to save cookies: {e}")

    def load(self) -> list[dict]:
        """从文件加载 cookies"""
        if not self.cookies_file.exists():
            logger.debug("No cookies file found, starting fresh")
            return []
        try:
            with open(self.cookies_file, encoding="utf-8") as f:
                cookies = json.load(f)
            logger.debug(f"Loaded {len(cookies)} cookies from {self.cookies_file}")
            return cookies
        except Exception as e:
            logger.warning(f"Failed to load cookies: {e}")
            return []

    def clear(self) -> None:
        """清除 cookies"""
        if self.cookies_file.exists():
            self.cookies_file.unlink()
            logger.debug("Cookies cleared")

    def is_fresh(self, max_age_hours: int = 12) -> bool:
        """检查 cookies 是否仍在有效期内"""
        if not self.cookies_file.exists():
            return False

        try:
            stat = self.cookies_file.stat()
            import time
            age_hours = (time.time() - stat.st_mtime) / 3600
            return age_hours < max_age_hours
        except Exception:
            return False
