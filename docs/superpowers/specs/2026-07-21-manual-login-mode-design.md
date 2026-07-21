# 手动登录模式（Manual Login Mode）设计文档

- **日期**: 2026-07-21
- **状态**: 待审阅
- **作者**: brainstorming 协作产出
- **范围**: 把 v1.0 的手动登录流程收编成正式能力（`login.mode` 配置开关），并清理三份临时脚本与 `data/` 运行时残留

## 1. 目标与背景

### 1.1 目标

v2.0 重构完成后，三份 `run_v2_apply*.py` 临时验证脚本靠 monkeypatch `LoginHandler._do_login` 实现"等用户手动登录"。本设计将其收编为正式能力：

1. **`LoginHandler` 支持 manual 模式** — 被动轮询 + 通知 + 超时，由 `config.login.mode: auto|manual` 切换
2. **激活已存在但闲置的 `LoginConfig`** — `login.mode` / `manual_wait_minutes` / `poll_interval_seconds` 已在 `defaults.yaml` 与 `settings.py` 中定义，但从未被源码读取
3. **CLI 可达** — `src/main.py start` 增加 `--login-mode` 旗标
4. **清理残留** — 删除三份 `run_v2_apply*.py` 与 `data/` 下 ~852MB 运行时残留，加固 `.gitignore`，新增 `scripts/clean_data.py` 防止再次堆积

### 1.2 现状诊断

| 事实 | 位置 |
|---|---|
| `LoginConfig` 已定义（mode/manual_wait_minutes/poll_interval_seconds）但**零读取** | `config/settings.py:37-53`、`config/defaults.yaml:22-25` |
| `LoginConfig` 已挂进 `AppConfig.login`，但无源码引用 `config.login` | `config/settings.py:127` |
| `PageController.get_cookies()` 已存在 | `src/browser/ports/page_controller.py:55` |
| 三份脚本各自 monkeypatch `_do_login`，三种检测策略 | `run_v2_apply.py`（cookie 名白名单）、`run_v2_apply_manual.py`（body 文本 + 选择器）、`run_v2_apply_chrome.py`（信任真实 Chrome profile） |
| `data/` 全部 untracked（含 `.gitkeep`），852MB 纯运行时残留 | 24 个 `browser_profile_test_*`（uuid 命名，TC-17 残留）、`browser_profile_manual`（423MB）、`browser_profile_manual_backup`（155MB）、`browser_profile_chrome`（30MB）+ debug HTML/PNG/log/db |
| `src/main.py start` 无 `--login-mode` 旗标 | `src/main.py:52-66` |

### 1.3 决策汇总（brainstorming 阶段已定）

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 推进方式 | Approach A：在 `ensure_logged_in` 内按 `config.login.mode` 分支 |
| 2 | 检测策略 | 统一复用现有 `_is_logged_in()`（DRY） |
| 3 | 凭证要求 | manual 模式**不要求** email/password，绕过 `_get_credentials` |
| 4 | 通知方式 | 仅 logger，不做 OS 通知（全平台可移植） |
| 5 | 清理范围 | 擦除全部运行时残留 + gitignore 加固 + `scripts/clean_data.py` |
| 6 | CLI | `src/main.py start` 增 `--login-mode {auto,manual}` 旗标，覆盖配置 |
| 7 | 配置字段 | 不新增字段——激活已存在的 `LoginConfig` 三项 |

## 2. 架构

### 2.1 分支点：`ensure_logged_in`

```
ensure_logged_in():
    # 1. 导航到首页（两模式共用，不变）
    navigate to homepage if on about:blank / not jobsdb
    # 2. 先查是否已登录（两模式共用，持久化 profile 的关键短路）
    for attempt in range(3):
        if await self._is_logged_in():
            return True                      # 已登录，跳过等待
        await asyncio.sleep(3)
    # 3. 按模式分支
    if self.login_config.mode == "manual":
        return await self._do_login_manual()
    return await self._do_login()            # auto 路径，完全不变
```

**关键：** "已登录"短路在两模式中都先跑——持久化 profile 里若有有效 session，直接跳过等待。这正是"一次登录长期复用"的收益来源。

