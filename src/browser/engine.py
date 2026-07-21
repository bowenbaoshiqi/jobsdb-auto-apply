"""
浏览器引擎 — Playwright 生命周期管理和 Stealth 配置
"""

from pathlib import Path
from typing import Optional

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from config.settings import BrowserConfig, get_config
from src.browser.stealth import get_combined_script
from src.storage.cookies import CookieStore


class BrowserEngine:
    """
    Playwright 浏览器引擎

    负责：
    1. 启动/停止浏览器
    2. 配置反指纹 stealth patches
    3. 管理持久化 profile（按账户隔离）
    4. Cookie/Session 持久化
    """

    def __init__(self, config: Optional[BrowserConfig] = None,
                 account_alias: str = "default"):
        self.config = config or get_config().browser
        self.account_alias = account_alias
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.cookie_store = CookieStore(
            f"./data/cookies_{account_alias}.json"
        )

    async def start(self) -> Page:
        """
        启动浏览器并返回主页面

        Returns:
            Playwright Page 对象
        """
        logger.info("Starting browser engine...")

        self.playwright = await async_playwright().start()

        # 浏览器启动参数
        browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            f"--window-size={self.config.window_width},{self.config.window_height}",
        ]

        # 有头模式下的额外参数
        if not self.config.headless:
            browser_args.extend([
                "--disable-gpu",
            ])
        else:
            # 无头模式需要更多伪装
            browser_args.extend([
                "--headless=new",  # Chrome 109+ 的新无头模式
            ])

        # 准备用户数据目录（持久化 profile）按账户隔离
        base_dir = Path(self.config.user_data_dir)
        user_data_dir = base_dir / self.account_alias
        user_data_dir.mkdir(parents=True, exist_ok=True)

        # 启动浏览器（使用 persistent context）
        # 使用 channel='chromium' 指向系统 Chromium，避免 Playwright bundled chromium 崩溃
        self.browser = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=self.config.headless,
            channel="chromium",
            args=browser_args,
            locale=self.config.locale,
            timezone_id=self.config.timezone_id,
            viewport={
                "width": self.config.viewport["width"],
                "height": self.config.viewport["height"],
            },
            geolocation=self.config.geolocation,
            permissions=["geolocation"] if self.config.geolocation else [],
            proxy={"server": self.config.proxy} if self.config.proxy else None,
            bypass_csp=True,
            java_script_enabled=True,
        )

        # launch_persistent_context 返回的是 BrowserContext
        self.context = self.browser

        # 获取默认 page
        pages = self.browser.pages
        self.page = pages[0] if pages else await self.browser.new_page()

        # 应用 stealth patches（关键！）
        await self._apply_stealth_patches()

        # 加载 cookies
        await self._load_cookies()

        logger.info("Browser engine started successfully")
        return self.page

    async def stop(self) -> None:
        """停止浏览器并保存 cookies"""
        logger.info("Stopping browser engine...")

        try:
            if self.page and not self.page.is_closed():
                # 保存 cookies
                await self._save_cookies()
                await self.page.close()
        except Exception as e:
            logger.warning(f"Error during page cleanup: {e}")

        try:
            if self.browser:
                await self.browser.close()
        except Exception as e:
            logger.warning(f"Error during browser cleanup: {e}")

        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.warning(f"Error during playwright cleanup: {e}")

        logger.info("Browser engine stopped")

    async def new_page(self) -> Page:
        """创建新标签页（自动注入 stealth）"""
        if not self.browser:
            raise RuntimeError("Browser not started")

        page = await self.browser.new_page()
        await self._apply_stealth_to_page(page)
        return page

    async def _apply_stealth_patches(self) -> None:
        """对所有已有页面应用 stealth patches"""
        if not self.browser:
            return

        for page in self.browser.pages:
            await self._apply_stealth_to_page(page)

    async def _apply_stealth_to_page(self, page: Page) -> None:
        """对单个页面应用 stealth patches"""
        try:
            combined_script = get_combined_script()
            await page.add_init_script(combined_script)
            logger.debug(f"Stealth patches applied to page: {page.url[:50]}")
        except Exception as e:
            logger.error(f"Failed to apply stealth patches: {e}")

    async def _load_cookies(self) -> None:
        """从文件加载 cookies"""
        if not self.page:
            return

        cookies = self.cookie_store.load()
        if cookies:
            # 确保 cookies 格式正确
            valid_cookies = []
            for cookie in cookies:
                # Playwright 期望特定格式
                valid_cookie = {
                    "name": cookie.get("name", ""),
                    "value": cookie.get("value", ""),
                    "domain": cookie.get("domain", ""),
                    "path": cookie.get("path", "/"),
                    "expires": cookie.get("expires", -1),
                    "httpOnly": cookie.get("httpOnly", False),
                    "secure": cookie.get("secure", False),
                    "sameSite": cookie.get("sameSite", "Lax"),
                }
                valid_cookies.append(valid_cookie)

            try:
                await self.context.add_cookies(valid_cookies)
                logger.debug(f"Loaded {len(valid_cookies)} cookies")
            except Exception as e:
                logger.warning(f"Failed to load cookies: {e}")

    async def _save_cookies(self) -> None:
        """保存 cookies 到文件"""
        if not self.context:
            return

        try:
            cookies = await self.context.cookies()
            self.cookie_store.save(cookies)
            logger.debug(f"Saved {len(cookies)} cookies")
        except Exception as e:
            logger.warning(f"Failed to save cookies: {e}")

    async def restart(self) -> Page:
        """重启浏览器"""
        logger.info("Restarting browser...")
        await self.stop()
        return await self.start()

    async def goto(self, url: str, wait_until: str = "networkidle") -> None:
        """
        导航到指定 URL

        Args:
            url: 目标 URL
            wait_until: 等待条件 (load/domcontentloaded/networkidle)
        """
        if not self.page:
            raise RuntimeError("Browser not started")

        logger.debug(f"Navigating to {url}")
        await self.page.goto(url, wait_until=wait_until)

    @property
    def current_page(self) -> Optional[Page]:
        """获取当前页面"""
        return self.page
