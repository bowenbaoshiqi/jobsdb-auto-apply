"""
职位详情页处理
"""

import asyncio
from typing import Optional

from loguru import logger

from src.browser.ports.page_controller import PageController
from src.jobsdb.exceptions import JobNotFoundError
from src.jobsdb.selectors import (
    ALREADY_APPLIED_BADGE,
    APPLY_BUTTON,
    EASY_APPLY_BUTTON,
    JOB_DESCRIPTION,
    JOB_DETAIL_COMPANY,
    JOB_DETAIL_LOCATION,
    JOB_DETAIL_SALARY,
    JOB_DETAIL_TITLE,
    QUICK_APPLY_BUTTON,
)
from src.simulation.behavior import HumanSimulator
from src.utils.screenshot import capture_screenshot


class JobDetailPage:
    """职位详情页处理器"""

    def __init__(self, page: PageController, job_url: Optional[str] = None,
                 human: Optional[HumanSimulator] = None):
        self.page = page
        self.job_url = job_url
        self.human = human

    async def navigate_with_simulation(self, job_url: Optional[str] = None) -> None:
        """
        模拟人类行为导航到职位详情页

        Args:
            job_url: 职位详情页 URL（如果构造时已提供则不需要）
        """
        url = job_url or self.job_url
        if not url:
            raise ValueError("Job URL not provided")

        logger.info(f"Navigating to job detail: {url[:60]}...")

        # 导航
        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)  # 等页面初始加载

        # 模拟人类浏览行为
        if self.human:
            await self.human.view_job_detail()
        else:
            # 基础等待
            await asyncio.sleep(2)

        # 检查页面是否加载成功
        title = await self._get_job_title()
        if not title:
            logger.warning("Job title not found, page may have failed to load")
            await capture_screenshot(self.page, "job_detail_error")
            raise JobNotFoundError(f"Failed to load job detail page: {url}")

        logger.debug(f"Loaded job: {title}")

    async def is_already_applied(self) -> bool:
        """检查是否已经投递过该职位"""
        try:
            badge = await self.page.query_selector(ALREADY_APPLIED_BADGE)
            if badge:
                return True

            # 备选：检查按钮文本
            apply_btn = await self.page.query_selector(APPLY_BUTTON)
            if apply_btn:
                text = await apply_btn.text_content()
                if text and "applied" in text.lower():
                    return True

            return False
        except Exception:
            return False

    async def get_apply_button(self):
        """获取 Quick Apply 按钮(只投一键申请的职位)

        v2.0 决策(2026-07-22,e2e 暴露):用户只要 Quick Apply 的职位。
        标准 "Apply"/"Apply now" 按钮常跳外部站点或需手动填长表,不在自动投递范围。
        旧版把标准 APPLY_BUTTON/APPLY_NOW_BUTTON 也算进来 → 找到后点不动 → 误判失败。
        现在只认 QUICK_APPLY_BUTTON / EASY_APPLY_BUTTON;两者都没有则返回 None,
        由 orchestrator 判为 SKIPPED(not_quick_apply),不计入连续失败。

        尝试多种选择器(quick/easy apply 有多种 DOM 变体)。
        """
        selectors = [
            QUICK_APPLY_BUTTON,
            EASY_APPLY_BUTTON,
        ]

        for selector in selectors:
            btn = await self.page.query_selector(selector)
            if btn:
                # 确认按钮是可见且可点击的
                is_visible = await btn.is_visible()
                if is_visible:
                    return btn

        return None

    async def get_job_info(self) -> dict:
        """获取职位详细信息"""
        info = {
            "title": "",
            "company": "",
            "location": "",
            "salary": "",
            "description": "",
        }

        try:
            # 标题
            title_el = await self.page.query_selector(JOB_DETAIL_TITLE)
            if title_el:
                info["title"] = await title_el.text_content() or ""

            # 公司
            company_el = await self.page.query_selector(JOB_DETAIL_COMPANY)
            if company_el:
                info["company"] = await company_el.text_content() or ""

            # 地点
            location_el = await self.page.query_selector(JOB_DETAIL_LOCATION)
            if location_el:
                info["location"] = await location_el.text_content() or ""

            # 薪资
            salary_el = await self.page.query_selector(JOB_DETAIL_SALARY)
            if salary_el:
                info["salary"] = await salary_el.text_content() or ""

            # 描述（可选）
            desc_el = await self.page.query_selector(JOB_DESCRIPTION)
            if desc_el:
                info["description"] = await desc_el.text_content() or ""

        except Exception as e:
            logger.warning(f"Error getting job info: {e}")

        return info

    async def _get_job_title(self) -> Optional[str]:
        """获取职位标题

        v2.0: `except Exception: pass` → 捕获 + debug 日志
        (三分法 B 类:降级 — 标题取不到返回 None,不阻断)。
        """
        try:
            title_el = await self.page.query_selector(JOB_DETAIL_TITLE)
            if title_el:
                return await title_el.text_content()
        except Exception as e:
            logger.debug(f"Failed to get job title: {e}")
        return None
