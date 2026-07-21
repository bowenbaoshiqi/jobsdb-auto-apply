"""
特征化测试: storage/database.py

锁定 v1.0 的数据库行为:存取、去重、状态流转、账户隔离、统计。
用 temp_database fixture(真 SQLite + tmp_path),不起浏览器。
重构 database.py 后这些测试仍绿 = 行为未变。
"""

from datetime import datetime, timedelta

import pytest

from src.storage.models import (
    ApplyResult,
    ApplyStatus,
    JobListing,
    SessionRecord,
    SessionStatus,
)


# ═══════════════════════════════════════════════════════
#  Job 操作
# ═══════════════════════════════════════════════════════

class TestJobOperations:
    def test_save_and_get_job(self, temp_database, sample_jobs):
        """存职位 → 能取回,字段完整"""
        job = sample_jobs[0]
        temp_database.save_job(job)

        retrieved = temp_database.get_job(job.id)
        assert retrieved is not None
        assert retrieved.id == job.id
        assert retrieved.title == job.title
        assert retrieved.company == job.company
        assert retrieved.url == job.url

    def test_get_nonexistent_job_returns_none(self, temp_database):
        """取不存在的职位返回 None"""
        assert temp_database.get_job("nonexistent-id") is None

    def test_job_exists_after_save(self, temp_database, sample_jobs):
        """存后 exists=True,未存=False"""
        job = sample_jobs[0]
        assert temp_database.job_exists(job.id) is False
        temp_database.save_job(job)
        assert temp_database.job_exists(job.id) is True

    def test_save_job_replaces_existing(self, temp_database):
        """INSERT OR REPLACE: 同 ID 再存会更新"""
        job = JobListing(id="j1", title="Engineer", company="A", url="http://x")
        temp_database.save_job(job)

        updated = JobListing(id="j1", title="Senior Engineer", company="B", url="http://y")
        temp_database.save_job(updated)

        retrieved = temp_database.get_job("j1")
        assert retrieved.title == "Senior Engineer"
        assert retrieved.company == "B"


# ═══════════════════════════════════════════════════════
#  Application 操作 + 去重
# ═══════════════════════════════════════════════════════

class TestApplicationOperations:
    def test_record_and_retrieve_application(self, temp_database, sample_jobs):
        """记录投递 → 能按 session 取回"""
        job = sample_jobs[0]
        temp_database.save_job(job)

        app = ApplyResult(
            status=ApplyStatus.SUBMITTED,
            job_id=job.id,
            duration_seconds=1.5,
        )
        temp_database.record_application(app, session_id="sess-1")

        apps = temp_database.get_applications_by_session("sess-1")
        assert len(apps) == 1
        assert apps[0]["job_id"] == job.id
        assert apps[0]["status"] == "submitted"
        assert apps[0]["duration_seconds"] == 1.5

    def test_get_applied_job_ids_returns_submitted_and_processing(self, temp_database, sample_jobs):
        """get_applied_job_ids 只返回 SUBMITTED + PROCESSING(不含 FAILED/SKIPPED)"""
        job = sample_jobs[0]
        temp_database.save_job(job)

        # SUBMITTED → 应出现
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id),
            session_id="s1",
        )
        # FAILED → 不应出现
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.FAILED, job_id=job.id, error_message="err"),
            session_id="s2",
        )

        applied = temp_database.get_applied_job_ids()
        assert job.id in applied

    def test_failed_application_not_in_applied_ids(self, temp_database, sample_jobs):
        """纯 FAILED 投递不计入已投递(可重试)"""
        job = sample_jobs[1]
        temp_database.save_job(job)
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.FAILED, job_id=job.id),
            session_id="s1",
        )
        assert job.id not in temp_database.get_applied_job_ids()


# ═══════════════════════════════════════════════════════
#  账户隔离
# ═══════════════════════════════════════════════════════

