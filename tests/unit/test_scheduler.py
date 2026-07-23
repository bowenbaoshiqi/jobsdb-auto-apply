"""
TC-10, TC-16: Rate Limiter + Scheduler 测试
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import SchedulerConfig
from src.scheduler.queue import ApplyQueue, RateLimiter
from src.storage.models import ApplyResult, ApplyStatus, SessionRecord, SessionStatus


class TestRateLimiter:
    """频率限制 — TC-10 测试"""

    @pytest.mark.asyncio
    async def test_tc10_hourly_cap_blocks(self, temp_database):
        """
        TC-10: 当日已达到 max_per_day 时应该触发等待

        策略：mock 数据库中已有 max_per_day 条记录，验证 wait_if_needed 会阻塞。
        """
        config = SchedulerConfig(
            max_per_hour=10,
            max_per_day=3,  # 设置很低的限制以便测试
            min_delay_between_seconds=1,  # 缩短基础间隔
        )
        db = temp_database
        limiter = RateLimiter(config, db)

        # 预先创建 session 和 application 记录
        session = SessionRecord(
            id="rate-test",
            started_at=datetime.now(),
            status=SessionStatus.COMPLETED,
        )
        db.start_session(session)

        # 添加 3 次已成功投递（达到 daily cap）
        for i in range(3):
            result = ApplyResult(
                status=ApplyStatus.SUBMITTED,
                job_id=f"job_{i}",
                applied_at=datetime.now(),
            )
            db.record_application(result, "rate-test")

        # 验证已达到上限
        assert db.get_application_count_today() == 3

        # 调用 wait_if_needed 应该阻塞，我们用 asyncio.wait_for 来检测超时
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(limiter.wait_if_needed(), timeout=0.5)

    @pytest.mark.asyncio
    async def test_tc10_min_delay_between(self, temp_database, sample_jobs):
        """
        TC-10 补充：非首次申请(本小时已有 1 条提交)走最小间隔 + 抖动
        """
        config = SchedulerConfig(
            min_delay_between_seconds=0.1,  # 100ms，加速测试
        )
        limiter = RateLimiter(config, temp_database)
        temp_database.set_account("default")

        # 预置 1 条已提交 → hour_count=1(非首次),才会走 min_delay 分支
        job = sample_jobs[0]
        temp_database.save_job(job)
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id), session_id="s1")

        start = asyncio.get_event_loop().time()
        await limiter.wait_if_needed()
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed >= 0.08, f"Waited only {elapsed:.3f}s, should be >= 0.1s"

    def test_rate_limiter_daily_calculation(self):
        """
        TC-10 补充：验证 _calculate_wait_for_next_hour 的返回值合理
        """
        from src.scheduler.queue import RateLimiter
        limiter = RateLimiter()

        wait_seconds = limiter._calculate_wait_for_next_hour()
        # 应该在 0 到 3600 之间
        assert 0 <= wait_seconds <= 3600, f"Invalid wait time: {wait_seconds}"


class TestQueuePrioritization:
    """队列优先级 — TC-16 补充"""

    def test_queue_filters_applied_jobs(self, temp_database):
        """
        TC-09 已经在 test_database.py 中覆盖，
        这里测试 _prioritize 逻辑。
        """
        from src.storage.models import JobListing

        jobs = [
            JobListing(id="1", title="A", company="A", salary=None),           # 没有薪资
            JobListing(id="2", title="B", company="B", salary="50K"),        # 有薪资
            JobListing(id="3", title="C", company="C", salary=None, location="HK"),  # 有地点
        ]

        queue = ApplyQueue(temp_database)
        prioritized = queue._prioritize(jobs)

        # 有薪资的 job 2 应该排第一
        assert prioritized[0].id == "2", \
            f"Job with salary should be first, got: {prioritized[0].id}"

    def test_queue_max_applies_limit(self, temp_database):
        """
        TC-16 补充：max_applies_per_session 限制
        """
        from src.storage.models import JobListing

        config = SchedulerConfig(max_applies_per_session=2)
        queue = ApplyQueue(temp_database, config)

        jobs = [
            JobListing(id="1", title="A", company="A"),
            JobListing(id="2", title="B", company="B"),
            JobListing(id="3", title="C", company="C"),
            JobListing(id="4", title="D", company="D"),
        ]

        result = queue.build_queue(jobs)
        assert len(result) == 2, f"Should limit to 2, got {len(result)}"
