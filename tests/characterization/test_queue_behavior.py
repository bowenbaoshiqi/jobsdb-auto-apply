"""
特征化测试: scheduler/queue.py

锁定 v1.0 的队列构建(过滤已投递 + 优先级排序 + 限量)和限流逻辑。
用 temp_database(真 SQLite)+ 自定义 SchedulerConfig(确定性),不起浏览器。
"""

from unittest.mock import AsyncMock, patch

import pytest

from config.settings import SchedulerConfig
from src.scheduler.queue import ApplyQueue, RateLimiter
from src.storage.models import ApplyResult, ApplyStatus, JobListing

# 确定性的测试 config
TEST_CONFIG = SchedulerConfig(
    max_applies_per_session=5,
    max_per_hour=10,
    max_per_day=30,
    min_delay_between_seconds=180.0,
    peak_hours_exclude=[{"start": 9, "end": 11}, {"start": 14, "end": 16}],
)


def make_job(id, salary=None, location=None, posted_date=None):
    return JobListing(
        id=id, title=f"Job {id}", company="Co", url=f"http://x/{id}",
        salary=salary, location=location, posted_date=posted_date,
    )


# ═══════════════════════════════════════════════════════
#  build_queue: 过滤已投递
# ═══════════════════════════════════════════════════════

class TestBuildQueueFiltering:
    def test_filters_out_applied_jobs(self, temp_database):
        """已投递(SUBMITTED)的职位被过滤"""
        temp_database.set_account("default")
        queue = ApplyQueue(temp_database, TEST_CONFIG)

        j1, j2, j3 = make_job("1"), make_job("2"), make_job("3")
        temp_database.save_job(j1)
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id="1"), session_id="s")

        result = queue.build_queue([j1, j2, j3])
        ids = [j.id for j in result]
        assert "1" not in ids  # 已投递被过滤
        assert "2" in ids
        assert "3" in ids

    def test_keeps_failed_jobs(self, temp_database):
        """FAILED 的职位不被过滤(可重试)"""
        temp_database.set_account("default")
        queue = ApplyQueue(temp_database, TEST_CONFIG)

        j1 = make_job("1")
        temp_database.save_job(j1)
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.FAILED, job_id="1"), session_id="s")

        result = queue.build_queue([j1])
        assert len(result) == 1

    def test_empty_input_returns_empty(self, temp_database):
        queue = ApplyQueue(temp_database, TEST_CONFIG)
        assert queue.build_queue([]) == []


# ═══════════════════════════════════════════════════════
#  build_queue: 优先级排序
# ═══════════════════════════════════════════════════════

class TestBuildQueuePrioritization:
    def test_job_with_salary_ranks_higher(self, temp_database):
        """有薪资信息的职位排序更靠前(+20)"""
        queue = ApplyQueue(temp_database, TEST_CONFIG)
        no_salary = make_job("1", salary=None)
        with_salary = make_job("2", salary="HKD 30K")

        result = queue.build_queue([no_salary, with_salary])
        assert result[0].id == "2"  # 有薪资优先

    def test_job_with_location_ranks_higher(self, temp_database):
        """有地点的 +10"""
        queue = ApplyQueue(temp_database, TEST_CONFIG)
        no_loc = make_job("1", location=None)
        with_loc = make_job("2", location="HK")

        result = queue.build_queue([no_loc, with_loc])
        assert result[0].id == "2"

    def test_today_posted_ranks_highest(self, temp_database):
        """posted_date 含 'today' 得 +30,高于薪资 +20"""
        queue = ApplyQueue(temp_database, TEST_CONFIG)
        salary_only = make_job("1", salary="HKD 30K", posted_date="2 days ago")
        today = make_job("2", salary=None, posted_date="Today")

        result = queue.build_queue([salary_only, today])
        assert result[0].id == "2"  # today(30) > salary(20)


# ═══════════════════════════════════════════════════════
#  build_queue: 限量
# ═══════════════════════════════════════════════════════

