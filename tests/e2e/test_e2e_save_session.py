"""
手动登录 + Session 保存 — 最可靠的方案

流程：
1. 启动可见浏览器访问 hk.jobsdb.com
2. 你手动在浏览器中处理验证码登录
3. 登录成功后，按 Enter 告诉脚本
4. 脚本保存 cookies + localStorage 到文件
5. 自动抓取首页推荐职位验证

下次运行可以从第4步开始，直接复用 session。
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


async def manual_login_and_save_session():
    """
    手动登录流程 — 一次登录，永久复用
    """
    print("=" * 60)
    print("JobsDB HK — 手动登录 + Session 保存")
    print("=" * 60)
    print()

    session_file = Path("./data/playwright_session.json")

    # 检查是否已有保存的 session
    if session_file.exists():
        print("💾 发现已保存的 session，尝试复用...")
        # 询问是否重新登录
        try:
            choice = input("   按 Enter 复用 session，输入 'new' 重新登录: ").strip()
        except EOFError:
            choice = ""

        if choice.lower() != 'new':
            print("✓ 将复用已保存的 session")
            await run_with_saved_session()
            return

    # Step 1: 启动可见浏览器
    print("🚀 启动浏览器（可见模式）...")
    print("   请稍候，浏览器窗口即将弹出...")
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
        page = await engine.start()
        print("✓ 浏览器已启动")
        print()

        # Step 2: 访问 JobsDB
        print("🌐 访问 hk.jobsdb.com...")
        await page.goto("https://hk.jobsdb.com/", wait_until="domcontentloaded")
        await asyncio.sleep(3)

        print()
        print("-" * 60)
        print("📱 请在浏览器窗口中完成以下操作：")
        print()
        print("   1. 点击页面右上角的 'Sign in' 或 'Log in'")
        print("   2. 输入你的邮箱: your-email@example.com")
        print("   3. 接收验证码并输入")
        print("   4. 完成登录，看到个人资料页/头像")
        print()
        print("   ⚠️  如果弹出验证码图片，请在浏览器中手动选择")
        print("   ⚠️  如果遇到其他验证，请按页面提示操作")
        print()
        print("-" * 60)

        # Step 3: 等待用户完成登录
        try:
            input("\n🛑 登录完成后，请按 Enter 继续...")
        except EOFError:
            # 非交互环境，等待固定时间
            print("\n非交互环境，等待 60 秒供登录...")
            await asyncio.sleep(60)

        print()
        print("🔐 验证登录状态...")
        await asyncio.sleep(2)

        # Step 4: 检查是否登录成功
        is_logged_in = False

        # 方法1: 检查 profile 链接
        for selector in ['a[href*="profile"]', '[data-automation="user-avatar"]', 'img[alt*="profile"]']:  # noqa: E501
            try:
                elem = await page.query_selector(selector)
                if elem and await elem.is_visible():
                    is_logged_in = True
                    print(f"✅ 检测到登录元素: {selector}")
                    break
            except Exception:
                pass

        # 方法2: URL 检查
        current_url = page.url
        if "login" not in current_url.lower():
            print(f"✅ 当前 URL: {current_url[:60]}...")
            is_logged_in = True

        if not is_logged_in:
            print("\n❌ 未检测到登录状态")
            print("请确认：")
            print("  1. 已完成验证码输入")
            print("  2. 页面已跳转到个人资料/首页")
            print("  3. 浏览器窗口没有被遮挡")
            return

        # Step 5: 保存 session
        print("\n💾 保存 session 数据...")

        # 保存 cookies
        cookies = await engine.context.cookies()
        cookies_path = Path("./data/playwright_cookies.json")
        cookies_path.parent.mkdir(parents=True, exist_ok=True)

        with open(cookies_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)
        print(f"✓ Cookies 已保存: {cookies_path} ({len(cookies)} 个)")

        # 保存 localStorage
        local_storage = await page.evaluate("() => JSON.stringify(localStorage)")
        local_path = Path("./data/playwright_localstorage.json")
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(local_storage)
        print(f"✓ LocalStorage 已保存: {local_path}")

        # 保存 sessionStorage
        session_storage = await page.evaluate("() => JSON.stringify(sessionStorage)")
        session_path = Path("./data/playwright_sessionstorage.json")
        with open(session_path, "w", encoding="utf-8") as f:
            f.write(session_storage)
        print(f"✓ SessionStorage 已保存: {session_path}")

        # Step 6: 抓取推荐职位验证
        print("\n🔍 测试抓取首页推荐职位...")
        scraper = HomepageScraper(page, HumanSimulator(page))

        try:
            jobs = await scraper.get_recommended_jobs(max_jobs=10)
            print(f"✅ 抓取成功！共找到 {len(jobs)} 个职位")

            if jobs:
                print("\n-" * 50)
                for i, job in enumerate(jobs[:5], 1):
                    print(f"{i}. {job.title} @ {job.company}")
                    if job.salary:
                        print(f"   💰 {job.salary}")
                print("-" * 50)

        except Exception as e:
            print(f"⚠️ 抓取测试失败: {e}")

        print("\n" + "=" * 60)
        print("✅ Session 保存成功！")
        print("=" * 60)
        print("\n📋 下次运行：")
        print("   python tests/test_e2e_save_session.py")
        print("   ")
        print("   脚本会自动复用本次保存的 session，无需再次登录。")

    except KeyboardInterrupt:
        print("\n\n⛔ 用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if page and not page.is_closed():
            print("\n等待 5 秒后关闭浏览器...")
            await asyncio.sleep(5)
        if engine:
            await engine.stop()
            print("✓ 浏览器已关闭")


async def run_with_saved_session():
    """
    复用之前保存的 session 进行抓取
    """
    print("\n" + "-" * 60)
    print("🔄 复用已保存的 Session")
    print("-" * 60)
    print()

    cookies_path = Path("./data/playwright_cookies.json")
    local_path = Path("./data/playwright_localstorage.json")

    if not cookies_path.exists():
        print("❌ 没有找到保存的 session")
        print("请先运行此脚本完成手动登录。")
        return

    # 启动浏览器
    config = BrowserConfig(
        headless=False,
        user_data_dir="./data/browser_profile_manual",
        locale="zh-HK",
        timezone_id="Asia/Hong_Kong",
    )
    engine = BrowserEngine(config)

    try:
        page = await engine.start()
        print("✓ 浏览器已启动")

        # 加载 cookies
        if engine.context:
            with open(cookies_path, encoding="utf-8") as f:
                cookies = json.load(f)
            await engine.context.add_cookies(cookies)
            print(f"✓ 已加载 {len(cookies)} 个 cookies")

        # 加载 localStorage
        if local_path.exists():
            with open(local_path, encoding="utf-8") as f:
                local_data = json.load(f)
            if local_data and local_data != "{}":
                await page.goto("about:blank")
                await page.evaluate(f"""
                    () => {{
                        const data = {local_data};
                        Object.keys(data).forEach(key => {{
                            localStorage.setItem(key, data[key]);
                        }});
                    }}
                """)
                print("✓ 已恢复 localStorage")

        # 访问 JobsDB
        print("\n🌐 访问 hk.jobsdb.com...")
        await page.goto("https://hk.jobsdb.com/", wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # 检查登录状态
        is_logged_in = False
        for selector in ['a[href*="profile"]', '[data-automation="user-avatar"]']:
            try:
                elem = await page.query_selector(selector)
                if elem and await elem.is_visible():
                    is_logged_in = True
                    print("✅ Session 有效，已登录")
                    break
            except Exception:
                pass

        if not is_logged_in:
            print("⚠️  Session 可能已过期，需要重新登录")
            return

        # 抓取职位
        print("\n🔍 抓取首页推荐职位...")
        scraper = HomepageScraper(page, HumanSimulator(page))
        jobs = await scraper.get_recommended_jobs(max_jobs=20)

        print(f"✅ 抓取完成！共找到 {len(jobs)} 个职位")
        if jobs:
            print("\n-" * 50)
            for i, job in enumerate(jobs[:10], 1):
                print(f"{i}. {job.title}")
                print(f"   🏢 {job.company} | 📍 {job.location or 'N/A'}")
                print()
            print("-" * 50)

    except Exception as e:
        print(f"❌ 错误: {e}")
    finally:
        if engine:
            await engine.stop()
            print("✓ 浏览器已关闭")


if __name__ == "__main__":
    try:
        asyncio.run(manual_login_and_save_session())
    except KeyboardInterrupt:
        print("\n\n⛔ 用户中断")
    except Exception as e:
        print(f"\n💥 致命错误: {e}")
        import traceback
        traceback.print_exc()
