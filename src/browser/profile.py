"""
浏览器 Profile 持久化管理

负责管理 Chromium 用户数据目录，确保：
1. 不同运行之间保持一致的浏览器指纹
2. 网站数据、localStorage、IndexedDB 持久化
3. 自动清理无用数据防止膨胀
"""

import shutil
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger


class ProfileManager:
    """浏览器 Profile 管理器"""

    def __init__(self, profile_dir: str = "./data/browser_profile"):
        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)

    def get_profile_path(self) -> str:
        """获取 profile 目录路径"""
        return str(self.profile_dir.absolute())

    def cleanup_old_data(self, max_age_days: int = 30) -> None:
        """
        清理过期的缓存数据

        Args:
            max_age_days: 超过多少天的数据需要清理
        """
        if not self.profile_dir.exists():
            return

        cutoff = datetime.now() - timedelta(days=max_age_days)
        cleaned = 0

        # 清理旧的缓存目录
        cache_dirs = [
            "Default/Cache",
            "Default/Code Cache",
            "Default/GPUCache",
            "Default/Service Worker",
        ]

        for cache_dir in cache_dirs:
            cache_path = self.profile_dir / cache_dir
            if cache_path.exists():
                try:
                    shutil.rmtree(cache_path)
                    cleaned += 1
                except Exception as e:
                    logger.warning(f"Failed to clean {cache_dir}: {e}")

        # 清理旧日志
        log_files = list(self.profile_dir.glob("**/*.log"))
        for log_file in log_files:
            try:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff:
                    log_file.unlink()
                    cleaned += 1
            except Exception as e:
                logger.debug(f"Failed to clean log {log_file}: {e}")

        logger.info(f"Profile cleanup completed, removed {cleaned} items")

    def reset_profile(self) -> None:
        """
        重置 profile（清除所有数据，相当于全新浏览器）
        只在遇到严重问题时使用。
        """
        if self.profile_dir.exists():
            try:
                shutil.rmtree(self.profile_dir)
                self.profile_dir.mkdir(parents=True, exist_ok=True)
                logger.warning("Browser profile has been reset")
            except Exception as e:
                logger.error(f"Failed to reset profile: {e}")

    def get_profile_size(self) -> str:
        """获取 profile 目录大小（人类可读）"""
        if not self.profile_dir.exists():
            return "0 B"

        total = 0
        for path in self.profile_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size

        # 转换为人类可读格式
        for unit in ["B", "KB", "MB", "GB"]:
            if total < 1024:
                return f"{total:.1f} {unit}"
            total /= 1024
        return f"{total:.1f} TB"

    def is_profile_valid(self) -> bool:
        """检查 profile 是否有效（基本结构是否存在）"""
        if not self.profile_dir.exists():
            return False

        # 检查必要的子目录
        required_paths = [
            self.profile_dir / "Default",
        ]
        return all(p.exists() for p in required_paths)
