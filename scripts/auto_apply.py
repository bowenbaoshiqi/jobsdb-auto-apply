"""
JobsDB 全自动投递 — 生产版

用法:
    python auto_apply.py 10          # 投递10个职位
    python auto_apply.py 5           # 投递5个职位
    python auto_apply.py             # 默认投递5个职位

功能:
    - 启动前自动检查环境（Python 版本、依赖包、Playwright 浏览器、登录 session）
    - 环境就绪后直接开始投递
    - 多步申请流程自动点击（Continue → Submit application）
    - 遇到无法处理的表单时 macOS 通知 + 3分钟轮询等待用户接管
    - 投递间隔 ≥3 分钟，避免频率过高
"""

import argparse
import asyncio
import importlib
import os
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─── 项目路径 ───────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import BrowserConfig, AppConfig
from src.browser.engine import BrowserEngine
from src.browser.playwright_page_controller import PlaywrightPageController
from src.jobsdb.homepage import HomepageScraper
from src.simulation.behavior import HumanSimulator
from src.storage.database import Database
from src.storage.models import ApplyResult, ApplyStatus
from src.storage.cookies import CookieStore
from src.monitor.logger import configure_logger

configure_logger()

# ─── 常量 ───────────────────────────────────────────────
LOG_FILE = Path(PROJECT_ROOT / "data" / "auto_apply.log")
SCREENSHOT_DIR = Path(PROJECT_ROOT / "data" / "screenshots")
DB_PATH = Path(PROJECT_ROOT / "data" / "jobsdb_e2e.db")
BROWSER_PROFILE = Path(PROJECT_ROOT / "data" / "browser_profile_manual")
COOKIES_FILE = Path(PROJECT_ROOT / "data" / "cookies.json")

# 依赖包映射: import_name → pip_name
REQUIRED_PACKAGES: Dict[str, str] = {
    "playwright": "playwright",
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings",
    "loguru": "loguru",
    "numpy": "numpy",
    "rich": "rich",
    "typer": "typer",
    "dotenv": "python-dotenv",
    "pytz": "pytz",
}

APPLY_INTERVAL_MIN_SEC = 45    # 投递间隔下限（秒）
APPLY_INTERVAL_MAX_SEC = 90    # 投递间隔上限（秒）——每次在此区间随机抖动，比固定值更像真人
USER_TAKEOVER_TIMEOUT = 120    # 用户接管等待上限（秒）：2 分钟内不响应则跳过该职位
USER_TAKEOVER_POLL = 10        # 轮询间隔（秒）
STEP_WAIT_SEC = 8              # 每步等待页面加载（秒）
PAGE_LOAD_WAIT_SEC = 10        # 申请页初始加载等待（秒）
MAX_STEPS_PER_JOB = 10         # 单职位最大步骤数
MAX_LOGIN_WAIT_MIN = 60        # 等待登录最大分钟数


# ═══════════════════════════════════════════════════════
#  日志 & 通知
# ═══════════════════════════════════════════════════════

def log_print(message: str, flush: bool = False):
    """同时输出到终端和日志文件"""
    now = datetime.now().strftime("%H:%M:%S")
    line = f"[{now}] {message}"
    print(line, flush=flush)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()


def notify_user(message: str):
    """macOS 弹窗通知"""
    try:
        script = f'display notification "{message}" with title "求职助手" sound name "Blow"'
        subprocess.run(["osascript", "-e", script], timeout=10, check=False)
    except Exception:
        pass


def alert_user_dialog(message: str):
    """macOS 系统弹窗（需要用户点击确认）"""
    try:
        script = f'display dialog "{message}" with title "求职助手需要操作" buttons {{"已处理", "跳过"}} default button "已处理" with icon caution'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=300,
        )
        return "已处理" in result.stdout
    except Exception:
        return False


# ═══════════════════════════════════════════════════════
#  环境检查（每个函数可独立调用 + 可测试）
# ═══════════════════════════════════════════════════════

class EnvCheckResult:
    """单项检查结果"""
    def __init__(self, name: str, passed: bool, message: str = "", fix_hint: str = ""):
        self.name = name
        self.passed = passed
        self.message = message
        self.fix_hint = fix_hint

    def __repr__(self):
        icon = "✅" if self.passed else "❌"
        s = f"{icon} {self.name}"
        if self.message:
            s += f": {self.message}"
        if self.fix_hint and not self.passed:
            s += f" → {self.fix_hint}"
        return s


def check_python_version(min_version: Tuple[int, int] = (3, 9)) -> EnvCheckResult:
    """检查 Python 版本"""
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= min_version:
        return EnvCheckResult("Python 版本", True, version_str)
    return EnvCheckResult(
        "Python 版本", False,
        f"{version_str}，需要 ≥ {min_version[0]}.{min_version[1]}",
        "请升级 Python",
    )


def check_python_dependencies(pkg_map: Optional[Dict[str, str]] = None) -> EnvCheckResult:
    """
    检查 Python 依赖包是否已安装。

    Args:
        pkg_map: {import_name: pip_name} 映射，默认使用 REQUIRED_PACKAGES

    Returns:
        EnvCheckResult，message 中包含缺失列表
    """
    if pkg_map is None:
        pkg_map = REQUIRED_PACKAGES
    missing = []
    for import_name, pip_name in pkg_map.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(pip_name)
    if not missing:
        return EnvCheckResult("Python 依赖", True, f"{len(pkg_map)} 个包已就绪")
    return EnvCheckResult(
        "Python 依赖", False,
        f"缺少 {len(missing)} 个: {', '.join(missing)}",
        f"pip install {' '.join(missing)}",
    )


