"""
Application form processing — state machine driven

Processing multiple application variants:
1. Easy Apply (one-page quick application)
2. Standard Apply (multi-step form)

State machine design, layering by form phases.
"""

import asyncio
import random
import time
from enum import Enum, auto
from typing import Optional

from loguru import logger

from src.browser.ports.page_controller import PageController
from src.jobsdb.exceptions import ApplyError, CaptchaDetectedError
from src.jobsdb.selectors import (
    ADDITIONAL_QUESTIONS,
    ALREADY_APPLIED_BADGE,
    APPLY_FORM,
    APPLY_MODAL,
    BACK_BUTTON,
    CONFIRM_SUBMIT_BUTTON,
    CONTINUE_BUTTON,
    COOKIE_ACCEPT_BUTTON,
    COOKIE_BANNER,
    COVER_LETTER_SECTION,
    COVER_LETTER_TEXTAREA,
    DEFAULT_RESUME_RADIO,
    ERROR_MESSAGE,
    FORM_VALIDATION_ERROR,
    LOADING_SPINNER,
    NEXT_STEP_BUTTON,
    NOTIFICATION_NO,
    NOTIFICATION_PROMPT,
    RECAPTCHA_IFRAME,
    RESUME_DROPDOWN,
    RESUME_SELECTION,
    STEP_CURRENT,
    STEP_INDICATOR,
    STEP_TOTAL,
    SUBMIT_APPLICATION_BUTTON,
    SUCCESS_MESSAGE,
    SUCCESS_MODAL,
)
from src.simulation.behavior import HumanSimulator
from src.storage.models import ApplyResult, ApplyStatus
from src.utils.screenshot import capture_screenshot


class ApplyStep(str, Enum):
    """Application phase"""
    RESUME_SELECTION = "resume_selection"
    QUESTIONS = "questions"
    COVER_LETTER = "cover_letter"
    REVIEW = "review"
    SUBMITTED = "submitted"
    UNKNOWN = "unknown"