### 2.2 为何不改 Orchestrator / factory / Port

- **Orchestrator**：调用 `login_handler.ensure_logged_in()`，接口不变
- **factory**：`create_login_handler` 多传一个 `login_config` 参数，工厂已有 `self.config`（完整 `AppConfig`）
- **Port**：`get_cookies()` 已存在，手动模式所需原语齐备

→ 最小爆炸半径：只动 `LoginHandler`、`ComponentFactory.create_login_handler` 签名、两份工厂实现、`main.py`。

## 3. 组件设计

### 3.1 `LoginHandler` 改动

**`__init__` 新增参数：**

```python
def __init__(self, page: PageController, config: JobsDBConfig,
             human: Optional[HumanSimulator] = None,
             account: Optional[Account] = None,
             login_config: Optional[LoginConfig] = None):
    ...
    self.login_config = login_config or LoginConfig()  # 默认 auto，向后兼容
```

- `login_config` 默认 `None` → 退化为 `LoginConfig()`（mode="auto"），**保证现有测试与 v1.0 行为不变**。TC-15（`test_tc15_no_credentials_raises_error`）用 `LoginHandler(page, config)` 两参构造，仍走 auto 路径，仍抛 `LoginError`。

**新增 `_do_login_manual`：**

```python
async def _do_login_manual(self) -> bool:
    """手动登录：导航到登录页 → logger 通知 → 被动轮询 _is_logged_in → 超时。

    不主动 goto（避免打断用户输密码/过验证码），登录成功后 JobsDB 自动跳首页，
    此时 _is_logged_in 命中 → 备份 cookies → 导航首页 → 返回 True。
    全程不要求凭证。
    """
    # 导航到登录页给用户起点
    await self.page.goto(self.config.login_url, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    # 再查一次（可能 profile 自带登录态）
    if await self._is_logged_in():
        logger.info("Manual login: already logged in, backing up cookies")
        await self._backup_session_cookies()
        return True

    wait_min = self.login_config.manual_wait_minutes
    interval = self.login_config.poll_interval_seconds
    deadline_iters = int(wait_min * 60 / interval)

    logger.warning(
        f"请在当前浏览器窗口登录 JobsDB（可处理验证码，程序不会刷新页面）。"
        f"等待手动登录...（最多 {wait_min} 分钟，每 {interval}s 检查一次）"
    )

    for attempt in range(deadline_iters):
        await asyncio.sleep(interval)
        try:
            if await self._is_logged_in():
                logger.info("检测到已登录，备份 cookies")
                await self._backup_session_cookies()
                # 登录后稳定，导航到首页开始投递
                await asyncio.sleep(2)
                await self.page.goto(self.config.homepage_url, wait_until="domcontentloaded")
                await asyncio.sleep(3)
                return True
            if attempt % 4 == 0:
                logger.info(
                    f"仍在等待登录... ({(attempt + 1) * interval / 60:.1f} 分钟) URL: {self.page.url}"
                )
        except Exception as e:
            # 三分法 B 类：降级——检查异常不阻断等待，不跳页
            logger.debug(f"登录检查异常（继续等，不跳页）: {e}")

    logger.error(f"等待手动登录超时（{wait_min} 分钟）")
    return False
```

**新增 `_backup_session_cookies`（收编自脚本，统一用 `config.storage.cookies_file`）：**

```python
async def _backup_session_cookies(self) -> int:
    """登录成功后备份 jobsdb/seek 域 cookies 到配置的 cookies_file。"""
    try:
        all_cookies = await self.page.get_cookies()
        session_cookies = [
            c for c in all_cookies
            if "jobsdb" in c.get("domain", "") or "seek" in c.get("domain", "")
        ]
        # 用 account.alias 隔离（与 BrowserEngine.cookie_store 一致）
        alias = self.account.alias if self.account else "default"
        from src.storage.cookies import CookieStore
        CookieStore(f"./data/cookies_{alias}.json").save(session_cookies)
        logger.info(f"已备份 {len(session_cookies)} 个 JobsDB cookies")
        return len(session_cookies)
    except Exception as e:
        # 非阻断
        logger.warning(f"cookies 备份失败（非阻断）: {e}")
        return 0
```

