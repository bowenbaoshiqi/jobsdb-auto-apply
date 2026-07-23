"""
真实 E2E 测试 — JobsDB HK 登录 + 首页职位抓取

⚠️ 安全提示：
- 账号密码通过终端交互输入，不会保存到文件
- 使用 headed 模式（可见浏览器窗口），方便你观察异常情况
- 测试结束后自动关闭浏览器
- Cookie 保存到 data/browser_profile_e2e（便于复用）

使用方法：
    conda activate jobsdb
    python tests/test_e2e_live.py
"""

import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os

from dotenv import load_dotenv
from loguru import logger

from config.settings import BrowserConfig, JobsDBConfig
from src.browser.engine import BrowserEngine
from src.jobsdb.homepage import HomepageScraper
from src.jobsdb.login import LoginHandler
from src.simulation.behavior import HumanSimulator
from src.storage.database import Database
from src.utils.screenshot import capture_screenshot

# 加载 .env
load_dotenv()


async def test_e2e_login_and_scrape():
    """
    TC-18 + TC-19: 真实登录 + 抓取首页推荐职位
    """
    print("=" * 60)
    print("JobsDB HK 真实 E2E 测试")
    print("=" * 60)
    print()

    # 方式1: 从环境变量/.env 读取
    email = os.environ.get("JOBSDB_EMAIL", "").strip()
    password = os.environ.get("JOBSDB_PASSWORD", "").strip()

    # 方式2: 交互式输入（如果在终端中运行）
    if not email or not password:
        try:
            email = input("请输入 JobsDB 邮箱 (email): ").strip()
            password = getpass.getpass("请输入 JobsDB 密码: ").strip()
        except EOFError:
            print("⚠️  无法交互输入，请配置 .env 文件:")
            print("   echo 'JOBSDB_EMAIL=your@email.com' >> .env")
            print("   echo 'JOBSDB_PASSWORD=your-password' >> .env")
            return

    if not email or not password:
        print("❌ 邮箱和密码不能为空")
        return
        print("❌ 密码不能为空")
        return

    print()
    print(f"✓ 账号: {email[:3]}***@{email.split('@')[-1]}")
    print("✓ 将打开浏览器窗口，请观察登录过程...")
    print("✓ 如果遇到验证码，请手动解决后按 Enter 继续")
    print()

    # 配置
    browser_config = BrowserConfig(
        headless=False,  # headed 模式，方便观察
        window_width=1920,
        window_height=1080,
        user_data_dir="./data/browser_profile_e2e",
        locale="zh-HK",
        timezone_id="Asia/Hong_Kong",
    )

    jobsdb_config = JobsDBConfig(
        email=email,
        password=password,
    )

    # 启动浏览器
    engine = BrowserEngine(browser_config)
    page = None

    try:
        print("🚀 启动浏览器...")
        page = await engine.start()
        print("✓ 浏览器已启动 (headed 模式)")

        # 等待一下让用户看到浏览器窗口
        await asyncio.sleep(1)

        # 初始化 HumanSimulator
        human = HumanSimulator(page)

        # 登录流程
        print("🔐 开始登录流程...")
        login_handler = LoginHandler(page, jobsdb_config, human)

        logged_in = False
        try:
            logged_in = await login_handler.ensure_logged_in()
        except Exception as e:
            logger.error(f"登录异常: {e}")
            print(f"\n⚠️ 登录过程中出现问题: {e}")
            print("可能原因：")
            print("  1. 账号密码错误")
            print("  2. 遇到验证码（查看浏览器窗口）")
            print("  3. 网络问题")

        if not logged_in:
            print("\n❌ 登录失败")
            # 截图保存
            screenshot = await capture_screenshot(page, "login_failed")
            print(f"📸 截图已保存: {screenshot}")
            return

        print("✅ 登录成功！")
        print()

        # 等待页面稳定
        await asyncio.sleep(2)

        # 抓取首页推荐职位
        print("🔍 开始抓取首页推荐职位...")
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

            # 保存到数据库
            db = Database("./data/jobsdb_e2e.db")
            for job in jobs:
                db.save_job(job)
            print("💾 已保存到数据库: data/jobsdb_e2e.db")
        else:
            print("⚠️ 没有找到推荐职位")
            print("可能原因：")
            print("  1. 新账号还没有推荐数据")
            print("  2. 页面结构变化，选择器需要更新")
            print("  3. 需要完善个人资料才能获得推荐")

        print()
        print("=" * 60)
        print("✅ E2E 测试完成！")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\n⛔ 用户中断")
    except Exception as e:
        logger.exception(f"E2E 测试异常: {e}")
        print(f"\n❌ 测试异常: {e}")
    finally:
        if page and not page.is_closed():
            print("\n等待 5 秒后关闭浏览器...")
            print("（你可以趁这个机会查看页面内容）")
            await asyncio.sleep(5)

        if engine:
            await engine.stop()
            print("✓ 浏览器已关闭")


async def test_e2e_apply_single_job():
    """
    TC-19 进阶：尝试投递单个职位（可选，需确认）
    """
    # 这个测试需要选择第一个职位并尝试投递
    # 由于涉及真实投递，默认不运行，需要用户显式确认
    pass


if __name__ == "__main__":
    try:
        asyncio.run(test_e2e_login_and_scrape())
    except Exception as e:
        print(f"\n💥 致命错误: {e}")
        import traceback
        traceback.print_exc()
