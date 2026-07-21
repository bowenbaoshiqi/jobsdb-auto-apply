"""
完整 Cookie 提取 + E2E 测试

使用 browser_cookie3 提取 Chrome 中完整的 cookie 属性，
保留 domain、path、secure、httpOnly 等信息。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import BrowserConfig
from src.browser.engine import BrowserEngine
from src.jobsdb.homepage import HomepageScraper
from src.simulation.behavior import HumanSimulator


def extract_full_cookies():
    """从 Chrome 提取完整的 cookies（包含 domain、path 等属性）"""
    try:
        import browser_cookie3
        cj = browser_cookie3.chrome()

        # 筛选目标域名的 cookies
        target_domains = ["jobsdb.com", "seek.com"]
        cookies = []

        for cookie in cj:
            if any(dom in cookie.domain for dom in target_domains):
                # 转换为 Playwright 格式
                pw_cookie = {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": cookie.secure,
                    "httpOnly": getattr(cookie, 'rest', {}).get('HttpOnly', False),
                }

                # 处理 expires / max-age
                if cookie.expires:
                    from datetime import datetime
                    if cookie.expires > datetime.now().timestamp():
                        pw_cookie["expires"] = int(cookie.expires)
                    else:
                        # 已过期，跳过
                        continue
                else:
                    pw_cookie["expires"] = -1

                # sameSite
                samesite = getattr(cookie, '_rest', {}).get('SameSite', '')
                if samesite:
                    pw_cookie["sameSite"] = samesite
                else:
                    pw_cookie["sameSite"] = "Lax" if not cookie.secure else "None"

                cookies.append(pw_cookie)

        print(f"✓ 提取到 {len(cookies)} 个完整 cookies")
        return cookies

    except Exception as e:
        print(f"✗ 提取失败: {e}")
        return []


async def test_e2e_full_cookies():
    """使用完整 cookie 进行 E2E 测试"""
    print("=" * 60)
    print("JobsDB HK E2E 测试 — 完整 Cookie 复用")
    print("=" * 60)
    print()

    # 提取 cookies
    print("🔍 从 Chrome 提取完整 cookies...")
    cookies = extract_full_cookies()

    if not cookies:
        print("❌ 未提取到 cookies")
        return

    # 展示关键认证 cookies
    auth_cookies = [c for c in cookies if "auth" in c["name"].lower() or "session" in c["name"].lower()]  # noqa: E501
    print(f"   其中认证相关: {len(auth_cookies)} 个")
    for c in auth_cookies[:3]:
        print(f"   - {c['name']}: {c['value'][:20]}... ({c['domain']})")
    print()

    # 启动浏览器
    config = BrowserConfig(
        headless=False,
        window_width=1920,
        window_height=1080,
        user_data_dir="./data/browser_profile_cookies",
        locale="zh-HK",
        timezone_id="Asia/Hong_Kong",
    )

    engine = BrowserEngine(config)

    try:
        print("🚀 启动浏览器...")
        page = await engine.start()
        print("✓ 浏览器已启动")

        # 注入 cookies
        if engine.context:
            try:
                await engine.context.add_cookies(cookies)
                print(f"✓ 已注入 {len(cookies)} 个 cookies")
            except Exception as e:
                print(f"⚠️ 注入部分 cookies 失败: {e}")

        # 访问 JobsDB
        print("\n🌐 访问 hk.jobsdb.com...")
        await page.goto("https://hk.jobsdb.com/", wait_until="domcontentloaded")
        await asyncio.sleep(5)

        print(f"   当前 URL: {page.url[:80]}...")
        print(f"   页面标题: {await page.title()}")

        # 检查是否被重定向到登录页
        if "login" in page.url.lower() or "seek.com" in page.url.lower():
            print("\n⚠️  被重定向到登录页 — Cookie 未保持登录")
            print("可能原因：")
            print("  1. Chrome 正在运行，cookies 已过期/被锁定")
            print("  2. 需要在 Chrome 中保持 JobsDB 标签页打开")
            print("  3. JobsDB 检测到不同浏览器指纹")
            print()
            print("建议：")
            print("  1. 在 Chrome 中打开 https://hk.jobsdb.com/ 确保已登录")
            print("  2. 重新运行此脚本")
            return

        # 检查登录元素
        print("\n🔐 检查登录状态...")
        is_logged_in = False

        # 方法1: 查找个人资料相关元素
        for selector in ['a[href*="profile"]', '[data-automation="user-avatar"]', 'img[alt*="profile"]']:  # noqa: E501
            try:
                elem = await page.query_selector(selector)
                if elem and await elem.is_visible():
                    is_logged_in = True
                    print(f"✅ 检测到登录元素: {selector}")
                    break
            except Exception:
                pass

        # 方法2: 检查页面文本
        if not is_logged_in:
            text = await page.text_content("body")
            if "Sign in" not in text and "Log in" not in text and "登入" not in text:
                is_logged_in = True
                print("✅ 页面无登录按钮，推测已登录")

        if not is_logged_in:
            print("\n❌ 未检测到登录状态")
            print("如果 Chrome 中是登录的但这里没有，可能是因为：")
            print("  - Chrome 正在运行，cookies 被文件锁锁定")
            print("  - Playwright 的 Chromium 版本与 Chrome 差异导致 session 不兼容")
            print()
            print("解决方案：尝试直接用 Chrome 的完整 profile:")
            print("  python tests/test_e2e_chrome_profile.py")
            return

        print("\n🎉 登录状态确认！")
        print()

        # 抓取推荐职位
        print("🔍 抓取首页推荐职位...")
        scraper = HomepageScraper(page, HumanSimulator(page))
        jobs = await scraper.get_recommended_jobs(max_jobs=20)

        print(f"✅ 抓取完成！共找到 {len(jobs)} 个职位")
        if jobs:
            print("\n-" * 60)
            for i, job in enumerate(jobs[:10], 1):
                print(f"{i}. {job.title} @ {job.company}")
                if job.location:
                    print(f"   📍 {job.location} | 💰 {job.salary or 'N/A'}")
            print("-" * 60)

        print("\n✅ E2E 测试完成！")
        await asyncio.sleep(10)

    except KeyboardInterrupt:
        print("\n⛔ 用户中断")
    except Exception as e:
        logger.exception(f"异常: {e}")
        print(f"\n❌ 异常: {e}")
    finally:
        if engine:
            await engine.stop()
            print("✓ 浏览器已关闭")


if __name__ == "__main__":
    try:
        asyncio.run(test_e2e_full_cookies())
    except Exception as e:
        print(f"\n💥 错误: {e}")
        import traceback
        traceback.print_exc()