> 注：`_backup_session_cookies` 用 `self.page.get_cookies()`（PageController 接口），不直接碰 `page.context.cookies()`——保持与 v2.0 解耦一致。`CookieStore` 导入放在方法内，避免模块顶层循环依赖风险（沿用脚本写法）。

### 3.2 `factory` 改动

`ComponentFactory.create_login_handler` 签名加 `login_config`，两份实现同步传参：

```python
# Protocol
def create_login_handler(self, page, config, human, account,
                         login_config) -> LoginHandler: ...

# DefaultFactory / FakeFactory
def create_login_handler(self, page, config, human, account, login_config):
    return LoginHandler(page, config, human, account, login_config=login_config)
```

`Orchestrator._init_browser` 调用处改为：

```python
self.login_handler = self.factory.create_login_handler(
    self.page_controller, self.config.jobsdb, self.human, self.account,
    login_config=self.config.login,
)
```

### 3.3 `src/main.py` 改动

`start` 命令增 `--login-mode` 旗标，覆盖配置：

```python
@app.command()
def start(
    account: Optional[str] = typer.Option(None, "--account", "-a", ...),
    max_jobs: int = typer.Option(None, "--max-jobs", "-m", ...),
    headless: bool = typer.Option(False, "--headless", "-h", ...),
    login_mode: Optional[str] = typer.Option(
        None, "--login-mode",
        help="登录模式: auto(自动填密码) / manual(等用户手动登录)。覆盖 config.login.mode",
    ),
):
    config = get_config()
    ...
    if login_mode:
        config.login.mode = login_mode      # pydantic validator 会校验 auto|manual
    if config.login.mode == "manual":
        config.browser.headless = False     # manual 必须 headed
    ...
```

启动面板增加 `Login mode: {mode}` 显示行。

### 3.4 不改的东西

- `_do_login()`（auto 路径）—— 完全不动
- `_is_logged_in()` —— 复用，不改
- `_get_credentials()` —— auto 路径仍用它；manual 路径不调用它
- `Orchestrator.run()` 主循环 —— 不动
- `BrowserEngine` —— 不动（脚本里 `_patched_start` 那套真实 Chrome profile hack **不收编**，超出本次范围；真实 Chrome profile 方案另立议题）

## 4. 数据流

### 4.1 manual 模式时序

```
用户: python -m src.main start --login-mode manual
  → main: config.login.mode = "manual", headless = False
  → Orchestrator.run
    → _init_browser: PlaywrightBrowser 起持久化 profile（data/browser_profile/<alias>）
    → _ensure_login → ensure_logged_in:
        导航首页 → _is_logged_in()?
          ├─ True（profile 自带有效 session）→ 备份 cookies → 返回 True（零等待）
          └─ False → _do_login_manual:
               导航登录页 → logger.warning 通知
               循环（每 poll_interval_seconds 秒）: _is_logged_in()?
                 ├─ True → 备份 cookies → 导航首页 → 返回 True
                 └─ False → 继续（超时则返回 False）
    → _scrape_jobs → _process_queue（投递）
    → _cleanup: BrowserEngine.stop 保存 cookies
```

### 4.2 cookie 流转

- **读**：`BrowserEngine._load_cookies`（启动时从 `cookies_<alias>.json` 注入）——已有，不变
- **写**：两处
  1. `_do_login_manual` 登录成功后 `_backup_session_cookies`（新增，主动备份 jobsdb 域）
  2. `BrowserEngine.stop` 的 `_save_cookies`（已有，全量保存）
- 持久化 profile（`data/browser_profile/<alias>/`）本身也跨重启保留登录态——cookies 文件是双保险

## 5. 错误处理

沿用 v2.0 三分法（见 `tests/TEST_PLAN.md`）：

| 异常类 | 处理 | 出处 |
|---|---|---|
| **B（降级）** cookie banner 关闭失败、`_get_login_error` 取不到、登录检查抛异常 | debug 日志，不阻断 | `_do_login_manual` 循环内 `except Exception` |
| **B（降级）** cookies 备份失败 | warning 日志，返回 0，不阻断登录成功 | `_backup_session_cookies` |
| **A（上抛）** 超时未登录 | 返回 False（不抛异常，让 Orchestrator 走 `_create_error_report("Login failed")`） | `_do_login_manual` 末尾 |
| **C（上抛）** auto 路径的 `LoginError`/`CaptchaDetectedError` | 不变 | `_do_login`（未动） |

