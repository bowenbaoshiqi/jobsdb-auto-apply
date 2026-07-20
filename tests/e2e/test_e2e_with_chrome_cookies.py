"""
从 Chrome 提取 jobsdb.com 的 cookies 并注入到 Playwright

原理：
1. 用 pycookiecheat 读取 macOS Chrome 加密 cookies
2. 格式转换为 Playwright 接受的格式
3. 启动浏览器时直接加载这些 cookies
4. 访问 jobsdb.com/hk 应该已是登录状态

使用方法：
    conda activate jobsdb
    python tests/test_e2e_with_chrome_cookies.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import BrowserConfig
from src.browser.engine import BrowserEngine
from src.jobsdb.homepage import HomepageScraper
from src.simulation.behavior import HumanSimulator
from src.storage.cookies import CookieStore


def extract_chrome_cookies(domains: list = None):
    """从 Chrome 提取多个域名的 cookies"""
    if domains is None:
        domains = ["hk.jobsdb.com", "login.seek.com"]

    all_cookies = {}
    from pycookiecheat import chrome_cookies

    for domain in domains:
        try:
            cookies = chrome_cookies(domain)
            print(f"✓ 从 Chrome 提取到 {len(cookies)} 个 cookies for {domain}")
            all_cookies.update(cookies)
        except Exception as e:
            print(f"⚠️ 提取 {domain} cookies 失败: {e}")

    return all_cookies


def convert_to_playwright_cookies(cookie_dict: dict):
    """将 pycookiecheat 的 cookie dict 转换为 Playwright 格式"""
    pw_cookies = []
    for name, value in cookie_dict.items():
        # Playwright cookie 格式
        pw_cookie = {
            "name": name,
            "value": value,
            "domain": ".jobsdb.com",
            "path": "/",
            "expires": -1,
            "httpOnly": False,
            "secure": True,
            "sameSite": "Lax",
        }
        pw_cookies.append(pw_cookie)
    return pw_cookies


async def test_e2e_with_chrome_session():
    """
    使用 Chrome 已有 session 进行 E2E 测试
    """
    print("=" * 60)
    print("JobsDB HK E2E 测试 — Chrome Session 复用")
    print("=" * 60)
    print()

    # Step 1: 从 Chrome 提取 cookies
    print("🔍 从 Chrome 提取 jobsdb.com cookies...")
    chrome_cookies = extract_chrome_cookies("hk.jobsdb.com")

    if not chrome_cookies:
        print("\n❌ 未找到 jobsdb.com 的 cookies")
        print("可能原因：")
        print("  1. 你尚未在 Chrome 中登录 JobsDB")
        print("  2. Chrome 没有记住登录状态")
        print("  3. macOS 钥匙串权限问题")
        print()
        print("请先在 Chrome 中访问 https://www.jobsdb.com/hk 并登录，")
        print("然后重新运行此脚本。")
        return

    # Step 2: 转换为 Playwright 格式并保存
    pw_cookies = convert_to_playwright_cookies(chrome_cookies)

    # 先保存到项目 cookie 文件
    cookie_store = CookieStore("./data/cookies_chrome.json")
    cookie_store.save(pw_cookies)
    print(f"💾 已保存 {len(pw_cookies)} 个 cookies 到 data/cookies_chrome.json")

    # Step 3: 启动浏览器并加载 cookies
    print("\n🚀 启动 Playwright 浏览器...")
    browser_config = BrowserConfig(
        headless=False,  # headed 模式方便观察
        window_width=1920,
        window_height=1080,
        user_data_dir="./data/browser_profile_chrome",
        locale="zh-HK",
        timezone_id="Asia/Hong_Kong",
    )

    engine = BrowserEngine(browser_config)

    try:
        page = await engine.start()
        print("✓ 浏览器已启动")

        # 加载 Chrome 的 cookies
        if engine.context:
            try:
                await engine.context.add_cookies(pw_cookies)
                print(f"✓ 已注入 {len(pw_cookies)} 个 cookies")
            except Exception as e:
                print(f"⚠️ 注入 cookies 时出错: {e}")

        # Step 4: 访问 JobsDB 并验证登录状态
        print("\n🌐 访问 hk.jobsdb.com...")
        await page.goto("https://hk.jobsdb.com/", wait_until="domcontentloaded")
        await asyncio.sleep(3)  # 等页面加载

        # 检查登录状态
        print("🔐 检查登录状态...")

        # 方法1: 检查是否有用户头像/用户名
        avatar_selectors = [
            '[data-automation="user-avatar"]',
            'a[href*="profile"]',
            'img[alt*="profile"]',
        ]

        is_logged_in = False
        for selector in avatar_selectors:
            try:
                elem = await page.query_selector(selector)
                if elem and await elem.is_visible():
                    is_logged_in = True
                    text = await elem.text_content() or ""
                    print(f"✅ 检测到登录状态元素: {selector[:40]}... ({text[:30]})")
                    break
            except:
                pass

        # 方法2: 检查页面文本
        if not is_logged_in:
            page_text = await page.text_content("body")
            login_indicators = ["Sign in", "Log in", "登入", "登录"]
            has_login_link = any(indicator in page_text for indicator in login_indicators)

            if not has_login_link:
                is_logged_in = True
                print("✅ 页面无登录按钮，推测已登录")
            else:
                print("⚠️ 页面仍有登录按钮，可能未登录")

        if not is_logged_in:
            print("\n❌ Cookie 复用失败，仍然显示未登录")
            print("可能原因：")
            print("  1. Chrome cookies 已过期")
            print("  2. JobsDB 检测到不同浏览器指纹，拒绝 cookie")
            print("  3. Cookie 域匹配问题（.jobsdb.com vs www.jobsdb.com）")
            print()
            print("请尝试刷新 Chrome 中的 JobsDB 页面确保登录状态最新，")
            print("然后关闭 Chrome 再运行此脚本。")

            # 截图供分析
            screenshot_path = Path("data/screenshots/cookie_transfer_failed.png")
            await page.screenshot(path=str(screenshot_path))
            print(f"📸 截图已保存: {screenshot_path}")
            return

        # Step 5: 抓取首页推荐职位
        print("\n🔍 开始抓取首页推荐职位...")
        human = HumanSimulator(page)
        scraper = HomepageScraper(page, human)

        try:
            jobs = await scraper.get_recommended_jobs(max_jobs=20)
        except Exception as e:
            logger.error(f"抓取失败: {e}")
            print(f"\n❌ 抓取失败: {e}")
            return

        print(f"✅ 抓取完成！共找到 {len(jobs)} 个职位")
        print()

        # 展示结果
        if jobs:
            print("-" * 60)
            print(f"{'#':<4} {'职位标题':<35} {'公司':<20}")
            print("-" * 60)
            for i, job in enumerate(jobs[:10], 1):
                title = job.title[:32] + "..." if len(job.title) > 35 else job.title
                company = job.company[:17] + "..." if len(job.company) > 20 else job.company
                print(f"{i:<4} {title:<35} {company:<20}")
            print("-" * 60)

            if len(jobs) > 10:
                print(f"... 还有 {len(jobs) - 10} 个职位未显示")
            print()
        else:
            print("⚠️ 没有找到推荐职位")
            print("可能：新账号无推荐、需要完善资料、页面结构变化")

        print("=" * 60)
        print("✅ E2E 测试完成！")
        print("=" * 60)

        # 保持浏览器打开几秒供观察
        print("\n等待 10 秒后关闭浏览器...")
        await asyncio.sleep(10)

    except Exception as e:
        logger.exception(f"E2E 测试异常: {e}")
        print(f"\n❌ 测试异常: {e}")
    finally:
        if engine:
            await engine.stop()
            print("✓ 浏览器已关闭")


if __name__ == "__main__":
    try:
        asyncio.run(test_e2e_with_chrome_session())
    except KeyboardInterrupt:
        print("\n\n⛔ 用户中断")
    except Exception as e:
        print(f"\n💥 致命错误: {e}")
        import traceback
        traceback.print_exc()