def check_playwright_browsers() -> EnvCheckResult:
    """
    检查 Playwright 浏览器是否可用。

    检查顺序：
    1. 系统 Chromium（channel='chromium' 会用到）
    2. Google Chrome（macOS 常见）
    3. Playwright bundled chromium
    """
    # 1. 检查 Playwright bundled chromium
    pw_cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    pw_chromium_dirs = list(pw_cache.glob("chromium-*")) if pw_cache.exists() else []
    pw_has_chromium = any(d.is_dir() for d in pw_chromium_dirs)

    # 2. 检查系统 Chrome/Chromium
    system_chrome = Path("/Applications/Google Chrome.app").exists()
    system_chromium = Path("/Applications/Chromium.app").exists()

    # channel='chromium' 需要 Chromium.app 或 Chrome.app
    # (Playwright 会自动查找)
    has_system_browser = system_chrome or system_chromium

    if has_system_browser:
        browser_name = "Chromium" if system_chromium else "Google Chrome"
        return EnvCheckResult(
            "浏览器", True,
            f"系统 {browser_name} 可用",
        )
    if pw_has_chromium:
        return EnvCheckResult(
            "浏览器", True,
            f"Playwright bundled chromium 可用（{len(pw_chromium_dirs)} 个版本）",
        )
    return EnvCheckResult(
        "浏览器", False,
        "未找到可用浏览器",
        "安装 Chromium: brew install --cask chromium 或 python -m playwright install chromium",
    )


def check_profile_directory(profile_dir: Optional[Path] = None) -> EnvCheckResult:
    """
    检查浏览器 profile 目录状态。

    - 目录是否存在（不存在则创建）
    - SingletonLock 是否存在（表示有残留进程）
    - 是否有登录数据（Default/Cookies 文件）
    """
    if profile_dir is None:
        profile_dir = BROWSER_PROFILE

    # 确保目录存在
    profile_dir.mkdir(parents=True, exist_ok=True)

    warnings = []

    # 检查锁文件
    lock_files = ["SingletonLock", "SingletonCookie", "SingletonSocket"]
    existing_locks = [f for f in lock_files if (profile_dir / f).exists()]
    if existing_locks:
        warnings.append(f"发现残留锁文件: {', '.join(existing_locks)}")

    # 检查登录数据
    has_cookies = (profile_dir / "Default" / "Cookies").exists()
    has_local_state = (profile_dir / "Local State").exists()
    has_login_data = has_cookies and has_local_state

    msg_parts = []
    if has_login_data:
        msg_parts.append("有登录数据")
    else:
        msg_parts.append("无登录数据（首次需要手动登录）")

    if warnings:
        msg_parts.extend(warnings)

    result = EnvCheckResult("浏览器 Profile", True, "；".join(msg_parts))
    result.warnings = warnings  # type: ignore
    return result


def clean_profile_locks(profile_dir: Optional[Path] = None) -> int:
    """清理 profile 锁文件，返回清理数量"""
    if profile_dir is None:
        profile_dir = BROWSER_PROFILE
    count = 0
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = profile_dir / lock_file
        if lock_path.exists():
            try:
                lock_path.unlink()
                count += 1
            except Exception:
                pass
    return count


