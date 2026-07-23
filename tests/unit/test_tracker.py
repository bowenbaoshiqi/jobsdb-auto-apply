"""
单元测试: monitor/tracker (ApplicationTracker / AlertManager / StatsAggregator)

用内存 Database 测,不起浏览器。
"""

import pytest

from src.monitor.tracker import AlertManager, ApplicationTracker, StatsAggregator
from src.storage.database import Database
from src.storage.models import ApplyResult, ApplyStatus, JobListing, SessionStatus


@pytest.fixture
def db(tmp_path):
    # 注意:不能用 :memory: — sqlite 的 :memory: 每连接独立,会丢表
    d = Database(str(tmp_path / "test.db"))
    d.set_account("test")
    return d


@pytest.fixture
def tracker(db):
    return ApplicationTracker(db)


@pytest.fixture
def stats(db):
    return StatsAggregator(db)


def make_job(jid="job-1", title="Dev", company="Co"):
    return JobListing(id=jid, title=title, company=company, url="http://x")


def make_result(status=ApplyStatus.SUBMITTED, jid="job-1", error=None):
    return ApplyResult(status=status, job_id=jid, error_message=error)


# ═══════════════════════════════════════════════════════
#  ApplicationTracker
# ═══════════════════════════════════════════════════════

class TestApplicationTracker:
    def test_start_session_returns_id(self, tracker):
        sid = tracker.start_session()
        assert isinstance(sid, str) and len(sid) > 0

    def test_start_session_uses_provided_id(self, tracker):
        sid = tracker.start_session("my-session")
        assert sid == "my-session"

    def test_record_application_persists(self, tracker, db):
        tracker.start_session("s1")
        tracker.record_application("s1", make_job(), make_result(ApplyStatus.SUBMITTED))
        apps = db.get_applications_by_session("s1")
        assert len(apps) == 1
        assert apps[0]["status"] == "submitted"

    def test_end_session(self, tracker, db):
        tracker.start_session("s1")
        tracker.end_session("s1", SessionStatus.COMPLETED, "done")
        # 会话应已结束(状态更新)
        sessions = db.get_recent_sessions()
        assert any(s["id"] == "s1" for s in sessions)


# ═══════════════════════════════════════════════════════
#  AlertManager
# ═══════════════════════════════════════════════════════

class TestAlertManager:
    def test_detection_suspected_alert_no_error(self, capsys):
        """detection_suspected_alert 不抛异常"""
        alert = AlertManager()
        alert.detection_suspected_alert("3 failures")
        out = capsys.readouterr().out
        assert "Detection suspected" in out

    @pytest.mark.asyncio
    async def test_captcha_alert_non_interactive(self, monkeypatch, tmp_path):
        """captcha_alert 在非交互环境(EOFError)走 sleep 分支"""
        alert = AlertManager(alert_on_captcha=True)

        # input 抛 EOFError → 走 asyncio.sleep(60);mock sleep 避免真等
        async def fake_sleep(s):
            pass

        import asyncio
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(EOFError()))

        # 用 FakePageController 避免 capture_screenshot 落盘
        from src.browser.fake.fake_page import FakePageController
        page = FakePageController()
        await alert.captcha_alert(page, "http://captcha")  # 不抛


# ═══════════════════════════════════════════════════════
#  StatsAggregator
# ═══════════════════════════════════════════════════════

class TestStatsAggregator:
    def test_empty_session_summary(self, stats):
        s = stats.get_session_summary("nonexistent")
        assert s["total"] == 0
        assert s["success"] == 0
        assert s["success_rate"] == 0

    def test_summary_counts(self, tracker, stats):
        tracker.start_session("s1")
        tracker.record_application("s1", make_job("j1"), make_result(ApplyStatus.SUBMITTED, "j1"))
        tracker.record_application("s1", make_job("j2"), make_result(ApplyStatus.FAILED, "j2", "err"))  # noqa: E501
        tracker.record_application("s1", make_job("j3"), make_result(ApplyStatus.SKIPPED, "j3"))

        s = stats.get_session_summary("s1")
        assert s["total"] == 3
        assert s["success"] == 1
        assert s["failed"] == 1
        assert s["skipped"] == 1
        # success_rate = success / (total - skipped) = 1/2 = 50
        assert s["success_rate"] == 50.0

    def test_summary_all_skipped_rate_zero(self, tracker, stats):
        """全 skipped → success_rate 0(避免除零)"""
        tracker.start_session("s1")
        tracker.record_application("s1", make_job("j1"), make_result(ApplyStatus.SKIPPED, "j1"))
        s = stats.get_session_summary("s1")
        assert s["success_rate"] == 0
