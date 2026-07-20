"""
真实 E2E 测试 — 复用 Chrome 完整 Profile

原理：直接启动 Playwright 并指向你的 Chrome 用户数据目录，
这样 Cookie、LocalStorage、Session Storage、IndexedDB 全部复用。

使用方法：
    conda activate jobsdb
    python tests/test_e2e_chrome_profile.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import BrowserConfig
from src.browser.engine import BrowserEngine
from src.jobsdb.homepage import HomepageScraper
from src.simulation.behavior import HumanSimulator
from src.utils.screenshot import capture_screenshot


CHROME_PROFILE_DIR = "/Users/t91/Library/Application Support/Google/Chrome"


def find_available_profile():
    """找到 Chrome 中可用的 profile"""
    default_profile = Path(CHROME_PROFILE_DIR) / "Default"
    if default_profile.exists():
        return str(default_profile)

    # 检查是否有其他 profile
    profile_dirs = list(Path(CHROME_PROFILE_DIR).glob("Profile *"))
    if profile_dirs:
        return str(profile_dirs[0])

    return None


async def test_e2e_with_chrome_profile():
    """
    TC-18 + TC-19: 使用 Chrome profile 真实登录 + 抓取
    """
    print("=" * 60)
    print("JobsDB HK E2E 测试 — Chrome Profile 复用")
    print("=" * 60)
    print()

    # 找到 Chrome profile
    chrome_profile = find_available_profile()
    if not chrome_profile:
        print("❌ 未找到 Chrome profile")
        return

    print(f"✓ 找到 Chrome profile: {chrome_profile}")
    print()

    # ⚠️ 重要：必须先关闭 Chrome！
    print("⚠️  警告：运行此测试前，请确保 Chrome 已完全关闭！")
    print("   如果 Chrome 正在运行，cookies 会被锁定，无法读取。")
    print()

    # 复制一份 profile 到临时目录（避免损坏原始数据）
    temp_profile = "./data/chrome_profile_temp"
    print(f"📁 复制 Chrome profile 到临时目录...")

    try:
        if Path(temp_profile).exists():
            shutil.rmtree(temp_profile)
        shutil.copytree(chrome_profile, temp_profile, symlinks=True)
        print(f"✓ Profile 已复制到: {temp_profile}")
    except Exception as e:
        print(f"⚠️ 复制失败，尝试直接使用原 profile: {e}")
        temp_profile = chrome_profile

    # 使用 Chrome profile 启动浏览器
    browser_config = BrowserConfig(
        headless=False,  # 必须 headed 模式
        window_width=1920,
        window_height=1080,
        user_data_dir=temp_profile,
        locale="zh-HK",
        timezone_id="Asia/Hong_Kong",
    )

    engine = BrowserEngine(browser_config)

    try:
        print("\n🚀 启动浏览器（使用 Chrome Profile）...")
        page = await engine.start()
        print("✓ 浏览器已启动")

        # 访问 JobsDB
        print("\n🌐 访问 hk.jobsdb.com...")
        await page.goto("https://hk.jobsdb.com/", wait_until="domcontentloaded")
        await asyncio.sleep(5)  # 等待页面完全加载

        # 检查登录状态
        print("🔐 检查登录状态...")

        # 方法1: 检查页面是否被重定向到登录页
        current_url = page.url
        print(f"   当前 URL: {current_url[:80]}...")

        if "login" in current_url.lower() or "seek.com" in current_url:
            print("\n⚠️  页面被重定向到登录页 — Cookie 未生效")
            print("可能原因：")
            print("  1. Chrome 未关闭，profile 文件被锁定")
            print("  2. Cookie 已过期")
            print("  3. JobsDB 检测到不同浏览器指纹")
            print("  4. Chrome 和 Playwright 的 Chromium 版本差异太大")
            print()
            print("建议：")
            print("  - 彻底关闭 Chrome（Cmd+Q）")
            print("  - 在 Chrome 中刷新 JobsDB 页面确保登录状态最新")
            print("  - 重新运行此脚本")
            return

        # 方法2: 检查用户相关元素
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
                    print(f"✅ 检测到登录状态: {selector}")
                    break
            except:
                pass

        if not is_logged_in:
            page_text = await page.text_content("body")
            login_indicators = ["Sign in", "Log in", "登入", "登录"]
            has_login = any(ind in page_text for ind in login_indicators)

            if not has_login and "dashboard" not in current_url:
                is_logged_in = True
                print("✅ 页面无登录按钮，推测已登录")

        if not is_logged_in:
            print("\n❌ 未检测到登录状态")
            screenshot = await capture_screenshot(page, "e2e_login_check")
            print(f"📸 截图: {screenshot}")
            return

        print("\n🎉 登录状态确认！可以抓取推荐职位了。")
        print()

        # 抓取首页推荐职位
        print("🔍 开始抓取首页推荐职位...")
        scraper = HomepageScraper(page, HumanSimulator(page))

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
            print(f"{'#':<4} {'职位标题':<35} {'公司':<20} {'地点':<15}")
            print("-" * 60)
            for i, job in enumerate(jobs[:15], 1):
                title = (job.title[:32] + "...") if len(job.title) > 35 else job.title
                company = (job.company[:17] + "...") if len(job.company) > 20 else job.company
                location = (job.location[:12] + "...") if job.location and len(job.location) > 15 else (job.location or "")
                print(f"{i:<4} {title:<35} {company:<20} {location:<15}")
            print("-" * 60)

            if len(jobs) > 15:
                print(f"... 还有 {len(jobs) - 15} 个职位未显示")
            print()
        else:
            print("⚠️ 没有找到推荐职位")
            print("可能：新账号无推荐、需要完善资料")

        print("=" * 60)
        print("✅ E2E 测试完成！")
        print("=" * 60)

        print("\n等待 10 秒供观察...")
        await asyncio.sleep(10)

    except KeyboardInterrupt:
        print("\n\n⛔ 用户中断")
    except Exception as e:
        logger.exception(f"E2E 测试异常: {e}")
        print(f"\n❌ 测试异常: {e}")
    finally:
        if engine:
            await engine.stop()
            print("✓ 浏览器已关闭")

        # 清理临时 profile
        if temp_profile != chrome_profile and Path(temp_profile).exists():
            try:
                shutil.rmtree(temp_profile)
                print(f"✓ 临时 profile 已清理")
            except:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(test_e2e_with_chrome_profile())
    except KeyboardInterrupt:
        print("\n\n⛔ 用户中断")
    except Exception as e:
        print(f"\n💥 致命错误: {e}")
        import traceback
        traceback.print_exc()
