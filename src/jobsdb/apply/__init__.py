"""
jobsdb.apply — 申请流程(状态机 + 步骤处理器)

v2.0: 从 v1.0 单文件 apply_flow.py(543 行) 拆分。

结构:
- flow.py: ApplyFlow 状态机骨架(apply 主循环)+ ApplyStep 枚举
- step_base.py: StepHandler 协议(detect + handle)
- detectors.py: 纯查询逻辑(当前步骤/成功/验证码/错误)
- steps/: 各步骤处理器(resume/questions/cover_letter/review/submit)
- steps/navigation.py: 步骤间导航辅助(click_next_or_submit)
- steps/popup_dismiss.py / captcha_check.py: 前置关卡

外部入口: from src.jobsdb.apply.flow import ApplyFlow, ApplyStep
"""

from src.jobsdb.apply.flow import ApplyFlow, default_handler_chain
from src.jobsdb.apply.step_base import ApplyStep

__all__ = ["ApplyFlow", "ApplyStep", "default_handler_chain"]
