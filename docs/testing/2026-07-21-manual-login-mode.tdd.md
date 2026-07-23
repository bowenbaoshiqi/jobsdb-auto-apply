# TDD 证据报告：手动登录模式（Manual Login Mode）

- **日期**: 2026-07-21
- **源设计**: `docs/superpowers/specs/2026-07-21-manual-login-mode-design.md`
- **分支**: `feature/v2.0`
- **提交序列**: `573cf8f`(RED) → `751b399`(GREEN) → `5b47201`(factory+CLI) → `c69fd24`(清理) → `87663de`(gitignore)

## 1. 用户旅程

来源：设计文档 brainstorming 阶段产出。

1. **作为用户**，我想用持久化浏览器 profile 一次手动登录、长期复用，**这样**不必每次投递都输密码/过验证码，降低风控风险。
2. **作为用户**，我想用 `--login-mode manual` 启动投递，**这样**程序打开浏览器等我登录，登录后自动接管投递。
3. **作为开发者**，我想把三份临时 monkeypatch 脚本收编成正式配置项，**这样**登录策略由 `config.login.mode` 统一管理，不再靠脚本 hack。
4. **作为开发者**，我想清掉 `data/` 下 ~852MB 测试残留并防止再堆积，**这样**仓库 lean、隐私干净。

## 2. 任务报告

### Task 1: `LoginHandler` 支持 manual 模式

- **执行摘要**: `ensure_logged_in` 按 `config.login.mode` 分支；新增 `_do_login_manual`（被动轮询 `_is_logged_in` + logger 通知 + 超时返回 False）与 `_backup_session_cookies`（备份 jobsdb/seek 域 cookies）。manual 模式绕过 `_get_credentials`，不要求凭证。
- **验证命令**: `uv run pytest tests/unit/test_login_manual.py -v`
- **RED 证据**: `AttributeError: 'LoginHandler' object has no attribute 'login_config'`（commit `573cf8f`）
- **GREEN 证据**: `9 passed`（commit `751b399`）
- **测试保证**: manual 模式不调 `_get_credentials`、轮询命中后备份 cookies、超时返回 False 不抛异常、auto 模式无凭证仍抛 `LoginError`（TC-15 回归保护）、`login_config` 默认 auto（向后兼容）。

### Task 2: 工厂透传 `login_config`

- **执行摘要**: `ComponentFactory.create_login_handler` 增 `login_config` 参数（默认 None→auto）；`DefaultFactory`/`FakeFactory` 同步透传；`Orchestrator._init_browser` 传 `self.config.login`。
- **验证命令**: `uv run pytest tests/unit/test_factory.py tests/unit/test_orchestrator.py -v`
- **GREEN 证据**: `29 passed`（含 2 个新 factory 用例）
- **测试保证**: `login_config` 透传到 `LoginHandler.login_config`；不传时默认 auto。

### Task 3: CLI `--login-mode` 旗标

- **执行摘要**: `src/main.py start` 增 `--login-mode {auto,manual}`，覆盖 `config.login.mode`；manual 模式强制 headed。
- **验证命令**: `uv run python -m src.main start --help`
- **证据**: help 输出含 `--login-mode <str>` 及说明。
- **保证**: CLI 旗标优先于配置文件；manual 自动禁用 headless。

### Task 4: 清理脚本与残留

- **执行摘要**: 删除 3 份 untracked `run_v2_apply*.py`；新增 `scripts/clean_data.py`（dry-run/apply/keep-profiles）；`--apply --keep-profiles` 释放 709.9MB。
- **验证命令**: `uv run python scripts/clean_data.py`（dry-run）；`du -sh data/`
- **证据**: `data/` 从 852MB → 75MB（仅保留 `browser_profile` 持久登录态）；`accounts/`、`.env` 未触碰。
- **保证**: 清理只动 `data/`，隐私红线（accounts/.env）不破；`--keep-profiles` 保留默认账户登录态。

### Task 5: `.gitignore` 加固

- **执行摘要**: 增 debug 产物模式 + `run_v2_apply*.py` 模式。
- **验证命令**: `git check-ignore run_v2_apply_test_ignore.py` / `git check-ignore debug_foo.png`
- **证据**: 两者均被忽略；`.env.example` 不被忽略。
- **保证**: 防止临时脚本与调试产物误入仓。

## 3. 测试规格（保证清单）