**关键：** manual 模式**不抛 `LoginError`**——超时返回 False，与 auto 模式"无凭证抛 LoginError"行为区分。这保证 `Orchestrator._ensure_login` 的 `except Exception` 兜底不会误吞 manual 超时。

## 6. 测试

遵循 TDD（先红后绿）。用 `FakePageController` 注入，不起浏览器。

### 6.1 新增单元测试 `tests/unit/test_login_manual.py`

| 测试 | 验证 |
|---|---|
| `test_manual_mode_no_credentials_succeeds_when_logged_in` | manual 模式 + profile 已登录 → `_is_logged_in` 命中 → 返回 True，**不要求凭证**，不进轮询 |
| `test_manual_mode_polls_until_logged_in` | manual 模式 + 首次未登录 → 轮询 N 次后 `_is_logged_in` 命中 → 返回 True；验证调用了 `_backup_session_cookies` |
| `test_manual_mode_timeout_returns_false` | manual 模式 + 永远未登录 + `manual_wait_minutes`/`poll_interval_seconds` 设极小 → 超时返回 False（不抛异常） |
| `test_manual_mode_does_not_call_get_credentials` | manual 模式 + 无 account/无 env 凭证 → 不抛 `LoginError`（auto 模式同条件会抛） |
| `test_auto_mode_still_requires_credentials` | auto 模式 + 无凭证 → 抛 `LoginError`（回归保护，TC-15 不破） |
| `test_manual_mode_backs_up_jobsdb_cookies` | 登录成功后 `cookies_<alias>.json` 含 jobsdb/seek 域 cookie |
| `test_login_config_defaults_to_auto` | `LoginHandler(page, config)` 不传 login_config → mode="auto" |

### 6.2 现有测试回归

- `tests/e2e/test_integration.py::TestLoginErrorHandling::test_tc15_no_credentials_raises_error` —— auto 模式仍抛 `LoginError`，**不破**
- `tests/unit/test_factory.py` —— `create_login_handler` 签名变了，需更新断言（传 `login_config`）
- `tests/unit/test_orchestrator.py` —— `FakeFactory.create_login_handler` 同步加参数

### 6.3 不新增 e2e

manual 模式的 e2e 需要真人登录，归入已有 `tests/e2e/test_e2e_live.py` 范畴（标记 `@pytest.mark.e2e`，CI 不跑）。本次只加单元测试。

## 7. 清理：脚本 + data/ 残留

### 7.1 删除三份脚本

```
run_v2_apply.py
run_v2_apply_chrome.py
run_v2_apply_manual.py
```

三份均 untracked（`??`），删除无 git 历史。它们的能力已被 `LoginHandler._do_login_manual` + `--login-mode manual` 取代。

### 7.2 擦除 `data/` 运行时残留

**全删**（852MB，全部 untracked）：

| 类别 | 内容 |
|---|---|
| 24 个测试 profile | `browser_profile_test_*`（uuid 命名，TC-17 残留） |
| 手动 profile | `browser_profile_manual`（423MB）、`browser_profile_manual_backup`（155MB） |
| 其他 profile | `browser_profile`、`browser_profile_chrome`、`browser_profile_cookies`、`browser_profile_test`、`browser_profile_v3` |
| debug 产物 | `apply_page_*.html/png`、`debug_*.html/png`、`job_detail_*.html`、`jobsdb_page.html`、`jobsdb_screenshot.png`、`review_page_debug.png` |
| 日志 | `auto_apply.log`、`v2_apply*.log`、`logs/` |
| 数据库 | `jobsdb.db`、`jobsdb_e2e.db` |
| cookies | `cookies.json`、`cookies_chrome.json`、`cookies_default.json`、`playwright_cookies.json`、`playwright_localstorage.json` |
| 其他 | `applications.json`（空）、`screenshots/`、`.DS_Store` |

