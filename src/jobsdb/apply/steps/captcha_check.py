"""
captcha_check — CAPTCHA 检测(前置检查,非状态机 step)

v1.0 _check_captcha 的逻辑已迁到 detectors.check_success 同族,
此模块保留为 apply 流程的"前置关卡"语义:apply() 开头先调它,命中即短路返回。
"""

from src.browser.ports.page_controller import PageController
from src.jobsdb.apply.detectors import check_captcha


async def run(page: PageController) -> bool:
    """检测 CAPTCHA,返回 True 表示命中(应终止流程)"""
    return await check_captcha(page)
