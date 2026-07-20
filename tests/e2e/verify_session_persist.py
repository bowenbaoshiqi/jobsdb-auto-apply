"""
最简单的验证 — 复用已有 Playwright profile

原理：Playwright 的 browser_profile_manual 目录会持久化
所有 cookies、localStorage、IndexedDB。

运行一次登录后，下次直接复用这个目录即可。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import BrowserConfig
from src.browser.engine import BrowserEngine


async def verify_profile_persistence():
    print("=" * 60)
    print("Session 持久化验证")
    print("=" * 60)
    print()

    # 关键：复用同一个 user_data_dir
    # 如果之前在此目录中登录过，cookies 和 localStorage 都在里面
    config = BrowserConfig(
        headless=False,
        user_data_dir="./data/browser_profile_manual",
        locale="zh-HK",
        timezone_id="Asia/Hong_Kong",
    )

    engine = BrowserEngine(config)

    try:
        print("🚀 启动浏览器（复用已有 profile）...")
        page = await engine.start()
        print("✓ 浏览器已启动\n")

        # 直接访问 JobsDB
        print("🌐 访问 hk.jobsdb.com...")
        await page.goto("https://hk.jobsdb.com/", wait_until="networkidle")
        await asyncio.sleep(3)

        url = page.url
        title = await page.title()

        print(f"   URL: {url[:80]}...")
        print(f"   标题: {title}")
        print()

        # 检查登录状态
        is_logged_in = False

        # 方法1: 查找 profile 链接
        profile_elems = await page.query_selector_all('a[href*="profile"]')
        for elem in profile_elems:
            if await elem.is_visible():
                text = await elem.text_content()
                print(f"✅ 找到 profile 链接: {text[:30]}")
                is_logged_in = True
                break

        # 方法2: 检查登录按钮
        if not is_logged_in:
            login_btns = await page.query_selector_all('text=Sign in, text=Log in, text=Login')
            if not login_btns:
                print("✅ 页面无登录按钮")
                is_logged_in = True

        # 方法3: 检查头像
        if not is_logged_in:
            avatar = await page.query_selector('img[alt*="profile"], [data-automation="user-avatar"]')
            if avatar and await avatar.is_visible():
                print("✅ 找到用户头像")
                is_logged_in = True

        print()
        if is_logged_in:
            print("🎉 Session 持久化成功！")
            print()
            print("这意味着：")
            print("  • 只需要在 Playwright 浏览器中登录一次")
            print("  • 之后运行脚本时复用同一个 profile 目录")
            print("  • 无需再次手动登录或提取 cookies")
            print()
            print("✅ 系统已准备就绪，可以运行正式投递：")
            print("   python -m src.main start --max-jobs 1")
        else:
            print("❌ 未检测到登录状态")
            print("\n可能原因：")
            print("  1. profile 目录中没有保存过登录 session")
            print("  2. Session 已过期（需要重新登录）")
            print()
            print("解决方案：运行手动登录脚本一次：")
            print("  python tests/test_e2e_auto_detect.py")
            print("  （浏览器弹出来后手动完成验证码登录）")

        print()
        print("等待 10 秒供观察...")
        await asyncio.sleep(10)

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if engine:
            await engine.stop()
            print("✓ 浏览器已关闭")


if __name__ == "__main__":
    try:
        asyncio.run(verify_profile_persistence())
    except KeyboardInterrupt:
        print("\n⛔ 中断")
    except Exception as e:
        print(f"\n💥 错误: {e}")
