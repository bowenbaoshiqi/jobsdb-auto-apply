"""
submit_step — 提交完成检测

v1.0 中 SUBMITTED 由 _detect_current_step / _check_success 判定,无独立 handler。
此模块提供步骤语义封装:检测是否已提交成功。
"""

from src.browser.ports.page_controller import PageController
from src.jobsdb.apply.detectors import check_success


class SubmitStep:
    """SUBMITTED 步骤处理器(只检测,不操作)"""

    async def detect(self, page: PageController) -> bool:
        return await check_success(page)

    async def handle(self, page: PageController, human=None) -> bool:
        # 已提交,无需操作
        return True
