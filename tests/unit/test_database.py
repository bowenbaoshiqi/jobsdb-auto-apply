"""
TC-08, TC-09: 数据库操作测试
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.models import (
    ApplyResult,
    ApplyStatus,
    JobListing,
    SessionRecord,
    SessionStatus,
)


class TestDatabaseIdempotent:
    """数据库 — P0 核心测试"""

    def test_tc08_save_job_idempotent(self, temp_database):
        """
        TC-08: 相同 job_id 重复保存应不报错且幂等
        """
        db = temp_database

        job1 = JobListing(
            id="12345",
            title="Original Title",
            company="Original Company",
            url="https://example.com/1",
        )

        job2 = JobListing(
            id="12345",
            title="Updated Title",
            company="Updated Company",
            url="https://example.com/1",
        )

        # 第一次保存
        db.save_job(job1)
        saved = db.get_job("12345")
        assert saved is not None
        assert saved.title == "Original Title"

        # 第二次保存（覆盖）
        db.save_job(job2)
        saved = db.get_job("12345")
        assert saved.title == "Updated Title"
        assert saved.company == "Updated Company"

    def test_tc08_job_exists(self, temp_database):
        """
        TC-08 补充：job_exists 方法
        """
        db = temp_database
        job = JobListing(id="99999", title="Test", company="Test", url="https://example.com")

        assert db.job_exists("99999") is False
        db.save_job(job)
        assert db.job_exists("99999") is True

    def test_tc09_queue_filters_applied_jobs(self, temp_database, sample_jobs):
        """
        TC-09: 已投递职位应被过滤
        """
        from src.scheduler.queue import ApplyQueue

        db = temp_database

        # 保存所有职位
        for job in sample_jobs:
            db.save_job(job)

        # 模拟第一个已投递
        result = ApplyResult(
            status=ApplyStatus.SUBMITTED,
            job_id="12345",
        )
        session = SessionRecord(
            id="test-session",
            started_at=__import__('datetime').datetime.now(),
            status=SessionStatus.COMPLETED,
        )
        db.start_session(session)
        db.record_application(result, "test-session")

        # 构建队列
        queue = ApplyQueue(db)
        filtered = queue.build_queue(sample_jobs)

        # 已投递的 12345 应被过滤
        assert len(filtered) == 2, f"Expected 2 jobs after filtering, got {len(filtered)}"
        assert all(job.id != "12345" for job in filtered), \
            "Applied job should be filtered out"

    def test_tc09_queue_prioritizes_with_salary(self, temp_database, sample_jobs):
        """
        TC-09 补充：优先投递有薪资的职位
        """
        from src.scheduler.queue import ApplyQueue

        db = temp_database
        queue = ApplyQueue(db)
        prioritized = queue._prioritize(sample_jobs)

        # 有薪资的职位应该在前面
        assert prioritized[0].salary is not None, \
            f"Jobs with salary should be prioritized, got: {prioritized[0].salary}"

    def test_tc09_get_applied_job_ids(self, temp_database):
        """
        TC-09 补充：get_applied_job_ids 方法
        """
        db = temp_database

        # 初始为空
        assert db.get_applied_job_ids() == []

        # 添加已投递记录
        result = ApplyResult(status=ApplyStatus.SUBMITTED, job_id="111")
        session = SessionRecord(
            id="s1",
            started_at=__import__('datetime').datetime.now(),
            status=SessionStatus.COMPLETED,
        )
        db.start_session(session)
        db.record_application(result, "s1")

        ids = db.get_applied_job_ids()
        assert "111" in ids
        assert len(ids) == 1

    def test_database_stats(self, temp_database):
        """
        补充：统计数据正确性
        """
        db = temp_database

        # 添加一些投递记录
        session = SessionRecord(
            id="stats-test",
            started_at=__import__('datetime').datetime.now(),
            status=SessionStatus.COMPLETED,
        )
        db.start_session(session)

        for i in range(5):
            status = ApplyStatus.SUBMITTED if i < 3 else ApplyStatus.FAILED
            result = ApplyResult(status=status, job_id=f"job_{i}")
            db.record_application(result, "stats-test")

        stats = db.get_stats(days=1)
        assert stats["total"] == 5
        assert stats["success"] == 3
        assert stats["failed"] == 2
        assert stats["success_rate"] == 60.0


class TestDatabaseMigration:
    """数据库迁移测试 — account_id 列"""

    def test_account_id_column_exists(self, tmp_path):
        """新数据库应包含 account_id 列"""
        from src.storage.database import Database

        db_path = tmp_path / "migrated.db"
        db = Database(str(db_path))
        db.set_account("test_user")

        # 验证表中存在 account_id 列
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(applications)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "account_id" in columns, f"Missing account_id in applications: {columns}"

        cursor = conn.execute("PRAGMA table_info(sessions)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "account_id" in columns, f"Missing account_id in sessions: {columns}"
        conn.close()

    def test_account_id_filtering(self, tmp_path):
        """账户隔离：不同账户的数据互不干扰"""
        from src.storage.database import Database
        from src.storage.models import ApplyResult, ApplyStatus, SessionRecord, SessionStatus

        db_path = tmp_path / "isolated.db"
        db = Database(str(db_path))

        # 账户 A 投递
        db.set_account("account_a")
        session_a = SessionRecord(
            id="s-a", started_at=__import__('datetime').datetime.now(), status=SessionStatus.ACTIVE
        )
        db.start_session(session_a)
        db.record_application(ApplyResult(status=ApplyStatus.SUBMITTED, job_id="job1"), "s-a")

        # 账户 B 投递
        db.set_account("account_b")
        session_b = SessionRecord(
            id="s-b", started_at=__import__('datetime').datetime.now(), status=SessionStatus.ACTIVE
        )
        db.start_session(session_b)
        db.record_application(ApplyResult(status=ApplyStatus.SUBMITTED, job_id="job2"), "s-b")

        # 验证隔离
        db.set_account("account_a")
        assert db.get_application_count_today() == 1
        assert db.get_applied_job_ids() == ["job1"]

        db.set_account("account_b")
        assert db.get_application_count_today() == 1
        assert db.get_applied_job_ids() == ["job2"]

    def test_stats_per_account(self, tmp_path):
        """统计数据按账户过滤"""
        from src.storage.database import Database
        from src.storage.models import ApplyResult, ApplyStatus, SessionRecord, SessionStatus

        db_path = tmp_path / "stats.db"
        db = Database(str(db_path))

        db.set_account("alice")
        session = SessionRecord(
            id="s1", started_at=__import__('datetime').datetime.now(), status=SessionStatus.ACTIVE
        )
        db.start_session(session)
        db.record_application(ApplyResult(status=ApplyStatus.SUBMITTED, job_id="j1"), "s1")
        db.record_application(ApplyResult(status=ApplyStatus.FAILED, job_id="j2"), "s1")

        db.set_account("bob")
        db.record_application(ApplyResult(status=ApplyStatus.SUBMITTED, job_id="j3"), "s1")

        # Alice 的统计
        alice_stats = db.get_stats(days=1, account="alice")
        assert alice_stats["total"] == 2
        assert alice_stats["success"] == 1

        # Bob 的统计
        bob_stats = db.get_stats(days=1, account="bob")
        assert bob_stats["total"] == 1
        assert bob_stats["success"] == 1

        # 全部统计
        all_stats = db.get_stats(days=1)
        assert all_stats["total"] == 3
