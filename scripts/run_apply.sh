#!/usr/bin/env bash
# 启动 JobsDB 投递会话(前台浏览器,manual 登录模式,复用已登录 profile)。
# 用法: scripts/run_apply.sh [职位数,默认 5]
# 由 /start-apply skill 调用;一般后台运行并 tail 日志盯关键标记。
set -u
cd "$(dirname "$0")/.."

N="${1:-5}"
case "$N" in
  ''|*[!0-9]*) echo "职位数必须是正整数,收到: '$N'" >&2; exit 2 ;;
esac

# 跑前检查:登录 cookies 必须存在(manual 模式复用已登录会话)
if [ ! -s data/cookies_default.json ]; then
  echo "⚠️ data/cookies_default.json 不存在或为空 — 可能未登录,投递会全部失败" >&2
  exit 3
fi

echo ">>> 启动投递:max-jobs=$N (login-mode=manual, headless=False)"
exec uv run python -m src.main --verbose start --login-mode manual --max-jobs "$N"