class ApplyFlow:
    """
    Application flow processor

    Handles the complete application process, from clicking Apply to confirming success.
    """

    def __init__(self, page: PageController, human: Optional[HumanSimulator] = None,
                 max_steps: int = 10):
        self.page = page
        self.human = human
        self.max_steps = max_steps
        self.current_step: ApplyStep = ApplyStep.UNKNOWN
        self.step_count = 0
        self.start_time: Optional[float] = None

    async def apply(self, job_id: str) -> ApplyResult:
        """
        Execute the complete application process

        Args:
            job_id: Job ID

        Returns:
            ApplyResult
        """
        self.start_time = time.time()
        self.step_count = 0

        try:
            logger.info(f"Starting apply flow for job {job_id}")

            # Detected CAPTCHA
            if await self._check_captcha():
                return ApplyResult(
                    status=ApplyStatus.CAPTCHA,
                    job_id=job_id,
                    error_message="CAPTCHA detected",
                )

            # Handle possible popups
            await self._dismiss_popups()

            # Wait for the application form/modal to appear
            await self._wait_for_apply_form()

            # State machine loop
            while self.step_count < self.max_steps:
                self.step_count += 1
                current = await self._detect_current_step()
                logger.debug(f"Apply step {self.step_count}: {current.value}")

                if current == ApplyStep.SUBMITTED:
                    # Success!
                    duration = time.time() - self.start_time
                    return ApplyResult(
                        status=ApplyStatus.SUBMITTED,
                        job_id=job_id,
                        duration_seconds=round(duration, 2),
                    )

                if current == ApplyStep.UNKNOWN:
                    # Can not identify the current phase, check if it is already in a success state
                    if await self._check_success():
                        duration = time.time() - self.start_time
                        return ApplyResult(
                            status=ApplyStatus.SUBMITTED,
                            job_id=job_id,
                            duration_seconds=round(duration, 2),
                        )

                    # There is an error or an unrecognized state
                    error = await self._get_error_message()
                    if error:
                        return ApplyResult(
                            status=ApplyStatus.FAILED,
                            job_id=job_id,
                            error_message=error,
                        )

                    # May need to have loaded
                    await asyncio.sleep(1)
                    continue

                # Process the current phase
                success = await self._handle_step(current)
                if not success:
                    return ApplyResult(
                        status=ApplyStatus.FAILED,
                        job_id=job_id,
                        error_message=f"Failed at step: {current.value}",
                    )

                # Phase transition waiting
                await asyncio.sleep(random.uniform(1.5, 3.0))

            # Exceeded the maximum number of steps
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

    async def _detect_current_step(self) -> ApplyStep:
        """Detect the current phase"""
        # Check success state
        if await self._check_success():
            return ApplyStep.SUBMITTED

        # Check phase indicator
        step_indicator = await self.page.query_selector(STEP_INDICATOR)
        if step_indicator:
            # There is phase indication, try to parse
            try:
                current_step_text = await step_indicator.text_content()
                if current_step_text:
                    text_lower = current_step_text.lower()
                    if "resume" in text_lower:
                        return ApplyStep.RESUME_SELECTION
                    elif "question" in text_lower:
                        return ApplyStep.QUESTIONS
                    elif "cover" in text_lower:
                        return ApplyStep.COVER_LETTER
                    elif "review" in text_lower:
                        return ApplyStep.REVIEW
            except Exception:
                pass

        # Determine by form element
        if await self.page.query_selector(RESUME_SELECTION):
            return ApplyStep.RESUME_SELECTION

        if await self.page.query_selector(ADDITIONAL_QUESTIONS):
            return ApplyStep.QUESTIONS

        if await self.page.query_selector(COVER_LETTER_SECTION):
            return ApplyStep.COVER_LETTER

        # Submittable state (Submit button visible, but not submitted yet)
        submit_btn = await self.page.query_selector(SUBMIT_APPLICATION_BUTTON)
        if submit_btn:
            is_visible = await submit_btn.is_visible()
            if is_visible:
                # Check if it is the final review phase
                if await self.page.query_selector(CONFIRM_SUBMIT_BUTTON):
                    return ApplyStep.REVIEW
                # May be a one-page application form, need to check if there are other steps
                return ApplyStep.REVIEW

        # Check if an error page
        error = await self.page.query_selector(ERROR_MESSAGE)
        if error:
            return ApplyStep.UNKNOWN

        # Check loading
        loading = await self.page.query_selector(LOADING_SPINNER)
        if loading:
            await asyncio.sleep(2)
            return await self._detect_current_step()

        return ApplyStep.UNKNOWN

    async def _handle_step(self, step: ApplyStep) -> bool:
        """Process specified phase"""
        handlers = {
            ApplyStep.RESUME_SELECTION: self._handle_resume_step,
            ApplyStep.QUESTIONS: self._handle_questions_step,
            ApplyStep.COVER_LETTER: self._handle_cover_letter_step,
            ApplyStep.REVIEW: self._handle_review_step,
        }

        handler = handlers.get(step)
        if handler:
            return await handler()

        return False

    async def _handle_resume_step(self) -> bool:
        """Resume selection phase"""
        logger.debug("Handling resume selection step")

        try:
            # Check if the default resume is selected
            default_radio = await self.page.query_selector(DEFAULT_RESUME_RADIO)
            if default_radio:
                # Confirm using default resume
                is_checked = await default_radio.is_checked()
                if not is_checked:
                    if self.human:
                        await self.human.mouse.click_element(default_radio)
                    else:
                        await default_radio.click()
                    await asyncio.sleep(0.5)
            else:
                # Try dropdown
                dropdown = await self.page.query_selector(RESUME_DROPDOWN)
                if dropdown:
                    # Select first option (assume it is the default resume)
                    options = await dropdown.query_selector_all("option")
                    if len(options) > 0:
                        await dropdown.select_option(index=0)
                        await asyncio.sleep(0.5)

            # Click the next step button
            return await self._click_next_or_submit()

        except Exception as e:
            logger.warning(f"Resume step error: {e}")
            return False

    async def _handle_questions_step(self) -> bool:
        """Handle additional questions"""
        logger.debug("Handling questions step")

        try:
            # Find all questions
            questions = await self.page.query_selector_all(ADDITIONAL_QUESTIONS)

            for question in questions:
                # Check the question type
                select = await question.query_selector("select")
                if select:
                    # Dropdown selection
                    options = await select.query_selector_all("option")
                    # Select the first non-empty option
                    for i, option in enumerate(options):
                        value = await option.get_attribute("value")
                        if value and value.strip():
                            await select.select_option(index=i)
                            break
                    continue

                # Text input or text area
                text_input = await question.query_selector("input[type=\"text\"], textarea")
                if text_input:
                    # Detect if it is a Yes/No question
                    label = await question.query_selector("label, .question-label")
                    if label:
                        label_text = await label.text_content() or ""
                        label_lower = label_text.lower()

                        if "year" in label_lower and "experience" in label_lower:
                            await text_input.fill("3")
                        elif "salary" in label_lower or "expected" in label_lower:
                            await text_input.fill("Negotiable")
                        else:
                            # Generic fill
                            await text_input.fill("N/A")
                    else:
                        await text_input.fill("N/A")
                    continue

                # Radio button
                radios = await question.query_selector_all("input[type=\"radio\"]")
                if radios:
                    # Select the first option
                    await radios[0].click()
                    continue

                # Checkbox
                checkboxes = await question.query_selector_all("input[type=\"checkbox\"]")
                if checkboxes:
                    # Select the first option
                    await checkboxes[0].click()

            await asyncio.sleep(0.5)
            return await self._click_next_or_submit()

        except Exception as e:
            logger.warning(f"Questions step error: {e}")
            return False

    async def _handle_cover_letter_step(self) -> bool:
        """Cover letter phase"""
        logger.debug("Handling cover letter step")

        try:
            # Check if it is optional
            textarea = await self.page.query_selector(COVER_LETTER_TEXTAREA)
            if textarea:
                # Check if required
                is_required = await textarea.get_attribute("required")
                if is_required:
                    # Need to fill in the cover letter
                    # Use generic cover letter content
                    cover_letter = (
                        "Dear Hiring Manager,\n\n"
                        "I am excited to apply for this position. "
                        "With my relevant experience and skills, I believe I would be a great fit. "
                        "I look forward to the opportunity to discuss how I can contribute to your team.\n\n"
                        "Best regards"
                    )

                    if self.human:
                        await self.human.fill_form_field(textarea, cover_letter)
                    else:
                        await textarea.fill(cover_letter)

                    await asyncio.sleep(0.5)

            return await self._click_next_or_submit()

        except Exception as e:
            logger.warning(f"Cover letter step error: {e}")
            return False

    async def _handle_review_step(self) -> bool:
        """Review and submit phase"""
        logger.debug("Handling review & submit step")

        try:
            # Find the submit button
            submit_btn = await self.page.query_selector(SUBMIT_APPLICATION_BUTTON)
            if not submit_btn:
                submit_btn = await self.page.query_selector(CONFIRM_SUBMIT_BUTTON)

            if not submit_btn:
                logger.error("Submit button not found")
                return False

            # Check if it is clickable
            is_visible = await submit_btn.is_visible()
            if not is_visible:
                logger.error("Submit button not visible")
                return False

            # Click to submit (the most critical action, add a longer wait)
            logger.info("Clicking submit button")

            if self.human:
                await self.human.click_apply_button(submit_btn)
            else:
                await submit_btn.click()

            # Wait for the submission response
            await asyncio.sleep(3)

            # Check success status
            return await self._check_success()

        except Exception as e:
            logger.warning(f"Review step error: {e}")
            return False

    async def _click_next_or_submit(self) -> bool:
        """Click next step or submit button"""
        # Priority: Next button > Submit button
        next_btn = await self.page.query_selector(NEXT_STEP_BUTTON)
        if next_btn:
            is_visible = await next_btn.is_visible()
            if is_visible:
                if self.human:
                    await self.human.mouse.click_element(next_btn)
                else:
                    await next_btn.click()
                await asyncio.sleep(2)
                return True

        submit_btn = await self.page.query_selector(SUBMIT_APPLICATION_BUTTON)
        if submit_btn:
            is_visible = await submit_btn.is_visible()
            if is_visible:
                if self.human:
                    await self.human.mouse.click_element(submit_btn)
                else:
                    await submit_btn.click()
                await asyncio.sleep(2)
                return True

        return False

    async def _check_success(self) -> bool:
        """Check if the submission was successful"""
        try:
            # Check for success message
            success = await self.page.query_selector(SUCCESS_MESSAGE)
            if success:
                return True

            success_modal = await self.page.query_selector(SUCCESS_MODAL)
            if success_modal:
                return True

            # Check page text
            page_text = await self.page.text_content("body")
            success_indicators = [
                "Application submitted",
                "successfully submitted",
                "Thank you for applying",
                "Application received",
                "申请已提交",
                "已成功提交",
            ]
            if any(indicator in page_text for indicator in success_indicators):
                return True

            return False
        except Exception:
            return False

    async def _check_captcha(self) -> bool:
        """Check if there is a CAPTCHA"""
        try:
            captcha = await self.page.query_selector(RECAPTCHA_IFRAME)
            if captcha:
                logger.warning("CAPTCHA detected")
                return True

            hcaptcha = await self.page.query_selector(
                'iframe[src*="hcaptcha"], .h-captcha'
            )
            if hcaptcha:
                logger.warning("hCaptcha detected")
                return True

            return False
        except Exception:
            return False

    async def _dismiss_popups(self) -> None:
        """Close possible pop-up windows"""
        popup_selectors = [
            COOKIE_BANNER,
            NOTIFICATION_PROMPT,
            'button:has-text("Not now")',
            'button:has-text("Skip")',
            'button:has-text("No thanks")',
        ]

        for selector in popup_selectors:
            try:
                popup = await self.page.query_selector(selector)
                if popup:
                    await popup.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass

    async def _wait_for_apply_form(self) -> None:
        """Wait for the application form to appear"""
        try:
            # Wait for modal or form
            await self.page.wait_for_selector(
                f"{APPLY_MODAL}, {APPLY_FORM}, {SUBMIT_APPLICATION_BUTTON}",
                timeout=10000,
            )
        except Exception:
            logger.warning("Apply form not detected, proceeding anyway")

    async def _get_error_message(self) -> Optional[str]:
        """Get error message"""
        try:
            error = await self.page.query_selector(ERROR_MESSAGE)
            if error:
                text = await error.text_content()
                return text.strip() if text else None

            validation = await self.page.query_selector(FORM_VALIDATION_ERROR)
            if validation:
                text = await validation.text_content()
                return text.strip() if text else None
        except Exception:
            pass
        return None
