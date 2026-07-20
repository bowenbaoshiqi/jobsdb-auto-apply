# 隐私保护检查清单

在提交到 GitHub 之前，请确认以下敏感信息**没有被上传**：

## ❌ 绝对不上传的内容

- [ ] `.env` 文件（包含 JOBSDB_EMAIL 和 JOBSDB_PASSWORD）
- [ ] `accounts/` 目录下的所有 JSON 文件（包含真实账号密码）
- [ ] `data/` 目录下的所有内容：
  - `browser_profile*/` - 浏览器 profile（包含登录状态、cookies、浏览历史）
  - `cookies*.json` - 登录 cookies
  - `*.db` / `*.sqlite` - 数据库（包含投递记录）
  - `*.png` / 截图 - 可能包含个人信息
  - `*.log` / 日志 - 可能包含账号信息
  - `auto_apply.log` - 投递日志

## ✅ 可以上传的内容

- 源代码 (`src/`, `config/`, `scripts/`, `tests/`)
- 配置文件模板 (`.env.example`, `config/defaults.yaml`)
- 文档 (`README.md`)
- 依赖配置 (`pyproject.toml`)
- 示例账户文件 (`accounts/example.json` - 不含真实密码)

## 🔒 已配置的保护措施

`.gitignore` 已配置忽略：
- `.env*` - 环境变量文件
- `data/` - 所有运行时数据
- `accounts/` - 账户凭证（但保留 `example.json`）
- `*.log` - 日志文件
- `__pycache__/` - Python 缓存

## 📝 首次使用说明

新用户克隆仓库后需要：

1. 复制环境变量模板：
   ```bash
   cp .env.example .env
   # 编辑 .env 填入你的 JobsDB 账号密码
   ```

2. 添加账户（推荐）：
   ```bash
   python -m src.main account add personal --email your-email@example.com
   ```

3. 安装依赖：
   ```bash
   pip install -e ".[dev]"
   playwright install chromium
   ```

4. 开始投递：
   ```bash
   python scripts/auto_apply.py 5
   ```
