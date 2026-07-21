# JobsDB 简历智能投递助手

模拟人类行为的自动化简历投递系统，针对 JobsDB HK (jobsdb.com/hk)。

## ✨ 特性

- 🤖 **模拟人类行为**：Bezier 曲线鼠标移动、自然滚动、拟人打字
- 🛡️ **多层反检测**：浏览器指纹伪装、时序随机化、持久化会话
- 🎯 **智能识别**：自动检测 Quick Apply / 快速申请按钮，跳过普通申请
- 📝 **自动处理 Cover Letter**：自动选择 "Don't include a cover letter"
- 📊 **实时监控**：终端仪表盘展示投递进度和统计
- 🔄 **智能调度**：频率控制、最佳投递时机优化
- 💾 **状态持久化**：SQLite 数据库记录投递历史
- ⚠️ **异常处理**：验证码检测、自动重试、优雅降级
- 👥 **多账户支持**：账户隔离，独立浏览器 profile

## 🚀 快速开始

### 1. 安装依赖

本项目用 [uv](https://docs.astral.sh/uv/) 管理依赖（v2.0 起推荐）：

```bash
# 用 uv(推荐)
uv venv
uv pip install -e ".[dev]"
uv pip install pytest-cov
uv run playwright install chromium

# 或用 pip(向后兼容)
pip install -e ".[dev]"
playwright install chromium
```

### 2. 添加账户

```bash
# 添加一个账户（交互式输入密码）
python -m src.main account add personal --email your-email@example.com

# 列出所有账户
python -m src.main account list

# 切换到指定账户
python -m src.main account use personal

# 查看当前活跃账户
python -m src.main account show
```

### 3. 配置（可选：单账户向后兼容）

如果你不想用多账户，也可以保留传统的 `.env` 配置：

```bash
cp .env.example .env
# 编辑 .env 填入你的 JobsDB 邮箱和密码
```

### 4. 开始投递

```bash
# 使用生产脚本投递（推荐）
python scripts/auto_apply.py 5

# 或使用 CLI 投递
python -m src.main start --max-jobs 5

# 查看统计
python -m src.main stats

# 查看会话历史
python -m src.main sessions
```

## 📁 项目结构

```
resume/
├── src/                    # 核心源码
│   ├── browser/            # 浏览器抽象层
│   │   ├── ports/          # BrowserPort + PageController 接口(Protocol)
│   │   ├── fake/           # 内存假实现(单测用,不起浏览器)
│   │   ├── playwright_*.py # Playwright 生产实现
│   │   └── stealth.py      # 反指纹
│   ├── jobsdb/             # JobsDB 交互层(只依赖 ports,不依赖 Playwright)
│   │   ├── apply/          # 投递状态机(flow.py + steps/ + detectors.py)
│   │   ├── login.py / homepage.py / job_detail.py
│   │   └── selectors.py    # CSS 选择器集中管理
│   ├── simulation/         # 人类行为模拟
│   ├── scheduler/          # 调度与队列
│   ├── monitor/            # 监控与仪表板
│   ├── storage/            # 数据存储(SQLite + cookies)
│   ├── accounts/           # 多账户管理
│   ├── factory.py          # ComponentFactory(DI: DefaultFactory + FakeFactory)
│   └── orchestrator.py     # 协调器(通过工厂注入 10 个依赖)
├── scripts/                # 生产脚本
│   └── auto_apply.py       # 自动投递主脚本
├── config/                 # 配置文件
├── tests/                  # 测试(三分类: unit / characterization / e2e)
└── data/                   # 运行时数据（gitignore）
```

## 🏗️ v2.0 架构（TDD 重构）

v2.0 是一次纯重构：**投递行为与 v1.0 完全一致**，但内部结构按 TDD 重写，目标是降低耦合、增强健壮性。采用 Strangler Fig 模式分 6 阶段渐进迁移，v1.0 全程可用。

### 核心改进

1. **浏览器抽象层（依赖反转）**
   - `BrowserPort` + `PageController` 用 Protocol 定义接口
   - `jobsdb/*` 只依赖 `PageController` 接口，**不再 import Playwright 的 `Page`**
   - 生产用 `PlaywrightPageController`，测试用 `FakePageController`（毫秒级，不起浏览器）

2. **工厂模式依赖注入**
   - `ComponentFactory`（Protocol，10 个 create 方法）生产 `Orchestrator` 的全部依赖
   - `DefaultFactory` 生产真实组件，`FakeFactory` 生产内存假组件
   - `Orchestrator` 不再硬编码 `new` 依赖，单测可注入 `FakeFactory` 全程不起浏览器、不落盘

3. **投递流程状态机拆分**
   - v1.0 的 543 行 `apply_flow.py` God Object 拆成 `apply/` 包
   - `flow.py` 状态机 + `steps/` 下 7 个 `StepHandler`（每个独立可测）+ `detectors.py` 纯查询函数

4. **异常三分法**
   - A 类（重试）：`RateLimitError` 等可恢复异常
   - B 类（降级）：cookie banner 关闭失败等非阻断异常，记日志继续
   - C 类（上抛）：`CaptchaDetectedError` / `SessionExpiredError` 等终止性异常
   - **清零** v1.0 的 8 处 `except Exception: pass` 静默吞错

### 测试三分类

| 分类 | 标记 | 用途 | CI |
|---|---|---|---|
| unit | `@pytest.mark.unit` | 纯单元测试，用 FakePageController，毫秒级 | ✅ 必跑 |
| characterization | `@pytest.mark.characterization` | 锁定 v1.0 行为的安全网（重构前先写） | ✅ 跑 |
| e2e | `@pytest.mark.e2e` | 真实 JobsDB + 手动登录，慢 | ❌ 默认跳过 |

```bash
# 默认跑 unit + characterization（不起浏览器）
uv run pytest

# 只跑单测
uv run pytest -m unit

# 跑全部(含 e2e,需要真实环境)
uv run pytest -m ''

# 带覆盖率(pyproject 卡 fail_under=60,当前 65%)
uv run pytest --cov=src --cov-report=term-missing

# lint
uv run ruff check src/ tests/
```

详见 [v2.0 设计文档](docs/superpowers/specs/2026-07-20-v2.0-design.md) 和 [实现计划](docs/superpowers/plans/2026-07-20-v2.0-implementation.md)。

## 🛡️ 反检测策略

1. **浏览器指纹伪装**：通过 Playwright 注入 JS patches 隐藏自动化标记
2. **拟人化交互**：鼠标移动遵循 Bezier 曲线，打字有随机延迟和错误
3. **会话持久化**：复用浏览器 profile，模拟回访用户
4. **频率控制**：保守策略（每小时 ≤10 次，每天 ≤30 次，间隔 ≥3 分钟）
5. **异常检测响应**：遇到验证码暂停等手动解决

## 👥 账户隔离

每个账户有完全独立的运行环境：

| 资源 | 隔离路径 |
|---|---|
| 浏览器 Profile | `data/browser_profile/<alias>/` |
| Cookies | `data/cookies_<alias>.json` |
| 投递记录 | 数据库中的 `account_id` 字段 |
| 会话历史 | 数据库中的 `account_id` 字段 |
| 日志 | `data/logs/<alias>/` |

切换账户相当于一个全新的浏览器身份，反检测性最佳。

## 🔒 安全说明

**本仓库永远不会包含你的真实凭证。**

- `accounts/`（已在 `.gitignore`）——仅保存在你的本地环境
- `data/`（已在 `.gitignore`）——运行时数据（profile、cookies、数据库、截图、日志）
- `.env`（已在 `.gitignore`）——单账户模式的旧版配置
- 请确保提交 `git push` 前检查 `git status`，确认上述目录不在变更列表中

详细隐私保护清单请查看 [PRIVACY_CHECKLIST.md](PRIVACY_CHECKLIST.md)

## 📋 功能说明

### 自动识别职位类型

脚本会自动识别 JobsDB 上的两种职位：

1. **Quick Apply / 快速申请** → 自动投递
2. **Apply / 申请**（跳外部网站）→ 自动跳过

### Cover Letter 自动处理

遇到 Cover Letter 选择页面时，脚本会自动：
1. 检测 "Don't include a cover letter" 选项
2. 选择该选项并触发 change 事件
3. 自动点击 Continue 继续流程

### 需要人工干预的情况

以下情况会弹出 macOS 系统通知，等待你手动处理：
- 验证码 / CAPTCHA
- 需要填写额外信息的复杂表单
- 登录状态过期

## ⚠️ 注意事项

- 首次运行会打开浏览器窗口（headed 模式），请手动解决可能出现的验证码
- 程序会逐渐学习用户登录状态，后续运行无需频繁重新登录
- 请遵守 JobsDB 使用条款，合理使用自动化工具
- 建议每次投递数量不要过多，避免账号被限制

## 📝 更新日志

### v2.0.0 (2026-07-20) — TDD 重构

- ✅ 浏览器抽象层：`BrowserPort` + `PageController`（Protocol），`jobsdb/*` 解耦 Playwright
- ✅ 工厂模式 DI：`ComponentFactory` 注入 Orchestrator 的 10 个依赖，`FakeFactory` 支持不起浏览器单测
- ✅ 投递流程状态机拆分：543 行 God Object → `apply/` 包（flow + 7 个 StepHandler + detectors）
- ✅ 异常三分法（A 重试 / B 降级 / C 上抛），清零 8 处 `except: pass`
- ✅ 测试三分类（unit / characterization / e2e），覆盖率 39% → 65%
- ✅ ruff lint 清零（221 → 0），CI 启用 lint + 覆盖率门槛
- ✅ uv 环境支持，修复多个 v1.0 latent bug（apply_flow 缺 `import random`、main.py 缺 `os/Path` import 等）
- ⚠️ **投递行为与 v1.0 完全一致**，无新功能

### v0.1.0 (2026-07-20)

- ✅ 自动识别 Quick Apply / 快速申请按钮
- ✅ 自动跳过普通申请（跳外部网站的职位）
- ✅ 自动处理 Cover Letter 页面（选择 "Don't include a cover letter"）
- ✅ 多账户隔离支持
- ✅ 完整的反检测策略
- ✅ 投递历史记录和统计

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License
