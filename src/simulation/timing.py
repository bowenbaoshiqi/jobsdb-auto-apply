"""
时序模块 — 人类行为时间分布

核心：
- 所有延迟使用高斯（正态）分布，而非均匀分布
- 人类反应的 timing 是有模式的：集中在某个均值附近，偶尔偏快或偏慢
- 不同操作类型有不同的时序特征
"""

import asyncio
import random
from enum import Enum
from typing import Optional

import numpy as np


class HumanActionType(str, Enum):
    """人类操作类型"""
    PAGE_LOAD = "page_load"          # 页面加载等待
    CLICK = "click"                  # 点击后停顿
    SCROLL = "scroll"                # 滚动后看内容
    FORM_FILL = "form_fill"          # 填表思考时间
    READ_CONTENT = "read_content"    # 阅读内容
    SUBMIT_WAIT = "submit_wait"      # 提交后等待响应
    BETWEEN_JOBS = "between_jobs"    # 职位之间切换
    TYPING_PAUSE = "typing_pause"    # 打字间隙小停顿
    HOVER = "hover"                  # 鼠标悬停


# 每种操作类型的时序特征（均值秒数, 标准差秒数）
ACTION_TIMING = {
    HumanActionType.PAGE_LOAD: (2.5, 1.0),        # 2.5s ± 1s
    HumanActionType.CLICK: (0.4, 0.2),            # 0.4s ± 0.2s
    HumanActionType.SCROLL: (0.8, 0.4),           # 0.8s ± 0.4s
    HumanActionType.FORM_FILL: (1.0, 0.5),        # 1.0s ± 0.5s
    HumanActionType.READ_CONTENT: (3.5, 1.5),     # 3.5s ± 1.5s
    HumanActionType.SUBMIT_WAIT: (2.0, 0.8),      # 2.0s ± 0.8s
    HumanActionType.BETWEEN_JOBS: (5.0, 2.0),     # 5s ± 2s
    HumanActionType.TYPING_PAUSE: (0.05, 0.02),   # 50ms ± 20ms
    HumanActionType.HOVER: (0.3, 0.15),           # 0.3s ± 0.15s
}


def human_delay(action_type: HumanActionType,
                mean_override: Optional[float] = None,
                std_override: Optional[float] = None,
                min_delay: float = 0.05) -> float:
    """
    生成人类行为的延迟时间

    Args:
        action_type: 操作类型
        mean_override: 覆盖均值（秒）
        std_override: 覆盖标准差（秒）
        min_delay: 最小延迟（秒）

    Returns:
        延迟秒数
    """
    mean, std = ACTION_TIMING.get(action_type, (1.0, 0.5))

    if mean_override is not None:
        mean = mean_override
    if std_override is not None:
        std = std_override

    # 高斯分布采样
    delay = np.random.normal(mean, std)

    # 极低概率的超长停顿（模拟"走神"）
    if random.random() < 0.02:  # 2%
        delay *= random.uniform(2.0, 4.0)

    return max(min_delay, delay)


async def wait_human(action_type: HumanActionType,
                     mean_override: Optional[float] = None,
                     std_override: Optional[float] = None) -> None:
    """
    等待一段人类行为时间

    Args:
        action_type: 操作类型
        mean_override: 覆盖均值
        std_override: 覆盖标准差
    """
    delay = human_delay(action_type, mean_override, std_override)
    await asyncio.sleep(delay)


def randomize_session_timing(base_applies: int = 10) -> list:
    """
    为一次 session 生成随机化的投递时间间隔

    真实人类不会在固定间隔投递，而是：
    - 有时连续看几个职位
    - 有时走开休息一会儿
    - 有时仔细读 JD 花更长时间
    """
    intervals = []
    for _i in range(base_applies - 1):
        # 基础间隔 3-7 分钟
        base = random.uniform(180, 420)

        # 20% 概率添加一个"休息"间隔（5-10分钟）
        if random.random() < 0.2:
            base += random.uniform(300, 600)

        # 5% 概率添加一个"长休息"（10-15分钟）
        if random.random() < 0.05:
            base += random.uniform(600, 900)

        intervals.append(base)

    return intervals


def is_peak_hour(tz_str: str = "Asia/Hong_Kong") -> bool:
    """
    检查当前是否是香港高峰时段
    """
    from datetime import datetime

    import pytz

    try:
        tz = pytz.timezone(tz_str)
        now = datetime.now(tz)
        hour = now.hour

        # 排除高峰时段：9-11点，14-16点
        peak_periods = [(9, 11), (14, 16)]
        return any(start <= hour < end for start, end in peak_periods)
    except Exception:
        # 如果 pytz 不可用，使用本地时间估算
        now = datetime.now()
        hour = now.hour
        peak_periods = [(9, 11), (14, 16)]
        return any(start <= hour < end for start, end in peak_periods)


def get_optimal_delay() -> float:
    """
    获取当前最佳等待时间

    高峰时段等待更久，非高峰时段可以稍快
    """
    if is_peak_hour():
        # 高峰时段：更保守
        return random.uniform(240, 480)  # 4-8 分钟
    else:
        # 非高峰时段：可稍快
        return random.uniform(180, 360)  # 3-6 分钟
