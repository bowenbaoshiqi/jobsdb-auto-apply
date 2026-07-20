"""
JobsDB HK — 自动检测登录 + Session 保存

不需要 input()！流程：
1. 浏览器弹出来，你手动在浏览器里登录
2. 脚本每 3 秒自动检查登录状态
3. 检测到登录成功后自动保存 session
4. 抓取职位验证

运行：
    conda activate jobsdb
    python tests/test_e2e_auto_detect.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import BrowserConfig
from src.browser.engine import BrowserEngine
from src.jobsdb.homepage import HomepageScraper
from src.simulation.behavior import HumanSimulator


async def is_logged_in(page) -> bool:
    """检查页面是否已登录"""
    # 方法1: 查找用户相关元素
    for selector in [
        'a[href*="profile"]',
        '[data-automation="user-avatar"]',
        'img[alt*="profile"]',
    ]:
        try:
            elem = await page.query_selector(selector)
            if elem and await elem.is_visible():
                return True
        except:
            pass

    # 方法2: URL 不包含 login
    url = page.url
    if "login" not in url.lower() and "seek.com" not in url.lower():
        return True

    return False


async def auto_login_and_save():
    print("=" * 60)
    print("JobsDB HK — 自动检测登录 + Session 保存")
    print("=" * 60)
    print()

    config = BrowserConfig(
        headless=False,
        window_width=1920,
        window_height=1080,
        user_data_dir="./data/browser_profile_manual",
        locale="zh-HK",
        timezone_id="Asia/Hong_Kong",
    )

    engine = BrowserEngine(config)
    page = None

    try:
        print("🚀 启动浏览器...")
        page = await engine.start()
        print("✓ 浏览器已启动\n")

        # 访问 JobsDB
        print("🌐 访问 hk.jobsdb.com...")
        await page.goto("https://hk.jobsdb.com/", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        print()
        print("-" * 60)
        print("📱 请在浏览器窗口中完成登录：")
        print()
        print("   1. 点击 'Sign in' / 'Log in'")
        print("   2. 输入邮箱: your-email@example.com")
        print("   3. 接收验证码并输入")
        print("   4. 完成登录")
        print()
        print("   ⏳ 脚本每 3 秒自动检测登录状态...")
        print("   ✅ 检测登录成功后会自动继续")
        print("-" * 60)
        print()

        # 轮询检测登录状态（最多 5 分钟）
        max_wait = 300  # 5 分钟
        checked = 0
        logged_in = False

        while checked < max_wait:
            await asyncio.sleep(3)
            checked += 3

            logged_in = await is_logged_in(page)

            if logged_in:
                print(f"✅ 检测到登录成功！（等待了 {checked} 秒）")
                break
            else:
                # 每 15 秒打印一次提示
                if checked % 15 == 0:
                    print(f"   ... 仍在等待登录 ({checked}s / {max_wait}s)")

        if not logged_in:
            print("\n⏰ 等待超时（5 分钟），未检测到登录")
            return

        # 等待页面稳定
        print("\n💤 等待页面稳定...")
        await asyncio.sleep(3)

        # 保存 session
        print("\n💾 保存 session 数据...")

        # Cookies
        cookies = await engine.context.cookies()
        cookies_path = Path("./data/playwright_cookies.json")
        cookies_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cookies_path, "w") as f:
            json.dump(cookies, f, indent=2)
        print(f"✓ Cookies: {cookies_path} ({len(cookies)} 个)")

        # localStorage
        ls = await page.evaluate("() => JSON.stringify(localStorage)")
        ls_path = Path("./data/playwright_localstorage.json")
        with open(ls_path, "w") as f:
            f.write(ls)
        print(f"✓ LocalStorage: {ls_path}")

        # 抓取测试
        print("\n🔍 抓取首页推荐职位验证...")
        scraper = HomepageScraper(page, HumanSimulator(page))

        try:
            jobs = await scraper.get_recommended_jobs(max_jobs=10)
            print(f"✅ 抓取成功！{len(jobs)} 个职位")

            if jobs:
                print("\n-" * 50)
                for i, job in enumerate(jobs[:5], 1):
                    print(f"{i}. {job.title}")
                    print(f"   🏢 {job.company} | 📍 {job.location or 'N/A'}")
                print("-" * 50)
        except Exception as e:
            print(f"⚠️  抓取测试失败: {e}")

        print("\n" + "=" * 60)
        print("✅ Session 保存完成！")
        print("=" * 60)
        print("\n📋 下次运行:")
        print("   python tests/test_e2e_save_session.py")

    except KeyboardInterrupt:
        print("\n\n⛔ 中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if page and not page.is_closed():
            print("\n等待 5 秒后关闭...")
            await asyncio.sleep(5)
        if engine:
            await engine.stop()
            print("✓ 浏览器已关闭")


if __name__ == "__main__":
    try:
        asyncio.run(auto_login_and_save())
    except KeyboardInterrupt:
        print("\n\n⛔ 中断")
    except Exception as e:
        print(f"\n💥 致命错误: {e}")
        import traceback
        traceback.print_exc()
