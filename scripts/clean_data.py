"""清理 data/ 运行时残留。

防止 browser_profile_test_*、debug 产物、日志、临时 cookies 等 ~GB 残留堆积。
配套手动登录模式(见 docs/superpowers/specs/2026-07-21-manual-login-mode-design.md 7.4)。

用法:
    python scripts/clean_data.py                       # 默认 dry-run,只列出要删的
    python scripts/clean_data.py --apply               # 实际删除
    python scripts/clean_data.py --apply --keep-profiles  # 保留 browser_profile/<alias> 持久登录态

安全:
    - 只动 data/ 目录。绝不碰 accounts/、.env(见 PRIVACY_CHECKLIST.md)
    - 默认 dry-run,必须显式 --apply 才真删
    - 删除前统计大小,删除后汇报
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 要整体删除的子目录(运行时 profile 残留 + 调试产物目录)
# browser_profile 是 config.browser.user_data_dir 的默认值(持久登录态):
#   - 默认(全清):删除
#   - --keep-profiles:保留(一次登录长期复用,免重登)
DIR_RESIDUE_PATTERNS = [
    "browser_profile",               # 默认持久 profile(75MB);--keep-profiles 保留
    "browser_profile_test",          # TC-17 测试 profile 残留(非 uuid 命名的旧版)
    "browser_profile_test_*",        # 24 个 uuid 命名的测试 profile
    "browser_profile_manual_backup", # 手动登录备份(155MB)
    "browser_profile_chrome",        # 真实 Chrome profile 实验
    "browser_profile_cookies",       # cookies 实验 profile
    "browser_profile_v3",            # v3 实验 profile
    "browser_profile_manual",        # 手动登录 profile(423MB);--keep-profiles 不保留此项
    "logs",                          # 日志目录
    "screenshots",                   # 截图目录
]

# 要删除的单文件(调试产物 + 临时 cookies + 临时 db + 日志)
FILE_RESIDUE_PATTERNS = [
    "apply_page_*.html",
    "apply_page_*.png",
    "debug_*.html",
    "debug_*.png",
    "job_detail_*.html",
    "jobsdb_page.html",
    "jobsdb_screenshot.png",
    "review_page_debug.png",
    "auto_apply.log",
    "v2_apply*.log",
    "cookies.json",
    "cookies_chrome.json",
    "cookies_default.json",
    "playwright_cookies.json",
    "playwright_localstorage.json",
    "jobsdb.db",
    "jobsdb_e2e.db",
    "applications.json",      # 运行时缓存(空文件)
    ".DS_Store",
]

# --keep-profiles 时额外保留的目录(持久登录态:一次登录长期复用)
KEEP_PROFILES = ["browser_profile"]


def _dir_size(path: Path) -> int:
    """递归计算目录大小(字节)。"""
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    try:
        for child in path.rglob("*"):
            if child.is_file():
                with contextlib.suppress(OSError):
                    total += child.stat().st_size
    except OSError:
        pass
    return total


def _human(size: int) -> str:
    """字节 → 人类可读。"""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _collect_targets(keep_profiles: bool) -> tuple[list[Path], list[Path]]:
    """收集要删除的目录和文件。返回 (dirs, files)。"""
    if not DATA_DIR.exists():
        return [], []

    dirs: list[Path] = []
    files: list[Path] = []

    keep_set = set(KEEP_PROFILES) if keep_profiles else set()

    # 目录
    for pattern in DIR_RESIDUE_PATTERNS:
        for match in DATA_DIR.glob(pattern):
            if not match.is_dir():
                continue
            if match.name in keep_set:
                continue
            dirs.append(match)

    # 文件
    for pattern in FILE_RESIDUE_PATTERNS:
        for match in DATA_DIR.glob(pattern):
            if match.is_file():
                files.append(match)

    # 去重(glob 可能重叠)
    dirs = sorted(set(dirs))
    files = sorted(set(files))

    return dirs, files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="清理 data/ 运行时残留(默认 dry-run)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="实际执行删除(默认只列出)",
    )
    parser.add_argument(
        "--keep-profiles", action="store_true",
        help="保留 browser_profile/<alias> 持久登录态(只清测试/debug 产物)",
    )
    args = parser.parse_args()

    if not DATA_DIR.exists():
        print(f"data/ 不存在: {DATA_DIR}")
        return 0

    dirs, files = _collect_targets(keep_profiles=args.keep_profiles)

    if not dirs and not files:
        print("data/ 已干净,无残留可清。")
        return 0

    total_size = sum(_dir_size(d) for d in dirs) + sum(f.stat().st_size for f in files)

    mode = "APPLY(实际删除)" if args.apply else "DRY-RUN(只列出,加 --apply 才真删)"
    print(f"模式: {mode}")
    print(f"保留持久 profile: {'是(--keep-profiles)' if args.keep_profiles else '否'}")
    print(f"data/ 目录: {DATA_DIR}")
    print(f"待清理: {len(dirs)} 个目录, {len(files)} 个文件, 共 {_human(total_size)}")
    print("-" * 60)

    if dirs:
        print("目录:")
        for d in dirs:
            print(f"  {_human(_dir_size(d)):>8}  {d.name}")
    if files:
        print("文件:")
        for f in files:
            try:
                print(f"  {_human(f.stat().st_size):>8}  {f.name}")
            except OSError:
                print(f"  {'?':>8}  {f.name}")

    print("-" * 60)

    if not args.apply:
        print("DRY-RUN: 未删除任何内容。加 --apply 执行。")
        return 0

    # 实际删除
    deleted_dirs = deleted_files = 0
    for d in dirs:
        try:
            shutil.rmtree(d)
            deleted_dirs += 1
        except OSError as e:
            print(f"  [失败] 目录 {d.name}: {e}", file=sys.stderr)

    for f in files:
        try:
            f.unlink()
            deleted_files += 1
        except OSError as e:
            print(f"  [失败] 文件 {f.name}: {e}", file=sys.stderr)

    print(f"已删除: {deleted_dirs} 目录, {deleted_files} 文件, 释放 {_human(total_size)}")
    print(f"data/ 剩余大小: {_human(_dir_size(DATA_DIR))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
