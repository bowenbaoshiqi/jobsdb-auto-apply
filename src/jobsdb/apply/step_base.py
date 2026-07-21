"""
step_base — StepHandler 协议 + ApplyStep 枚举

apply_flow 拆分的核心抽象:每个步骤(简历选择/问题/求职信/审核提交)独立成
一个 handler,实现 detect + handle。ApplyFlow 主循环遍历 handler 链,第一个
detect()==True 的负责 handle。

ApplyStep 枚举也放这里(而非 flow.py),避免 flow ↔ detectors 循环 import。

收益:每个 step 可用 FakePageController 独立单测,不起浏览器;加新步骤只需
加一个 steps/xxx_step.py + 注册到 default_handler_chain()。
"""

from enum import Enum
from typing import Protocol, runtime_checkable

from src.browser.ports.page_controller import PageController


class ApplyStep(str, Enum):
    """申请阶段(v1.0 枚举原样迁移)"""
    RESUME_SELECTION = "resume_selection"
    QUESTIONS = "questions"
    COVER_LETTER = "cover_letter"
    REVIEW = "review"
    SUBMITTED = "submitted"
    UNKNOWN = "unknown"


@runtime_checkable
class StepHandler(Protocol):
    """单个申请步骤的处理器。"""

    async def detect(self, page: PageController) -> bool:
        """当前页面是否处于此步骤。"""
        ...

    async def handle(self, page: PageController, human=None) -> bool:
        """处理此步骤,返回是否成功(True=继续下一步,False=终止)。"""
        ...