def kill_orphan_browsers() -> int:
    """
    清理残留的 Playwright 浏览器进程。
    只杀 "Google Chrome for Testing"，不杀用户的 Google Chrome。
    返回杀死的进程数。
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", "Google Chrome for Testing"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return 0
        pids = result.stdout.strip().split("\n")
        subprocess.run(
            ["pkill", "-f", "Google Chrome for Testing"],
            timeout=10, check=False,
        )
        import time
        time.sleep(3)
        return len(pids)
    except Exception:
        return 0


def ensure_data_directories() -> EnvCheckResult:
    """确保数据目录存在"""
    dirs = [LOG_FILE.parent, SCREENSHOT_DIR, DB_PATH.parent, BROWSER_PROFILE]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    return EnvCheckResult("数据目录", True, f"{len(dirs)} 个目录已就绪")


def run_environment_checks(
    pkg_map: Optional[Dict[str, str]] = None,
    profile_dir: Optional[Path] = None,
    auto_fix: bool = True,
) -> Tuple[bool, List[EnvCheckResult]]:
    """
    执行全部环境检查。

    Args:
        pkg_map: 自定义依赖包映射
        profile_dir: 自定义浏览器 profile 路径
        auto_fix: 是否自动修复（清理锁文件、杀死残留进程）

    Returns:
        (all_passed, results)
    """
    results: List[EnvCheckResult] = []

    # 1. Python 版本
    results.append(check_python_version())

    # 2. Python 依赖
    results.append(check_python_dependencies(pkg_map))

    # 3. 浏览器
    results.append(check_playwright_browsers())

    # 4. 数据目录
    results.append(ensure_data_directories())

    # 5. Profile 目录
    profile_result = check_profile_directory(profile_dir)
    results.append(profile_result)

    # 6. 自动修复
    if auto_fix:
        # 清理残留进程
        killed = kill_orphan_browsers()
        if killed > 0:
            log_print(f"   🧹 已清理 {killed} 个残留浏览器进程")

        # 清理锁文件
        if hasattr(profile_result, 'warnings') and profile_result.warnings:
            locks_cleaned = clean_profile_locks(profile_dir)
            if locks_cleaned > 0:
                log_print(f"   🧹 已清理 {locks_cleaned} 个 profile 锁文件")

    all_passed = all(r.passed for r in results)
    return all_passed, results


def print_check_results(results: List[EnvCheckResult]):
    """格式化打印检查结果"""
    log_print("🔍 环境检查")
    log_print("-" * 40)
    for r in results:
        log_print(f"   {r}")
    log_print("-" * 40)


# ═══════════════════════════════════════════════════════
#  登录检查
# ═══════════════════════════════════════════════════════

async def check_login(page) -> bool:
    """检查是否已登录 JobsDB"""
    for selector in [
        'a[href*="profile"]',
        '[data-automation="user-avatar"]',
        'img[alt*="profile"]',
    ]:
        try:
            elem = await page.query_selector(selector)
            if elem and await elem.is_visible():
                return True
        except Exception:
            pass

    try:
        text = await page.text_content("body")
        return (
            "Sign in" not in text
            and "Log in" not in text
            and "sign in" not in text.lower()
        )
    except Exception:
        return False


async def ensure_logged_in(page, context=None) -> bool:
    """
    确保已登录 JobsDB。如果未登录，弹通知等用户手动登录。
    登录成功后自动备份 cookies 到 JSON 文件。
    返回 True 表示已登录。
    """
    if await check_login(page):
        # 已登录，备份 cookies
        if context:
            await _backup_cookies(context)
        return True

    msg = "JobsDB 未登录，请在浏览器中完成登录"
    log_print(f"   ⚠ {msg}")
    notify_user(msg)
    log_print(f"   ⏳ 等待用户登录...（最多 {MAX_LOGIN_WAIT_MIN} 分钟）")

    for attempt in range(MAX_LOGIN_WAIT_MIN * 6):  # 每10秒检查一次
        await asyncio.sleep(10)
        try:
            await page.goto("https://hk.jobsdb.com/", wait_until="domcontentloaded")
            await asyncio.sleep(3)
            if await check_login(page):
                log_print("   ✅ 检测到已登录！")
                # 登录成功，备份 cookies
                if context:
                    await _backup_cookies(context)
                return True
        except Exception:
            pass
        if attempt % 6 == 0:
            log_print(f"   仍在等待登录... ({(attempt + 1) * 10 // 60} 分钟)")

    log_print("   ❌ 等待登录超时")
    return False


async def _backup_cookies(context) -> int:
    """
    从浏览器 context 导出 cookies 备份到 JSON 文件。
    只保存 JobsDB 域名的 cookies，避免保存无关数据。
    返回保存的 cookies 数量。
    """
    try:
        all_cookies = await context.cookies()
        # 只保留 JobsDB 相关的 cookies
        jobsdb_cookies = [
            c for c in all_cookies
            if "jobsdb" in c.get("domain", "") or "seek" in c.get("domain", "")
        ]
        store = CookieStore(str(COOKIES_FILE))
        store.save(jobsdb_cookies)
        log_print(f"   💾 已备份 {len(jobsdb_cookies)} 个 JobsDB cookies")
        return len(jobsdb_cookies)
    except Exception as e:
        log_print(f"   ⚠ Cookies 备份失败: {e}")
        return 0


async def _restore_cookies(context) -> bool:
    """
    从 JSON 文件恢复 cookies 到浏览器 context。
    返回是否成功恢复。
    """
    if not COOKIES_FILE.exists():
        log_print("   ℹ️ 无 cookies 备份文件")
        return False

    store = CookieStore(str(COOKIES_FILE))
    cookies = store.load()
    if not cookies:
        log_print("   ℹ️ Cookies 备份为空")
        return False

    # 检查备份新鲜度（24小时内）
    if not store.is_fresh(max_age_hours=24):
        log_print("   ⚠ Cookies 备份超过 24 小时，可能已过期")
        # 仍然尝试恢复，但标记可能失败

    try:
        # Playwright 需要特定格式的 cookies
        valid_cookies = []
        for cookie in cookies:
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

        await context.add_cookies(valid_cookies)
        log_print(f"   💾 已恢复 {len(valid_cookies)} 个 cookies")
        return True
    except Exception as e:
        log_print(f"   ⚠ Cookies 恢复失败: {e}")
        return False


# ═══════════════════════════════════════════════════════
#  按钮检测 & 点击（三层策略）
# ═══════════════════════════════════════════════════════

async def smart_click_button(page, keywords, timeout=5000, min_y=300):
    """
    智能查找并点击按钮。

    策略优先级：
    1. Playwright get_by_role("button"/"link", name=...) — 选 y 最大的
    2. CSS button/a:has-text(...) — 选 y 最大的
    3. JavaScript 遍历 button/a/input[submit] — 选 y 最大的

    关键：侧边栏步骤按钮 y≈226，操作按钮 y>300，通过 min_y 过滤。

    返回: (clicked: bool, found_text: str)
    """
    for keyword in keywords:
        # 策略1: Playwright locator
        for role in ["button", "link"]:
            try:
                locator = page.get_by_role(role, name=keyword, exact=False)
                count = await locator.count()
                if count > 0:
                    candidates = []
                    for i in range(min(count, 10)):
                        elem = locator.nth(i)
                        if await elem.is_visible():
                            if await elem.is_disabled():
                                continue
                            box = await elem.bounding_box()
                            if box and box["y"] >= min_y:
                                candidates.append((box["y"], elem))
                    if candidates:
                        candidates.sort(key=lambda c: c[0], reverse=True)
                        best_y, best_elem = candidates[0]
                        text = await best_elem.text_content() or ""
                        log_print(
                            f"   ✓ [策略1] 点击 {role}: "
                            f"'{text.strip()[:40]}' (y={int(best_y)})"
                        )
                        try:
                            await best_elem.click(timeout=timeout)
                            return True, text.strip()
                        except Exception as e:
                            log_print(f"   ⚠ [策略1] 点击失败: {str(e)[:60]}")
                            for y, elem in candidates[1:]:
                                try:
                                    await elem.click(timeout=timeout)
                                    text = await elem.text_content() or ""
                                    log_print(
                                        f"   ✓ [策略1 重试] 点击: "
                                        f"'{text.strip()[:40]}' (y={int(y)})"
                                    )
                                    return True, text.strip()
                                except Exception:
                                    continue
            except Exception:
                pass

        # 策略2: CSS has-text
        try:
            candidates = []
            for tag in ["button", "a", "span[role='button']"]:
                selector = f'{tag}:has-text("{keyword}")'
                elems = await page.query_selector_all(selector)
                for elem in elems:
                    if await elem.is_visible():
                        disabled = await elem.get_attribute("disabled")
                        aria_disabled = await elem.get_attribute("aria-disabled")
                        if disabled is not None or aria_disabled == "true":
                            continue
                        box = await elem.bounding_box()
                        if box and box["y"] >= min_y:
                            candidates.append((box["y"], elem))
            if candidates:
                candidates.sort(key=lambda c: c[0], reverse=True)
                best_y, best_elem = candidates[0]
                text = await best_elem.text_content() or ""
                log_print(
                    f"   ✓ [策略2] 点击: '{text.strip()[:40]}' (y={int(best_y)})"
                )
                try:
                    await best_elem.click(timeout=timeout)
                    return True, text.strip()
                except Exception as e:
                    log_print(f"   ⚠ [策略2] 点击失败: {str(e)[:60]}")
        except Exception:
            pass

        # 策略3: JavaScript 遍历（兜底）
        try:
            result = await page.evaluate(
                """
                (keyword) => {
                    const elements = document.querySelectorAll(
                        'button, a, input[type="submit"]'
                    );
                    let best = null;
                    let bestY = -1;
                    for (const el of elements) {
                        const text = (el.textContent || '').trim().toLowerCase();
                        const aria = (
                            el.getAttribute('aria-label') || ''
                        ).toLowerCase();
                        const textParts = text.split(/\\s{2,}/);
                        const matches = textParts.some(
                            p => p.includes(keyword.toLowerCase())
                        ) || aria.includes(keyword.toLowerCase());
                        if (matches) {
                            if (
                                el.disabled
                                || el.getAttribute('aria-disabled') === 'true'
                            ) continue;
                            const rect = el.getBoundingClientRect();
                            if (
                                rect.width > 0 && rect.height > 0
                                && rect.top >= 300 && rect.top > bestY
                            ) {
                                bestY = rect.top;
                                best = el;
                            }
                        }
                    }
                    if (best) {
                        best.click();
                        return {
                            found: true,
                            text: best.textContent.trim().substring(0, 50),
                            tag: best.tagName,
                            y: Math.round(bestY),
                        };
                    }
                    return { found: false };
                }
                """,
                keyword,
            )
            if result and result.get("found"):
                log_print(
                    f"   ✓ [策略3] 点击 {result['tag']}: "
                    f"'{result['text']}' (y={result.get('y', '?')})"
                )
                return True, result["text"]
        except Exception:
            pass

    return False, ""


# ═══════════════════════════════════════════════════════
#  页面状态检测
# ═══════════════════════════════════════════════════════

async def is_apply_success(url: str) -> bool:
    """是否投递成功（到达 success 页或回到详情页）"""
    return "/apply/success" in url or is_job_detail_page(url)


async def detect_quick_apply(page) -> Tuple[bool, str]:
    """
    检测当前职位详情页是否是快速申请。
    返回 (is_quick_apply, button_text)
    """
    # 快速申请关键词（中英文）
    quick_keywords = [
        "quick apply", "easy apply",
        "快速申请", "简单申请", "一键申请",
    ]

    # 普通申请关键词（这些会跳外部网站）
    normal_keywords = [
        "apply now", "apply",
        "申请", "立即申请",
    ]

    # 获取所有按钮文本
    buttons_info = await page.evaluate("""
        () => {
            const buttons = [];
            document.querySelectorAll('button, a, [role="button"]').forEach(el => {
                const text = (el.textContent || '').trim();
                const aria = (el.getAttribute('aria-label') || '').trim();
                const combined = (text + ' ' + aria).toLowerCase();
                if (combined.length > 0 && combined.length < 100) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        buttons.push({
                            text: text,
                            aria: aria,
                            combined: combined,
                            y: rect.top,
                            tag: el.tagName.toLowerCase(),
                        });
                    }
                }
            });
            return buttons;
        }
    """)

    # 优先找快速申请按钮
    for btn in buttons_info:
        combined = btn["combined"]
        for kw in quick_keywords:
            if kw in combined:
                return True, btn["text"] or btn["aria"]

    # 找普通申请按钮
    for btn in buttons_info:
        combined = btn["combined"]
        for kw in normal_keywords:
            if kw in combined:
                return False, btn["text"] or btn["aria"]

    # 没找到任何申请按钮
    return False, "not found"


async def click_quick_apply_button(page) -> bool:
    """
    点击快速申请按钮。
    返回是否成功点击。
    """
    quick_keywords = [
        "quick apply", "easy apply",
        "快速申请", "简单申请", "一键申请",
    ]

    for keyword in quick_keywords:
        # 策略1: Playwright role
        for role in ["button", "link"]:
            try:
                locator = page.get_by_role(role, name=keyword, exact=False)
                count = await locator.count()
                for i in range(min(count, 5)):
                    elem = locator.nth(i)
                    if await elem.is_visible():
                        box = await elem.bounding_box()
                        if box and box["y"] >= 200:
                            text = await elem.text_content() or ""
                            log_print(f"   ✓ 点击快速申请按钮: '{text.strip()[:40]}'", flush=True)
                            await elem.click(timeout=5000)
                            return True
            except Exception:
                pass

        # 策略2: CSS has-text
        try:
            for tag in ["button", "a", "span[role='button']"]:
                selector = f'{tag}:has-text("{keyword}")'
                elems = await page.query_selector_all(selector)
                for elem in elems:
                    if await elem.is_visible():
                        box = await elem.bounding_box()
                        if box and box["y"] >= 200:
                            text = await elem.text_content() or ""
                            log_print(f"   ✓ 点击快速申请按钮: '{text.strip()[:40]}'", flush=True)
                            await elem.click(timeout=5000)
                            return True
        except Exception:
            pass

    return False


async def handle_cover_letter_page(page) -> bool:
    """
    检测并处理 cover letter 选择页面。
    自动点击 "Don't include cover letter" / "Skip" 等按钮。
    返回 True 表示已处理。
    """
    # 检测是否是 cover letter 选择页面（不是 review 页面）
    is_cover_page = await page.evaluate("""
        () => {
            const url = window.location.href.toLowerCase();
            // review 页面不处理
            if (url.includes('/review')) return false;

            const text = (document.body.textContent || '').toLowerCase();
            const hasCoverLetter = text.includes('cover letter') || text.includes('求职信');

            // 必须有 "don't include" 或类似跳过选项
            const hasSkipOption = text.includes("don't include") ||
                                  text.includes('do not include') ||
                                  text.includes('skip cover') ||
                                  text.includes('no cover letter') ||
                                  text.includes('不包括') ||
                                  text.includes('跳过');

            return hasCoverLetter && hasSkipOption;
        }
    """)

    if not is_cover_page:
        return False

    log_print("   📝 检测到 cover letter 页面，尝试自动跳过...", flush=True)

    # 优先点击 "Don't include a cover letter" 按钮（精确匹配）
    exact_keywords = [
        "Don't include a cover letter",
        "Don't include cover letter",
        "don't include a cover letter",
        "don't include cover letter",
    ]

    # 先尝试精确匹配
    for keyword in exact_keywords:
        try:
            # 策略1: Playwright button/link role
            for role in ["button", "link"]:
                locator = page.get_by_role(role, name=keyword, exact=False)
                count = await locator.count()
                for i in range(min(count, 5)):
                    elem = locator.nth(i)
                    if await elem.is_visible():
                        box = await elem.bounding_box()
                        if box and box["y"] >= 200:
                            text = await elem.text_content() or ""
                            log_print(f"   ✓ 点击 cover letter 按钮: '{text.strip()[:50]}'", flush=True)
                            await elem.click(timeout=5000)
                            return True
        except Exception:
            pass

        try:
            # 策略2: CSS has-text
            for tag in ["button", "a", "span[role='button']"]:
                selector = f'{tag}:has-text("{keyword}")'
                elems = await page.query_selector_all(selector)
                for elem in elems:
                    if await elem.is_visible():
                        box = await elem.bounding_box()
                        if box and box["y"] >= 200:
                            text = await elem.text_content() or ""
                            log_print(f"   ✓ 点击 cover letter 按钮: '{text.strip()[:50]}'", flush=True)
                            await elem.click(timeout=5000)
                            return True
        except Exception:
            pass

    # 模糊匹配关键词
    fuzzy_keywords = [
        "Don't include",
        "No cover letter",
        "Skip cover letter",
        "Skip",
        "Continue without cover letter",
        "不包括求职信",
        "跳过",
    ]

    for keyword in fuzzy_keywords:
        try:
            # 策略1: Playwright button/link role
            for role in ["button", "link"]:
                locator = page.get_by_role(role, name=keyword, exact=False)
                count = await locator.count()
                for i in range(min(count, 5)):
                    elem = locator.nth(i)
                    if await elem.is_visible():
                        box = await elem.bounding_box()
                        if box and box["y"] >= 200:  # 避开顶部导航
                            text = await elem.text_content() or ""
                            log_print(f"   ✓ 点击 cover letter 按钮: '{text.strip()[:40]}'", flush=True)
                            await elem.click(timeout=5000)
                            return True
        except Exception:
            pass

        try:
            # 策略2: CSS has-text
            for tag in ["button", "a", "span[role='button']"]:
                selector = f'{tag}:has-text("{keyword}")'
                elems = await page.query_selector_all(selector)
                for elem in elems:
                    if await elem.is_visible():
                        box = await elem.bounding_box()
                        if box and box["y"] >= 200:
                            text = await elem.text_content() or ""
                            log_print(f"   ✓ 点击 cover letter 按钮: '{text.strip()[:40]}'", flush=True)
                            await elem.click(timeout=5000)
                            return True
        except Exception:
            pass

    # 如果找不到 skip 按钮，尝试找 cover letter 的 "Don't include" radio
    try:
        # 精确定位：coverLetter-method 且 value="none" 的 radio
        no_cover_radio = await page.query_selector(
            'input[type="radio"][name="coverLetter-method"][value="none"]'
        )

        # 如果找不到，尝试通过 label 文本找
        if not no_cover_radio:
            # 找包含 "Don't include a cover letter" 的 label
            labels = await page.query_selector_all('label')
            for label in labels:
                text = await label.text_content() or ""
                # 必须同时包含 "don't include" 和 "cover letter"
                text_lower = text.lower()
                if "don't include" in text_lower and "cover" in text_lower:
                    # 找到对应的 radio
                    radio_id = await label.get_attribute('for')
                    if radio_id:
                        no_cover_radio = await page.query_selector(f'#{radio_id}')
                    else:
                        # label 内部可能有 radio
                        no_cover_radio = await label.query_selector('input[type="radio"]')
                    if no_cover_radio:
                        # 验证是 coverLetter-method
                        name = await no_cover_radio.get_attribute('name')
                        if name and 'coverletter' in name.lower():
                            break
                        else:
                            no_cover_radio = None

        if no_cover_radio and await no_cover_radio.is_visible():
            # 点击 radio 并触发 change 事件
            await no_cover_radio.click()
            await page.evaluate('(el) => el.dispatchEvent(new Event("change", { bubbles: true }))', no_cover_radio)
            log_print("   ✓ 选择 'Don\\'t include a cover letter'", flush=True)
            await asyncio.sleep(1)

            # 然后点 Continue
            continue_btn = await page.query_selector('button:has-text("Continue")')
            if continue_btn:
                await continue_btn.click()
                log_print("   ✓ 点击 Continue", flush=True)
            return True
    except Exception as e:
        log_print(f"   ⚠ 处理 cover letter radio 失败: {e}", flush=True)

    log_print("   ⚠ 未找到 cover letter 跳过按钮", flush=True)
    return False


def is_job_detail_page(url: str) -> bool:
    """是否回到职位详情页"""
    return "job/" in url and "/apply" not in url


async def wait_for_user_takeover(page, reason: str) -> bool:
    """
    通知用户接管，轮询等待最多 USER_TAKEOVER_TIMEOUT 秒。
    每隔 USER_TAKEOVER_POLL 秒检查一次页面状态。
    返回 True = 用户已处理，False = 超时跳过。
    """
    # 先发通知
    notify_user(reason)
    log_print(f"   🚨 {reason}")

    # 再弹系统对话框（会阻塞，但用户点完就返回）
    user_confirmed = alert_user_dialog(f"{reason}\\n\\n请在浏览器中处理，然后点击'已处理'继续。")

    if user_confirmed:
        # 用户点击了"已处理"，再确认一下页面状态
        await asyncio.sleep(2)
        if is_job_detail_page(page.url) or await is_apply_success(page.url):
            return True
        # 即使用户点了已处理但页面状态不对，也相信用户
        return True

    # 用户点了"跳过"或超时，再轮询一段时间看页面是否自己变化
    max_polls = USER_TAKEOVER_TIMEOUT // USER_TAKEOVER_POLL
    for poll in range(max_polls):
        elapsed = (poll + 1) * USER_TAKEOVER_POLL
        log_print(
            f"   ⏳ 等待页面变化... ({elapsed}s/{USER_TAKEOVER_TIMEOUT}s)",
            flush=True,
        )
        await asyncio.sleep(USER_TAKEOVER_POLL)
        if is_job_detail_page(page.url) or await is_apply_success(page.url):
            return True
    return False


# ═══════════════════════════════════════════════════════
#  核心投递逻辑
# ═══════════════════════════════════════════════════════

async def auto_apply(page, job, human, db) -> bool:
    """自动投递单个职位，返回是否成功"""
    log_print(f"\n🎯 [{datetime.now().strftime('%H:%M:%S')}] {job.title[:40]}")

    # 检查数据库：已投递则跳过
    if job.id in db.get_applied_job_ids():
        log_print("   ⏭ 已投递，跳过")
        return False

    # 先访问职位详情页，检测是否是快速申请
    detail_url = f"https://hk.jobsdb.com/job/{job.id}"
    log_print("   访问职位详情页...", flush=True)

    try:
        await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        log_print(f"   ❌ 详情页加载失败: {e}")
        return False

    await asyncio.sleep(5)

    # 检测是否是快速申请
    is_quick, button_text = await detect_quick_apply(page)
    if not is_quick:
        log_print(f"   ⏭ 非快速申请（按钮: '{button_text}'），跳过")
        return False

    log_print(f"   ✅ 检测到快速申请按钮: '{button_text}'", flush=True)

    # 点击快速申请按钮进入申请流程
    clicked = await click_quick_apply_button(page)
    if not clicked:
        log_print("   ❌ 无法点击快速申请按钮，跳过")
        return False

    await asyncio.sleep(PAGE_LOAD_WAIT_SEC)

    # 检查是否跳转到登录页
    if "login" in page.url.lower() or "signin" in page.url.lower():
        log_print("   ⚠ 需要登录，跳过")
        notify_user("需要重新登录 JobsDB")
        return False

    # 截图记录
    await page.screenshot(path=str(SCREENSHOT_DIR / f"apply_{job.id}_start.png"))

    # ── 步骤循环 ──
    stuck_count = 0
    cover_letter_handled_urls = set()  # 记录已处理过 cover letter 的 URL

    for step in range(MAX_STEPS_PER_JOB):
        log_print(f"\n   📋 步骤 {step + 1}/{MAX_STEPS_PER_JOB}", flush=True)
        await asyncio.sleep(STEP_WAIT_SEC)

        current_url = page.url
        log_print(f"   URL: {current_url}", flush=True)

        # 成功检测
        if await is_apply_success(current_url):
            log_print("   ✅ 投递成功！（已到达成功页面）", flush=True)
            _record_success(db, job)
            return True

        # 登录检测
        if "login" in current_url.lower() or "signin" in current_url.lower():
            log_print("   ⚠ 跳转到登录页，停止", flush=True)
            return False

        # 截图当前步骤
        await page.screenshot(
            path=str(SCREENSHOT_DIR / f"apply_{job.id}_step{step + 1}.png")
        )

        # 检测步骤指示
        step_info = await page.evaluate("""
            () => {
                const all = document.querySelectorAll(
                    '[class*="step"], [aria-label*="step"], [data-automation*="step"]'
                );
                for (const el of all) {
                    const t = el.textContent || el.getAttribute('aria-label') || '';
                    if (/step/i.test(t)) return t.trim().substring(0, 80);
                }
                return '';
            }
        """)
        if step_info:
            log_print(f"   📊 步骤指示: {step_info}")

        # ── 查找并点击按钮 ──
        # 优先处理 cover letter 选择页（每个 URL 只处理一次）
        if current_url not in cover_letter_handled_urls:
            cover_letter_handled = await handle_cover_letter_page(page)
            if cover_letter_handled:
                log_print("   ✅ 已处理 cover letter 页面", flush=True)
                cover_letter_handled_urls.add(current_url)
                await asyncio.sleep(5)
                continue

        button_keywords = [
            ["Continue", "continue", "CONTINUE"],
            ["Submit application", "submit application"],
            ["Review and submit", "review and submit"],
            ["Submit", "submit", "SUBMIT"],
            ["Don't include", "dont include", "no cover letter", "skip cover"],
        ]

        clicked = False
        found_text = ""
        for keyword_group in button_keywords:
            clicked, found_text = await smart_click_button(page, keyword_group)
            if clicked:
                break

        if clicked:
            log_print("   ⏳ 等待页面响应...", flush=True)
            await asyncio.sleep(5)

            new_url = page.url
            if new_url != current_url:
                log_print(f"   ✅ URL已变化: {new_url}", flush=True)
                stuck_count = 0
            else:
                has_new_button = await page.evaluate("""
                    () => {
                        const keywords = ['submit', 'confirm', 'agree', 'accept'];
                        const buttons = document.querySelectorAll(
                            'button, a, input[type="submit"]'
                        );
                        for (const btn of buttons) {
                            const text = (btn.textContent || '').trim().toLowerCase();
                            const aria = (
                                btn.getAttribute('aria-label') || ''
                            ).toLowerCase();
                            const combined = text + ' ' + aria;
                            for (const kw of keywords) {
                                if (combined.includes(kw) && !combined.includes('review')) {
                                    const rect = btn.getBoundingClientRect();
                                    if (rect.width > 0 && rect.height > 0) return true;
                                }
                            }
                        }
                        return false;
                    }
                """)
                if has_new_button:
                    log_print("   ✅ 检测到新的提交按钮", flush=True)
                    stuck_count = 0
                else:
                    stuck_count += 1
                    log_print(f"   ⚠ URL未变化 (连续 {stuck_count} 次)", flush=True)
                    if stuck_count >= 3:
                        handled = await wait_for_user_takeover(
                            page, f"职位 {job.title[:20]} 投递卡住，请接管浏览器",
                        )
                        if handled:
                            log_print("   ✅ 用户处理完成，投递成功！", flush=True)
                            _record_success(db, job, tag="manual-assisted")
                            return True
                        else:
                            log_print("   ⚠ 超时，跳过此职位", flush=True)
                            return False
        else:
            stuck_count = 0
            log_print("   ⚠ 未找到可点击按钮", flush=True)

            has_form = await page.evaluate("""
                () => {
                    const inputs = document.querySelectorAll(
                        'input:not([type="hidden"]):not([type="submit"]), select, textarea'
                    );
                    for (const inp of inputs) {
                        const rect = inp.getBoundingClientRect();
                        if (
                            rect.width > 50 && rect.height > 20
                            && rect.top >= 0 && rect.top < window.innerHeight
                        ) return true;
                    }
                    return false;
                }
            """)

            if has_form:
                handled = await wait_for_user_takeover(
                    page, "职位需要填写额外信息，请接管浏览器"
                )
                if handled:
                    log_print("   ✅ 用户处理完成，投递成功！", flush=True)
                    _record_success(db, job, tag="manual-assisted")
                    return True
                else:
                    log_print("   ⚠ 超时，跳过此职位", flush=True)
                    return False
            else:
                log_print("   ℹ️ 无操作项，可能已完成", flush=True)
                await asyncio.sleep(5)

    log_print("   ❌ 达到最大步骤数，未确认成功", flush=True)
    return False


def _record_success(db, job, tag: Optional[str] = None):
    """记录投递成功"""
    if tag is None:
        tag = f"auto-{datetime.now().strftime('%Y%m%d')}"
    result = ApplyResult(
        status=ApplyStatus.SUBMITTED,
        job_id=job.id,
        duration_seconds=0,
    )
    db.record_application(result, tag)


# ═══════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════

async def run(max_apply: int = 5):
    """
    主入口：环境检查 → 启动浏览器 → 登录确认 → 抓取职位 → 批量投递

    Args:
        max_apply: 本次最大投递数
    """
    log_print("=" * 60)
    log_print("JobsDB 全自动投递")
    log_print(f"目标投递数: {max_apply}")
    log_print("=" * 60)
    log_print("")

    # ── 1. 环境检查 ──
    all_passed, results = run_environment_checks()
    print_check_results(results)
    if not all_passed:
        log_print("❌ 环境检查未通过，请修复后重试")
        return

    # ── 2. 启动浏览器 ──
    config = AppConfig(
        browser=BrowserConfig(
            headless=False,
            user_data_dir=str(BROWSER_PROFILE),
            window_width=1920,
            window_height=1080,
        )
    )
    engine = BrowserEngine(config.browser)
    db = Database(str(DB_PATH))

    try:
        log_print("🚀 启动浏览器...", flush=True)
        page = None
        for attempt in range(3):
            try:
                page = await engine.start()
                break
            except Exception as e:
                log_print(f"   ⚠ 浏览器启动失败 (第 {attempt + 1}/3 次): {str(e)[:80]}")
                if attempt < 2:
                    kill_orphan_browsers()
                    clean_profile_locks()
                    await asyncio.sleep(3)
        if page is None:
            log_print("   ❌ 浏览器启动失败，请检查 profile 目录或重启")
            return
        log_print("✅ 浏览器已启动\n", flush=True)

        # ── 3. 尝试从备份恢复 cookies ──
        if engine.context:
            log_print("💾 检查 cookies 备份...", flush=True)
            await _restore_cookies(engine.context)

        # ── 4. 访问首页 & 检查登录 ──
        log_print("🌐 访问首页...", flush=True)
        await page.goto("https://hk.jobsdb.com/", wait_until="domcontentloaded")
        await asyncio.sleep(8)
        log_print(f"   当前URL: {page.url}", flush=True)

        log_print("🔐 检查登录状态...", flush=True)
        if not await ensure_logged_in(page, context=engine.context):
            log_print("❌ 登录超时，退出")
            return
        log_print("✅ 已登录\n", flush=True)

        # ── 5. 抓取职位 ──
        log_print("🔍 抓取职位...", flush=True)
        human = HumanSimulator(page)
        scraper = HomepageScraper(PlaywrightPageController(page), human)
        fetch_count = max(max_apply * 3, 20)
        jobs = await scraper.get_recommended_jobs(max_jobs=fetch_count)
        log_print(f"✅ 找到 {len(jobs)} 个职位\n", flush=True)

        if not jobs:
            log_print("❌ 没有职位可投递", flush=True)
            return

        # ── 6. 批量投递 ──
        applied = 0
        for idx, job in enumerate(jobs, 1):
            if applied >= max_apply:
                log_print(f"\n⏹️ 已达到最大投递数 {max_apply}，停止", flush=True)
                break

            success = await auto_apply(page, job, human, db)
            if success:
                applied += 1
                if applied < max_apply:
                    interval = random.uniform(APPLY_INTERVAL_MIN_SEC, APPLY_INTERVAL_MAX_SEC)
                    log_print(
                        f"\n⏳ 等待 {interval:.0f} 秒后投递下一个...",
                        flush=True,
                    )
                    await asyncio.sleep(interval)

        # ── 7. 结果汇总 ──
        log_print(f"\n{'=' * 60}", flush=True)
        log_print(f"本次共投递 {applied} 个职位", flush=True)
        log_print(f"{'=' * 60}", flush=True)

        log_print("\n✅ 投递完成，浏览器保持打开", flush=True)
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        log_print("\n⛔ 用户中断", flush=True)
    except Exception as e:
        log_print(f"\n❌ 错误: {e}", flush=True)
        import traceback
        traceback.print_exc()
        notify_user(f"投递错误: {str(e)[:50]}")
    finally:
        if engine:
            await engine.stop()
        log_print("✓ 浏览器已关闭", flush=True)


# ═══════════════════════════════════════════════════════
#  CLI 入口
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="JobsDB 全自动投递",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python auto_apply.py 10     投递10个职位
  python auto_apply.py 5      投递5个职位
  python auto_apply.py        默认投递5个职位
        """,
    )
    parser.add_argument(
        "count",
        type=int,
        nargs="?",
        default=5,
        help="投递数量（默认5）",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run(max_apply=args.count))
    except KeyboardInterrupt:
        log_print("\n⛔ 已退出")
    except Exception as e:
        log_print(f"\n💥 致命错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
