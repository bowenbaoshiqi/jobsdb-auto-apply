"""
apply/steps — 申请流程的步骤处理器集合

每个 step 一个独立类,实现 StepHandler 协议(detect + handle)。
ApplyFlow 主循环遍历 handler 链处理申请。
"""

from src.jobsdb.apply.steps.cover_letter_step import CoverLetterStep
from src.jobsdb.apply.steps.questions_step import QuestionsStep
from src.jobsdb.apply.steps.resume_step import ResumeStep
from src.jobsdb.apply.steps.review_step import ReviewStep
from src.jobsdb.apply.steps.submit_step import SubmitStep

__all__ = [
    "CoverLetterStep",
    "QuestionsStep",
    "ResumeStep",
    "ReviewStep",
    "SubmitStep",
]