**保留**：`data/.gitkeep`（结构占位）。

> ⚠️ **隐私红线**：清理只动 `data/` 目录。绝碰 `accounts/*.json`、`.env`（见 [[privacy-protection]]）。`accounts/` 与 `.env` 不在清理范围。

### 7.3 `.gitignore` 加固

当前 `.gitignore` 已有 `data/`（第 29 行）与 `*.log`（第 37 行）。补充更细的运行时产物规则，防止 `data/` 之外也漏入仓：

```gitignore
# 运行时数据（浏览器 profile、cookies、数据库、截图、日志）
data/
*.log

# 调试产物
debug_*.html
debug_*.png
*_screenshot.png
apply_page_*.html
apply_page_*.png
job_detail_*.html
review_page_debug.png

# 临时验证脚本（已收编为正式能力，禁止再建 run_v2_apply*.py）
run_v2_apply*.py
```

### 7.4 新增 `scripts/clean_data.py`

防止 `data/` 再次堆积 ~GB 残留。提供 `--dry-run` 与 `--keep-profiles`（保留 `browser_profile/<alias>` 持久登录态，只清测试/debug 产物）。

```python
"""清理 data/ 运行时残留。

用法:
  python scripts/clean_data.py              # 默认 dry-run，只列出要删的
  python scripts/clean_data.py --apply      # 实际删除
  python scripts/clean_data.py --apply --keep-profiles  # 保留 browser_profile/<alias>
"""
```

清理规则（与 7.2 一致）：删所有 `browser_profile_test_*`、`browser_profile_manual*`、`browser_profile_chrome`、`browser_profile_cookies`、`browser_profile_v3`、debug 产物、日志、cookies 临时文件、`.DS_Store`。`--keep-profiles` 时保留 `browser_profile/<alias>`。

## 8. 完成标准

| # | 标准 | 验证 |
|---|---|---|
| 1 | `login.mode=manual` 时 `LoginHandler` 不要求凭证、轮询 `_is_logged_in`、超时返回 False | 6.1 单元测试全绿 |
| 2 | `login.mode=auto` 时行为与 v1.0 完全一致（TC-15 不破） | 6.2 回归测试全绿 |
| 3 | `python -m src.main start --login-mode manual` 可启动并进入手动等待 | 人工 e2e |
| 4 | 三份 `run_v2_apply*.py` 已删 | `ls run_v2_apply*.py` 无输出 |
| 5 | `data/` 仅剩 `.gitkeep`（或 `--keep-profiles` 保留的 profile） | `du -sh data/` < 10MB |
| 6 | `.gitignore` 含运行时产物规则 | grep 校验 |
| 7 | `scripts/clean_data.py --dry-run` 正确列出残留 | 人工跑 |
| 8 | 全量 `pytest -m "not e2e and not integration"` 绿 | CI |
| 9 | `ruff check .` 零告警 | CI |

## 9. 实施顺序（供 writing-plans 展开）

1. **测试先行**：写 `tests/unit/test_login_manual.py`（红）
2. **`LoginHandler`**：加 `login_config` 参数 + `_do_login_manual` + `_backup_session_cookies`（绿）
3. **factory**：`create_login_handler` 签名 + 两份实现 + Orchestrator 调用处
4. **`main.py`**：`--login-mode` 旗标
5. **回归**：跑全量单测，修 `test_factory.py`/`test_orchestrator.py` 签名
6. **清理脚本**：删三份 `run_v2_apply*.py`
7. **清理 data/**：`scripts/clean_data.py` + 实际擦除
8. **`.gitignore`** 加固
9. **文档**：README 增 manual 模式说明、CHANGELOG 记录

## 10. 非目标（Out of Scope）

- **真实 Chrome profile 方案**（`run_v2_apply_chrome.py` 的 `launch_persistent_context` 指向系统 Chrome 目录）——不收编，涉及 `BrowserEngine.start` 改造与 profile 锁问题，另立议题
- **OS 通知**（osascript/桌面通知）——本次仅 logger
- **手动登录的 Slack/邮件通知**——不做
- **auto 模式的任何行为变更**——零改动