| # | 保证 | 测试 | 类型 | 结果 | 证据 |
|---|------|------|------|------|------|
| 1 | `login_config` 默认 auto（两参构造向后兼容） | `test_login_config_defaults_to_auto` | unit | PASS | `tests/unit/test_login_manual.py` |
| 2 | manual + 已登录 → 返回 True，不要求凭证 | `test_manual_mode_no_credentials_succeeds_when_logged_in` | unit | PASS | 同上 |
| 3 | manual + 无凭证 → 不调 `_get_credentials` | `test_manual_mode_does_not_call_get_credentials` | unit | PASS | 同上 |
| 4 | manual + 首次未登录 → 轮询直到 `_is_logged_in` 命中 | `test_manual_mode_polls_until_logged_in` | unit | PASS | 同上 |
| 5 | manual + 超时 → 返回 False（不抛异常） | `test_manual_mode_timeout_returns_false` | unit | PASS | 同上 |
| 6 | manual 超时不抛 `LoginError`（Orchestrator 不误吞） | `test_manual_mode_timeout_does_not_raise_login_error` | unit | PASS | 同上 |
| 7 | `_backup_session_cookies` 只存 jobsdb/seek 域 | `test_manual_mode_backs_up_jobsdb_cookies` | unit | PASS | 同上 |
| 8 | manual 登录成功路径触发 cookie 备份 | `test_manual_login_path_calls_backup_on_success` | unit | PASS | 同上 |
| 9 | auto + 无凭证 → 抛 `LoginError`（TC-15 回归） | `test_auto_mode_still_requires_credentials` | unit | PASS | 同上 |
| 10 | factory 透传 `login_config` | `test_create_login_handler_propagates_login_config` | unit | PASS | `tests/unit/test_factory.py` |
| 11 | factory 不传 `login_config` 默认 auto | `test_create_login_handler_defaults_to_auto_without_login_config` | unit | PASS | 同上 |
| 12 | 全量回归无破坏 | 全套 `pytest -m "not e2e and not integration"` | unit+char | PASS | 309 passed, 1 skipped |
| 13 | touched files lint 零告警 | `ruff check src/main.py src/factory.py src/orchestrator.py src/jobsdb/login.py tests/unit/test_login_manual.py tests/unit/test_factory.py scripts/clean_data.py` | lint | PASS | All checks passed |

## 4. 覆盖率与已知缺口

- **验证命令**: `uv run pytest -m "not e2e and not integration" --cov=src --cov-report=term`
- **总覆盖率**: **67.52%**（超过 60% 门槛）
- **`src/jobsdb/login.py`**: 49% — 未覆盖的是 `_do_login` auto 路径（lines 157-272，v1.0 遗留逻辑，由 e2e/integration 测试覆盖，CI 不跑）。**本次新增的 `_do_login_manual` / `_backup_session_cookies` / `ensure_logged_in` 分支均已覆盖。**
- **已知缺口（非目标，见设计 Section 10）**:
  - manual 模式 e2e（真人登录）归入 `tests/e2e/test_e2e_live.py`，CI 不跑
  - 真实 Chrome profile 方案（`run_v2_apply_chrome.py` 的系统 Chrome 目录 hack）未收编，另立议题
  - `scripts/auto_apply.py`（v1.0 遗留，30 个 lint 告警）未动，超出本次范围

## 5. 调试过程中诊断的根因（供复盘）

实施中 3 个测试失败，经 systematic-debugging 诊断出两个真实根因（非实现 bug）：

1. **`LoginConfig.manual_wait_minutes` 是 `int`**，测试误传 `0.01`（float）被 pydantic 拒。修正：用 `manual_wait_minutes=1`（int）+ 极小 `poll_interval_seconds` + no-op `asyncio.sleep`。
2. **`ensure_logged_in` 的"已登录短路"在 `_do_login_manual` 之前**：page 预设 logged_in=True 时，预检循环就返回 True，备份永远不触发。修正：cookie 备份改直接测 `_backup_session_cookies`（纯单元）+ 端到端用阈值 `>=4`/`>=5` 确保控制流真正进入 manual 路径。

这两个修正反映的是**测试设计对控制流的误判**，实现本身正确（已登录短路不备份是设计——`BrowserEngine.stop` 统一保存）。

## 6. 合并证据

若 squash 合并，保留以下 RED/GREEN 摘要：

- **RED** (`573cf8f`): 7 用例，`AttributeError: 'LoginHandler' object has no attribute 'login_config'`
- **GREEN** (`751b399`): 9 passed（含诊断后修正的 2 个用例）
- **factory+CLI** (`5b47201`): 29 passed（factory+orchestrator）
- **全量回归**: 309 passed, 1 skipped, 67.52% coverage, touched files ruff 零告警
