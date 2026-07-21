"""
flow — 申请流程状态机骨架

v2.0: 从 v1.0 apply_flow.py(543 行) 拆出的主循环。只含:
- ApplyStep 枚举
- ApplyFlow.apply() 主循环(状态推进 + 超时/计数)
- default_handler_chain()(按优先级的步骤处理器链)

每个 step 的处理逻辑在 steps/* 独立类里,可单独用 FakePageController 测。
行为与 v1.0 完全一致(机械迁移),特征化测试保证。
"""

import asyncio
import random
import time
from typing import Optional

from loguru import logger

from src.browser.ports.page_controller import PageController
from src.jobsdb.apply.detectors import (
    check_captcha,
    check_success,
    detect_current_step,
    get_error_message,
)
from src.jobsdb.apply.step_base import ApplyStep, StepHandler
from src.jobsdb.apply.steps import (
    CoverLetterStep,
    QuestionsStep,
    ResumeStep,
    ReviewStep,
    SubmitStep,
)
from src.jobsdb.exceptions import CaptchaDetectedError
from src.jobsdb.selectors import APPLY_FORM, APPLY_MODAL, SUBMIT_APPLICATION_BUTTON
from src.simulation.behavior import HumanSimulator
from src.storage.models import ApplyResult, ApplyStatus
from src.utils.screenshot import capture_screenshot

# 步骤 → handler 映射(v1.0 _handle_step 的 handlers dict 等价)
_STEP_HANDLERS = {
    ApplyStep.RESUME_SELECTION: ResumeStep(),
    ApplyStep.QUESTIONS: QuestionsStep(),
    ApplyStep.COVER_LETTER: CoverLetterStep(),
    ApplyStep.REVIEW: ReviewStep(),
}


def default_handler_chain() -> list[StepHandler]:
    """默认步骤处理器链(按优先级)"""
    return [
        SubmitStep(),       # SUBMITTED 检测优先
        ResumeStep(),
        QuestionsStep(),
        CoverLetterStep(),
        ReviewStep(),
    ]


class ApplyFlow:
    """申请流程处理器(v2.0 状态机骨架)"""

    def __init__(self, page: PageController, human: Optional[HumanSimulator] = None,
                 max_steps: int = 10,
                 handlers: Optional[list[StepHandler]] = None):
        self.page = page
        self.human = human
        self.max_steps = max_steps
        self.handlers = handlers or default_handler_chain()
        self.current_step: ApplyStep = ApplyStep.UNKNOWN
        self.step_count = 0
        self.start_time: Optional[float] = None

    async def apply(self, job_id: str) -> ApplyResult:
        """执行完整申请流程(v1.0 apply 主循环,行为一致)"""
        self.start_time = time.time()
        self.step_count = 0

        try:
            logger.info(f"Starting apply flow for job {job_id}")

            # 检测到 CAPTCHA
            if await check_captcha(self.page):
                return ApplyResult(
                    status=ApplyStatus.CAPTCHA,
                    job_id=job_id,
                    error_message="CAPTCHA detected",
                )

            # 处理可能的弹窗
            await self._dismiss_popups()

            # 等待申请表单/弹窗出现
            await self._wait_for_apply_form()

            # 状态机循环
            while self.step_count < self.max_steps:
                self.step_count += 1
                current = await detect_current_step(self.page)
                self.current_step = current
                logger.debug(f"Apply step {self.step_count}: {current.value}")

                if current == ApplyStep.SUBMITTED:
                    # 成功!
                    duration = time.time() - self.start_time
                    return ApplyResult(
                        status=ApplyStatus.SUBMITTED,
                        job_id=job_id,
                        duration_seconds=round(duration, 2),
                    )

                if current == ApplyStep.UNKNOWN:
                    # 无法识别当前阶段,检查是否已在成功状态
                    if await check_success(self.page):
                        duration = time.time() - self.start_time
                        return ApplyResult(
                            status=ApplyStatus.SUBMITTED,
                            job_id=job_id,
                            duration_seconds=round(duration, 2),
                        )

                    # 有错误或无法识别的状态
                    error = await get_error_message(self.page)
                    if error:
                        return ApplyResult(
                            status=ApplyStatus.FAILED,
                            job_id=job_id,
                            error_message=error,
                        )

                    # 可能还在加载
                    await asyncio.sleep(1)
                    continue

                # 处理当前阶段
                success = await self._handle_step(current)
                if not success:
                    return ApplyResult(
                        status=ApplyStatus.FAILED,
                        job_id=job_id,
                        error_message=f"Failed at step: {current.value}",
                    )

                # 阶段转换等待
                await asyncio.sleep(random.uniform(1.5, 3.0))

            # 超过最大步数
            return ApplyResult(
                status=ApplyStatus.FAILED,
                job_id=job_id,
                error_message="Max steps exceeded",
            )

        except CaptchaDetectedError:
            return ApplyResult(
                status=ApplyStatus.CAPTCHA,
                job_id=job_id,
                error_message="CAPTCHA detected",
            )
        except Exception as e:
            logger.exception(f"Apply flow error: {e}")
            screenshot = await capture_screenshot(self.page, f"apply_error_{job_id}")
            return ApplyResult(
                status=ApplyStatus.FAILED,
                job_id=job_id,
                error_message=str(e),
                screenshot_path=screenshot,
            )

    async def _handle_step(self, step: ApplyStep) -> bool:
        """处理指定阶段(v1.0 _handle_step:委托给对应 handler)"""
        handler = _STEP_HANDLERS.get(step)
        if handler:
            return await handler.handle(self.page, self.human)
        return False

    async def _dismiss_popups(self) -> None:
        """关闭可能的弹窗(v1.0 _dismiss_popups,委托到 steps/popup_dismiss)"""
        from src.jobsdb.apply.steps.popup_dismiss import run as dismiss_popups
        await dismiss_popups(self.page)

    async def _wait_for_apply_form(self) -> None:
        """等待申请表单出现(v1.0 _wait_for_apply_form)"""
        try:
            await self.page.wait_for_selector(
                f"{APPLY_MODAL}, {APPLY_FORM}, {SUBMIT_APPLICATION_BUTTON}",
                timeout=10000,
            )
        except Exception:
            logger.warning("Apply form not detected, proceeding anyway")
