"""
Monitor module — status tracking, alerts, statistics
"""

import asyncio
from datetime import datetime
from typing import Optional

from loguru import logger

from src.storage.database import Database
from src.storage.models import ApplyResult, SessionRecord, SessionStatus
from src.utils.screenshot import capture_screenshot


class ApplicationTracker:
    """Application status tracker"""

    def __init__(self, db: Database):
        self.db = db

    def start_session(self, session_id: Optional[str] = None) -> str:
        """Start a new session (可接收外部传入的 session_id)"""
        if session_id is None:
            import uuid
            session_id = uuid.uuid4().hex[:12]

        session = SessionRecord(
            id=session_id,
            started_at=datetime.now(),
            status=SessionStatus.ACTIVE,
        )
        self.db.start_session(session)
        logger.info(f"Session started: {session_id}")
        return session_id

    def record_application(self, session_id: str, job, result: ApplyResult) -> None:
        """Record the application result"""
        self.db.record_application(result, session_id)

        status_emoji = {
            "submitted": "✅",
            "failed": "❌",
            "skipped": "⏭️",
            "captcha": "🤖",
        }.get(result.status.value, "❓")

        logger.info(
            f"{status_emoji} {job.title} @ {job.company} — {result.status.value}"
            f"{f' ({result.error_message})' if result.error_message else ''}"
        )

    def end_session(self, session_id: str, status: SessionStatus = SessionStatus.COMPLETED,
                    notes: Optional[str] = None) -> None:
        """End the session"""
        self.db.end_session(session_id, status, notes)
        logger.info(f"Session ended: {session_id} ({status.value})")


class AlertManager:
    """Alert manager"""

    def __init__(self, alert_on_captcha: bool = True):
        self.alert_on_captcha = alert_on_captcha

    async def captcha_alert(self, page, page_url: str) -> None:
        """CAPTCHA detected alert"""
        logger.critical("🚨 CAPTCHA DETECTED — Manual intervention required!")

        # Take screenshot
        screenshot = await capture_screenshot(page, "captcha_detected")

        if self.alert_on_captcha:
            # Terminal alert
            print("\n" + "=" * 60)
            print("⚠️  CAPTCHA 验证码检测到！")
            print(f"页面: {page_url}")
            print(f"截图: {screenshot}")
            print("请在浏览器中手动解决验证码")
            print("=" * 60 + "\n")

            # Pause and wait for user input
            try:
                input("解决验证码后按 Enter 继续...")
            except EOFError:
                # Non-interactive environment
                await asyncio.sleep(60)  # Wait 1 minute

    def detection_suspected_alert(self, reason: str) -> None:
        """Suspicious detection alert"""
        logger.warning(f"🤔 Detection suspected: {reason}")
        print(f"\n⚠️ Warning: Detection suspected — {reason}")
        print("Slowing down and limiting session...\n")


class StatsAggregator:
    """Statistics aggregator"""

    def __init__(self, db: Database):
        self.db = db

    def get_session_summary(self, session_id: str) -> dict:
        """Get session summary"""
        apps = self.db.get_applications_by_session(session_id)

        total = len(apps)
        success = sum(1 for a in apps if a["status"] == "submitted")
        failed = sum(1 for a in apps if a["status"] == "failed")
        skipped = sum(1 for a in apps if a["status"] == "skipped")
        captcha = sum(1 for a in apps if a["status"] == "captcha")

        success_rate = (success / (total - skipped) * 100) if (total - skipped) > 0 else 0

        return {
            "session_id": session_id,
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "captcha": captcha,
            "success_rate": round(success_rate, 1),
        }

    def get_recent_stats(self, days: int = 7) -> dict:
        """Get recent statistics"""
        return self.db.get_stats(days)
