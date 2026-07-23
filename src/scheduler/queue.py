"""
Scheduling and control module
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from config.settings import SchedulerConfig, get_config
from src.storage.database import Database
from src.storage.models import JobListing


class ApplyQueue:
    """Application queue manager"""

    def __init__(self, db: Database, config: Optional[SchedulerConfig] = None):
        self.db = db
        self.config = config or get_config().scheduler

    def build_queue(self, jobs: list[JobListing]) -> list[JobListing]:
        """
        Build the application queue, filtering out already applied positions

        Args:
            jobs: Raw list of jobs grabbed from the homepage

        Returns:
            Filtered and sorted job list
        """
        # Get a list of already applied positions
        applied_ids = set(self.db.get_applied_job_ids())

        # Filter new jobs
        new_jobs = [job for job in jobs if job.id not in applied_ids]

        logger.info(f"Filtered {len(new_jobs)} new jobs from {len(jobs)} total")

        # Sort by priority
        prioritized = self._prioritize(new_jobs)

        # Limit the number per session
        return prioritized[:self.config.max_applies_per_session]

    def _prioritize(self, jobs: list[JobListing]) -> list[JobListing]:
        """
        Sort jobs by priority

        Strategy:
        1. Jobs with salary info (company is more formal)
        2. Recently published
        3. Have complete information
        """
        def score(job: JobListing) -> float:
            s = 0.0

            # Having salary info +20
            if job.salary:
                s += 20

            # Having location info +10
            if job.location:
                s += 10

            # Recent publishing (if date info is available)
            if job.posted_date:
                if "today" in job.posted_date.lower() or "today" in job.posted_date:
                    s += 30
                elif "hour" in job.posted_date.lower():
                    s += 25
                elif "day" in job.posted_date.lower() and "1" in job.posted_date:
                    s += 20

            return s

        # Descending order by score
        return sorted(jobs, key=score, reverse=True)


class RateLimiter:
    """Frequency limiter"""

    def __init__(self, config: Optional[SchedulerConfig] = None,
                 db: Optional[Database] = None):
        self.config = config or get_config().scheduler
        self.db = db

    async def wait_if_needed(self) -> None:
        """
        Wait if the frequency limit is exceeded
        """
        # Check the number of applications per hour
        if self.db:
            hour_count = self.db.get_application_count_last_hour()
            if hour_count >= self.config.max_per_hour:
                # Need to wait until the next hour
                wait_seconds = self._calculate_wait_for_next_hour()
                logger.warning(
                    f"Hourly rate limit reached ({hour_count}/{self.config.max_per_hour}). "
                    f"Waiting {wait_seconds:.0f}s"
                )
                await asyncio.sleep(wait_seconds)
                return

            # Check the number of applications per day
            day_count = self.db.get_application_count_today()
            if day_count >= self.config.max_per_day:
                # Today has reached the limit, need to wait until tomorrow
                wait_seconds = self._calculate_wait_for_tomorrow()
                logger.warning(
                    f"Daily rate limit reached ({day_count}/{self.config.max_per_day}). "
                    f"Waiting {wait_seconds:.0f}s (until tomorrow)"
                )
                await asyncio.sleep(wait_seconds)
                return

            # 第一次申请不等待(hour_count==0 表示本小时无记录,即首个职位),
            # 避免 5 个职位的测试要等 4×延迟。从第二个职位开始才走 min_delay + 抖动。
            if hour_count == 0:
                logger.debug("Rate limiter: first apply this hour, skipping min delay")
                return

        # Minimum interval waiting
        min_delay = self.config.min_delay_between_seconds
        # Add random perturbation
        delay = min_delay + random.uniform(0, min_delay * 0.3)

        logger.debug(f"Rate limiter: waiting {delay:.0f}s before next apply")
        await asyncio.sleep(delay)

    def _calculate_wait_for_next_hour(self) -> float:
        """Calculate the seconds to wait for the next hour"""
        now = datetime.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return (next_hour - now).total_seconds()

    def _calculate_wait_for_tomorrow(self) -> float:
        """Calculate the seconds to wait for tomorrow"""
        now = datetime.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return (tomorrow - now).total_seconds()


class TimingOptimizer:
    """Timing optimization"""

    def __init__(self, config: Optional[SchedulerConfig] = None):
        self.config = config or get_config().scheduler

    def is_good_time_to_apply(self) -> bool:
        """
        Check if the current time is suitable for applying

        Avoid peak hours:
        - Morning 9-11
        - Afternoon 14-16
        """
        now = datetime.now()
        hour = now.hour

        for period in self.config.peak_hours_exclude:
            if period["start"] <= hour < period["end"]:
                return False

        return True

    def get_optimal_start_delay(self) -> float:
        """
        Get the optimal start delay time

        If in peak hours, wait until after peak hours
        """
        if self.is_good_time_to_apply():
            return random.uniform(10, 30)  # Short wait

        now = datetime.now()
        hour = now.hour

        # Find the end time of the next non-peak period
        for period in sorted(self.config.peak_hours_exclude,
                            key=lambda x: x["start"]):
            if hour < period["start"]:
                # Before the peak period, wait until after the peak period
                target = now.replace(hour=period["end"], minute=random.randint(0, 30))
                return (target - now).total_seconds()

        # After the last peak period, wait until after the peak period tomorrow
        target = now + timedelta(days=1)
        target = target.replace(hour=9, minute=random.randint(0, 30))
        return (target - now).total_seconds()