class TestBuildQueueLimit:
    def test_limits_to_max_applies_per_session(self, temp_database):
        """超过 max_applies_per_session 的部分被截断"""
        config = SchedulerConfig(max_applies_per_session=2, max_per_hour=10,
                                 max_per_day=30, min_delay_between_seconds=1.0)
        queue = ApplyQueue(temp_database, config)
        jobs = [make_job(str(i)) for i in range(10)]

        result = queue.build_queue(jobs)
        assert len(result) == 2


# ═══════════════════════════════════════════════════════
#  RateLimiter: 频率计算
# ═══════════════════════════════════════════════════════

class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_wait_if_needed_skips_delay_on_first_apply(self, temp_database):
        """本小时无已提交记录(hour_count==0)= 首次申请,跳过 min_delay 不等待"""
        config = SchedulerConfig(max_applies_per_session=10, max_per_hour=10,
                                 max_per_day=30, min_delay_between_seconds=100.0)
        limiter = RateLimiter(config, temp_database)

        with patch("src.scheduler.queue.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await limiter.wait_if_needed()
            # 首次申请不等待
            mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_wait_if_needed_sleeps_min_delay_on_second_apply(
        self, temp_database, sample_jobs
    ):
        """本小时已有 1 条提交(非首次)→ 等待 min_delay + 随机扰动"""
        config = SchedulerConfig(max_applies_per_session=10, max_per_hour=10,
                                 max_per_day=30, min_delay_between_seconds=100.0)
        limiter = RateLimiter(config, temp_database)
        temp_database.set_account("default")

        # 制造 1 条已提交(使 hour_count=1,非首次)
        job = sample_jobs[0]
        temp_database.save_job(job)
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id), session_id="s1")

        with patch("src.scheduler.queue.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await limiter.wait_if_needed()
            mock_sleep.assert_awaited_once()
            slept = mock_sleep.await_args.args[0]
            # 100 + [0, 30) 的随机
            assert 100 <= slept < 130

    @pytest.mark.asyncio
    async def test_hourly_limit_triggers_long_wait(self, temp_database, sample_jobs):
        """达到 max_per_hour 时,等待到下一小时"""
        config = SchedulerConfig(max_applies_per_session=10, max_per_hour=2,
                                 max_per_day=30, min_delay_between_seconds=1.0)
        limiter = RateLimiter(config, temp_database)
        temp_database.set_account("default")

        # 制造 2 个已提交(达到 max_per_hour=2)
        job = sample_jobs[0]
        temp_database.save_job(job)
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id), session_id="s1")
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id), session_id="s2")

        with patch("src.scheduler.queue.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await limiter.wait_if_needed()
            mock_sleep.assert_awaited_once()
            slept = mock_sleep.await_args.args[0]
            # 等到下一小时,应该是几百到几千秒
            assert slept > 60  # 不是 min_delay(1s),是长等待

    @pytest.mark.asyncio
    async def test_daily_limit_triggers_wait_until_tomorrow(self, temp_database, sample_jobs):
        """达到 max_per_day 时,等到明天"""
        config = SchedulerConfig(max_applies_per_session=10, max_per_hour=100,
                                 max_per_day=2, min_delay_between_seconds=1.0)
        limiter = RateLimiter(config, temp_database)
        temp_database.set_account("default")

        job = sample_jobs[0]
        temp_database.save_job(job)
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id), session_id="s1")
        temp_database.record_application(
            ApplyResult(status=ApplyStatus.SUBMITTED, job_id=job.id), session_id="s2")

        with patch("src.scheduler.queue.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await limiter.wait_if_needed()
            slept = mock_sleep.await_args.args[0]
            # 等到明天,应该 > 1小时
            assert slept > 3600


# ═══════════════════════════════════════════════════════
#  RateLimiter: 无 db 时
# ═══════════════════════════════════════════════════════

class TestRateLimiterNoDb:
    @pytest.mark.asyncio
    async def test_no_db_only_min_delay(self):
        """无 db 时,只走 min_delay 分支(不查频率)"""
        config = SchedulerConfig(max_applies_per_session=10, max_per_hour=10,
                                 max_per_day=30, min_delay_between_seconds=50.0)
        limiter = RateLimiter(config, db=None)

        with patch("src.scheduler.queue.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await limiter.wait_if_needed()
            slept = mock_sleep.await_args.args[0]
            assert 50 <= slept < 65  # 50 + [0, 15)
