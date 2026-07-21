"""
Orchestrator — Director layer, main loop

Coordinate all modules to complete the end-to-end job submission process.
"""

import asyncio
import uuid
from typing import List, Optional

from playwright.async_api import Page
from loguru import logger

from config.settings import AppConfig, get_config
from src.accounts.registry import Account
from src.browser.engine import BrowserEngine
from src.browser.ports.page_controller import PageController
from src.browser.playwright_page_controller import PlaywrightPageController
from src.jobsdb.apply.flow import ApplyFlow
from src.jobsdb.homepage import HomepageScraper
from src.jobsdb.job_detail import JobDetailPage
from src.jobsdb.login import LoginHandler
from src.monitor.tracker import AlertManager, ApplicationTracker, StatsAggregator
from src.scheduler.queue import ApplyQueue, RateLimiter, TimingOptimizer
from src.simulation.behavior import HumanSimulator
from src.storage.database import Database
from src.storage.models import ApplyResult, ApplyStatus, JobListing, SessionStatus
from src.utils.screenshot import capture_screenshot, generate_session_id


class Orchestrator:
    """
    Director

    Main responsibilities:
    1. Initialize and coordinate all modules
    2. Execute the main loop: login → grab positions → submit
    3. Handle exceptions and alerts
    4. Generate session reports
    """

    def __init__(self, config: Optional[AppConfig] = None,
                 account: Optional[Account] = None,
                 max_jobs: Optional[int] = None):
        self.config = config or get_config()
        self.account = account or Account(alias="default", email="", password="")
        self.max_jobs = max_jobs or self.config.scheduler.max_applies_per_session

        # Core modules
        self.browser: Optional[BrowserEngine] = None
        self.page: Optional[Page] = None
        self.page_controller: Optional[PageController] = None
        self.human: Optional[HumanSimulator] = None

        # Data storage (带账户隔离)
        self.db = Database(self.config.storage.database_path)
        self.db.set_account(self.account.alias)

        # JobsDB interaction
        self.login_handler: Optional[LoginHandler] = None
        self.scraper: Optional[HomepageScraper] = None

        # Scheduler
        self.queue_manager = ApplyQueue(self.db, self.config.scheduler)
        self.rate_limiter = RateLimiter(self.config.scheduler, self.db)
        self.timing_optimizer = TimingOptimizer(self.config.scheduler)

        # Monitor
        self.tracker = ApplicationTracker(self.db)
        self.alert = AlertManager(self.config.monitoring.alert_on_captcha)
        self.stats = StatsAggregator(self.db)

        # State
        self.session_id: Optional[str] = None
        self.jobs_processed = 0
        self.jobs_succeeded = 0
        self.consecutive_failures = 0
        self.detection_suspected = False

    async def run(self) -> dict:
        """
        Main execution method

        Returns:
            Session summary report
        """
        logger.info("=" * 50)
        logger.info("JobsDB Resume Assistant Starting...")
        logger.info(f"Max jobs this session: {self.max_jobs}")
        logger.info("=" * 50)

        try:
            # Phase 1: Initialize the browser
            await self._init_browser()

            # Phase 2: Login
            if not await self._ensure_login():
                return self._create_error_report("Login failed")

            # Phase 3: Grab recommended positions
            jobs = await self._scrape_jobs()
            if not jobs:
                logger.info("No new jobs to apply")
                return self._create_empty_report()

            # Phase 4: Build the queue
            queue = self.queue_manager.build_queue(jobs)
            if not queue:
                logger.info("No new jobs after filtering")
                return self._create_empty_report()

            # Phase 5: Process the queue
            self.session_id = generate_session_id(self.account.alias)
            self.tracker.start_session(session_id=self.session_id)
            await self._process_queue(queue)

            # Phase 6: Generate the report
            return self._create_session_report()
            logger.exception(f"Orchestrator error: {e}")
            return self._create_error_report(str(e))
        finally:
            await self._cleanup()

    async def _init_browser(self) -> None:
        """Initialize the browser"""
        logger.info(f"Initializing browser for account [{self.account.alias}]...")
        self.browser = BrowserEngine(
            self.config.browser,
            account_alias=self.account.alias,
        )
        self.page = await self.browser.start()
        # jobsdb/* 依赖 PageController 接口;HumanSimulator 仍需原始 Page(mouse/viewport)
        self.page_controller = PlaywrightPageController(self.page)

        # Initialize the human behavior simulator
        self.human = HumanSimulator(
            self.page,
            bezier_points=self.config.simulation.mouse_bezier_points,
            typo_probability=self.config.simulation.typing_typo_probability,
            base_delay_ms=self.config.simulation.typing_base_delay_ms,
            delay_variance_ms=self.config.simulation.typing_delay_variance_ms,
        )

        # Initialize the JobsDB handler
        self.login_handler = LoginHandler(
            self.page_controller, self.config.jobsdb, self.human, self.account
        )
        self.scraper = HomepageScraper(self.page_controller, self.human)

    async def _ensure_login(self) -> bool:
        """Ensure login status"""
        try:
            return await self.login_handler.ensure_logged_in()
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    async def _scrape_jobs(self) -> List[JobListing]:
        """Grab positions from the homepage"""
        logger.info("Navigating to homepage to scrape jobs...")

        # Navigate to the homepage
        await self.browser.goto(self.config.jobsdb.homepage_url)
        await asyncio.sleep(3)  # Wait for dynamic content to load

        # Grab positions
        jobs = await self.scraper.get_recommended_jobs(max_jobs=50)

        # Save the position information to the database
        for job in jobs:
            self.db.save_job(job)

        return jobs

    async def _process_queue(self, queue: List[JobListing]) -> None:
        """Process the application queue"""
        logger.info(f"Processing {len(queue)} jobs...")

        for i, job in enumerate(queue, 1):
            logger.info(f"[{i}/{len(queue)}] Processing: {job.title} @ {job.company}")

            # Frequency limit check
            await self.rate_limiter.wait_if_needed()

            # Check if suspected of being detected
            if self.detection_suspected:
                if self.consecutive_failures >= self.config.monitoring.suspicion_threshold:
                    logger.warning("Detection threshold reached, aborting session")
                    self.tracker.end_session(
                        self.session_id,
                        SessionStatus.ABORTED,
                        "Detection suspected",
                    )
                    return

            # Execute the application
            result = await self._apply_to_job(job)

            # Update statistics
            self.jobs_processed += 1
            if result.status == ApplyStatus.SUBMITTED:
                self.jobs_succeeded += 1
                self.consecutive_failures = 0
            elif result.status == ApplyStatus.FAILED:
                self.consecutive_failures += 1
            elif result.status == ApplyStatus.CAPTCHA:
                # CAPTCHA, wait for manual resolution
                await self.alert.captcha_alert(self.page_controller, self.page.url)
                self.consecutive_failures = 0

            # Record the application result
            self.tracker.record_application(self.session_id, job, result)

            # Detection suspicion check
            if self.consecutive_failures >= self.config.monitoring.suspicion_threshold:
                self.detection_suspected = True
                self.alert.detection_suspected_alert(
                    f"{self.consecutive_failures} consecutive failures"
                )

            # Random distraction behavior (simulate real human "daydreaming")
            if i < len(queue) and not self.detection_suspected:
                if asyncio.iscoroutinefunction(self.human.random_distractor):
                    await self.human.random_distractor()

        # Normal end of session
        self.tracker.end_session(self.session_id, SessionStatus.COMPLETED)

    async def _apply_to_job(self, job: JobListing) -> ApplyResult:
        """
        Apply to a single position

        Full process:
        1. Navigate to the position details page
        2. Check if already applied
        3. Click the apply button
        4. Process the application form
        5. Confirm the result
        """
        try:
            # Navigate to the position details page
            detail_page = JobDetailPage(self.page_controller, job.url, self.human)
            await detail_page.navigate_with_simulation()

            # Check if already applied
            if await detail_page.is_already_applied():
                logger.info(f"Already applied to {job.title}, skipping")
                return ApplyResult(
                    status=ApplyStatus.SKIPPED,
                    job_id=job.id,
                    reason="already_applied",
                )

            # Get the apply button
            apply_button = await detail_page.get_apply_button()
            if not apply_button:
                logger.warning(f"Apply button not found for {job.title}")
                return ApplyResult(
                    status=ApplyStatus.FAILED,
                    job_id=job.id,
                    error_message="Apply button not found",
                )

            # Click the apply button
            if self.human:
                await self.human.click_apply_button(apply_button)
            else:
                await apply_button.click()
                await asyncio.sleep(2)

            # Wait for the form/modal to appear
            await asyncio.sleep(2)

            # Handle the application flow
            apply_flow = ApplyFlow(self.page_controller, self.human)
            result = await apply_flow.apply(job.id)

            return result

        except Exception as e:
            logger.exception(f"Error applying to job {job.id}: {e}")
            screenshot = await capture_screenshot(self.page_controller, f"error_{job.id}")
            return ApplyResult(
                status=ApplyStatus.FAILED,
                job_id=job.id,
                error_message=str(e),
                screenshot_path=screenshot,
            )

    def _create_session_report(self) -> dict:
        """Create a session report"""
        if not self.session_id:
            return self._create_error_report("No session created")

        summary = self.stats.get_session_summary(self.session_id)

        logger.info("=" * 50)
        logger.info("Session Summary")
        logger.info(f"  Session ID: {self.session_id}")
        logger.info(f"  Jobs processed: {summary['total']}")
        logger.info(f"  Successful: {summary['success']}")
        logger.info(f"  Failed: {summary['failed']}")
        logger.info(f"  Skipped: {summary['skipped']}")
        logger.info(f"  Success rate: {summary['success_rate']}%")
        logger.info("=" * 50)

        return summary

    def _create_error_report(self, error: str) -> dict:
        """Create an error report"""
        return {
            "error": error,
            "session_id": self.session_id,
            "total": self.jobs_processed,
            "success": self.jobs_succeeded,
            "success_rate": 0,
        }

    def _create_empty_report(self) -> dict:
        """Create an empty report (no jobs)"""
        return {
            "message": "No jobs to apply",
            "total": 0,
            "success": 0,
            "success_rate": 0,
        }

    async def _cleanup(self) -> None:
        """Clean up resources"""
        if self.browser:
            await self.browser.stop()
            logger.info("Browser stopped")