class TestAccountIsolation:
    def test_applied_ids_isolated_by_account(self, temp_database, sample_jobs):
        """账户 A 投递的职位,账户 B 的 get_applied_job_ids 不含"""
        job = sample_jobs[0]
        temp_database.save_job(job)

        # 账户 A 投递
        temp_database.set_account("account_a")
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id),
            session_id="sess-a",
        )

        # 账户 B 查询
        temp_database.set_account("account_b")
        assert job.id not in temp_database.get_applied_job_ids()

        # 切回 A,应有
        temp_database.set_account("account_a")
        assert job.id in temp_database.get_applied_job_ids()

    def test_default_account_when_not_set(self, temp_database, sample_jobs):
        """未 set_account 时用 'default'"""
        job = sample_jobs[0]
        temp_database.save_job(job)
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id),
            session_id="s1",
        )
        # account_alias 为 None,但查询用 'default'
        assert temp_database.account_alias is None
        assert job.id in temp_database.get_applied_job_ids()


# ═══════════════════════════════════════════════════════
#  Session 操作
# ═══════════════════════════════════════════════════════

class TestSessionOperations:
    def test_start_and_end_session(self, temp_database):
        """开始会话 → 结束时状态更新"""
        session = SessionRecord(id="sess-1", started_at=datetime.now())
        temp_database.start_session(session)

        temp_database.end_session("sess-1", SessionStatus.COMPLETED, notes="done")

        recent = temp_database.get_recent_sessions(limit=5)
        assert len(recent) == 1
        assert recent[0]["id"] == "sess-1"
        assert recent[0]["status"] == "completed"
        assert recent[0]["notes"] == "done"

    def test_end_session_counts_applications(self, temp_database, sample_jobs):
        """end_session 统计该 session 的成功/失败数"""
        job = sample_jobs[0]
        temp_database.save_job(job)
        temp_database.set_account("default")

        session = SessionRecord(id="sess-count", started_at=datetime.now())
        temp_database.start_session(session)

        # 2 成功 + 1 失败
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id), session_id="sess-count")
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id), session_id="sess-count")
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.FAILED, job_id=job.id), session_id="sess-count")

        temp_database.end_session("sess-count", SessionStatus.COMPLETED)

        recent = temp_database.get_recent_sessions(limit=5)
        s = [r for r in recent if r["id"] == "sess-count"][0]
        assert s["jobs_attempted"] == 3
        assert s["jobs_succeeded"] == 2
        assert s["jobs_failed"] == 1


# ═══════════════════════════════════════════════════════
#  频率统计
# ═══════════════════════════════════════════════════════

class TestFrequencyCounting:
    def test_count_today_only_counts_submitted(self, temp_database, sample_jobs):
        """今天的投递数只计 SUBMITTED"""
        job = sample_jobs[0]
        temp_database.save_job(job)
        temp_database.set_account("default")

        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id), session_id="s1")
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.FAILED, job_id=job.id), session_id="s2")

        assert temp_database.get_application_count_today() == 1

    def test_count_last_hour(self, temp_database, sample_jobs):
        """最近1小时计数"""
        job = sample_jobs[0]
        temp_database.save_job(job)
        temp_database.set_account("default")

        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id), session_id="s1")

        assert temp_database.get_application_count_last_hour() == 1


# ═══════════════════════════════════════════════════════
#  Captcha 事件
# ═══════════════════════════════════════════════════════

class TestCaptchaEvents:
    def test_log_captcha_event_does_not_raise(self, temp_database):
        """记录验证码事件不报错"""
        temp_database.set_account("default")
        temp_database.log_captcha_event(
            page_url="https://hk.jobsdb.com/job/123",
            resolution="manual_solved",
        )
        # 不报错即通过(无返回值)


# ═══════════════════════════════════════════════════════
#  统计
# ═══════════════════════════════════════════════════════

class TestStats:
    def test_stats_empty_database(self, temp_database):
        """空库统计:全零,success_rate=0"""
        stats = temp_database.get_stats(days=7)
        assert stats["total"] == 0
        assert stats["success"] == 0
        assert stats["failed"] == 0
        assert stats["success_rate"] == 0
        assert stats["daily_breakdown"] == []

    def test_stats_with_applications(self, temp_database, sample_jobs):
        """有投递记录的统计"""
        job = sample_jobs[0]
        temp_database.save_job(job)
        temp_database.set_account("default")

        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id), session_id="s1")
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.FAILED, job_id=job.id), session_id="s2")

        stats = temp_database.get_stats(days=7)
        assert stats["total"] == 2
        assert stats["success"] == 1
        assert stats["failed"] == 1
        assert stats["success_rate"] == 50.0
