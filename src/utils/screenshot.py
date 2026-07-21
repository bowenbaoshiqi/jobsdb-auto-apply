import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from src.browser.ports.page_controller import PageController


async def capture_screenshot(page: PageController,
                             filename: Optional[str] = None,
                             screenshots_dir: str = "./data/screenshots") -> str:
    """
    截取当前页面截图

    Args:
        page: PageController(任意实现)
        filename: 文件名（不含路径），默认使用时间戳
        screenshots_dir: 截图保存目录

    Returns:
        截图文件的完整路径
    """
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"screenshot_{timestamp}.png"

    screenshots_path = Path(screenshots_dir)
    screenshots_path.mkdir(parents=True, exist_ok=True)

    filepath = screenshots_path / filename

    try:
        await page.screenshot(path=str(filepath), full_page=True)
        logger.debug(f"Screenshot saved to {filepath}")
        return str(filepath)
    except Exception as e:
        logger.error(f"Failed to capture screenshot: {e}")
        return ""


async def save_page_html(page: PageController,
                         filename: Optional[str] = None,
                         data_dir: str = "./data") -> str:
    """
    保存当前页面 HTML 内容

    Args:
        page: PageController(任意实现)
        filename: 文件名（不含路径），默认使用时间戳
        data_dir: HTML 保存目录

    Returns:
        HTML 文件的完整路径
    """
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"page_{timestamp}.html"

    html_path = Path(data_dir) / "html"
    html_path.mkdir(parents=True, exist_ok=True)

    filepath = html_path / filename

    try:
        html_content = await page.content()
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.debug(f"HTML saved to {filepath}")
        return str(filepath)
    except Exception as e:
        logger.error(f"Failed to save HTML: {e}")
        return ""


def generate_session_id(account_alias: str = "") -> str:
    """生成唯一会话 ID（可按账户前缀隔离）"""
    import uuid
    suffix = uuid.uuid4().hex[:12]
    if account_alias:
        return f"{account_alias}_{suffix}"
    return suffix
