# JobsDB 简历投递助手 — 测试用例文档

## 测试策略

| 类型 | 数量 | 层级 | 目标 |
|------|------|------|------|
| 单元测试 | 12 | 单模块 | 验证每个函数/类的独立行为 |
| 集成测试 | 5 | 多模块协作 | 验证模块间交互正确 |
| 端到端测试 | 3 | 全流程 | 验证完整业务流程 |

---

## 一、单元测试 (12个)

### TC-01: Stealth 反指纹 — Navigator.webdriver 隐藏
```python
async def test_stealth_patches_hide_webdriver():
    """
    验证 stealth 模块注入的 JS patch 能正确隐藏 navigator.webdriver
    
    前置条件：BrowserEngine 已启动
    输入：无（页面加载后检查）
    预期输出：navigator.webdriver === undefined
    验证方式：page.evaluate() 读取属性值
    """
```

### TC-02: Stealth 反指纹 — WebGL Vendor/Renderer 伪装
```python
async def test_stealth_patches_webgl_fingerprint():
    """
    验证 WebGL vendor/renderer 被覆盖为 'Intel Inc.' / 'Intel Iris Xe Graphics'
    
    前置条件：Stealth patches 已注入
    输入：调用 WebGL getParameter(0x9245) 和 getParameter(0x9246)
    预期输出：
        vendor == 'Intel Inc.'
        renderer == 'Intel Iris Xe Graphics'
    """
```

### TC-03: Mouse 模拟 — Bezier 曲线路径生成
```python
def test_mouse_bezier_path_is_not_straight_line():
    """
    验证鼠标移动路径不是直线，而是曲线
    
    输入：start=(0, 0), end=(100, 100)
    预期输出：路径中至少有一个点的 x/y 坐标不落在直线 y=x 上
    验证方式：检查路径与直线的偏差 > 5px
    """
```

### TC-04: Mouse 模拟 — 鼠标位置连续性
```python
def test_mouse_path_no_large_gaps():
    """
    验证 Bezier 路径是连续的，没有突变
    
    输入：start=(100, 100), end=(500, 300)
    预期输出：相邻点之间的最大距离 < 50px
    """
```

### TC-05: Typing 模拟 — 按键延迟服从高斯分布
```python
async def test_typing_delay_gaussian_distribution():
    """
    验证打字间隔不是均匀分布，而是集中在均值附近
    
    输入：typing_base_delay=80ms, variance=40ms，样本量 N=100
    预期输出：
        - 大部分延迟在 40ms-120ms 之间（约 68%）
        - 极少延迟 < 20ms 或 > 200ms
        - 标准差 ≈ 40ms ± 15ms
    验证方式：Monte Carlo 模拟抽样并统计
    """
```

### TC-06: Typing 模拟 — Typo 概率正确
```python
async def test_typing_introduces_typos():
    """
    验证 typo_probability=0.04 时，确实会产生约 4% 的 typo
    
    输入：text="abcdefghijklmnopqrstuvwxyz", 重复 10 次
    预期输出：输入事件序列中 Backspace 出现次数 > 0 且 < 20 次
    """
```

### TC-07: Timing 模拟 — 不同操作类型延迟不同
```python
def test_human_delay_varies_by_action_type():
    """
    验证不同操作类型产生不同的延迟范围
    
    输入：
        - PAGE_LOAD (均值 2.5s)
        - CLICK (均值 0.4s)
        - READ_CONTENT (均值 3.5s)
    预期输出：
        - PAGE_LOAD > CLICK（99% 概率）
        - READ_CONTENT > PAGE_LOAD（99% 概率）
    验证方式：各采样 100 次取均值比较
    """
```

### TC-08: Database — 职位重复保存不报错
```python
def test_database_save_job_idempotent():
    """
    验证同一个 job_id 可以重复 save，结果正确覆盖
    
    输入：两次调用 save_job 相同的 JobListing(id="123")
    预期输出：
        - 第二次 save 不报错
        - get_job("123") 返回最新数据
        - 数据库中只有一条记录
    """
```

### TC-09: Database — 已投递职位过滤
```python
def test_queue_filters_already_applied_jobs():
    """
    验证 ApplyQueue.build_queue 正确过滤已投递职位
    
    前置条件：数据库中已有 job_id="123" 的投递记录（status=submitted）
    输入：jobs=[JobListing(id="123"), JobListing(id="456")]
    预期输出：返回 [JobListing(id="456")]，长度为 1
    """
```

### TC-10: Rate Limiter — 当日次数超限触发等待
```python
async def test_rate_limiter_daily_cap():
    """
    验证当日投递数达到 max_per_day 时触发长等待
    
    前置条件：数据库中今日已有 30 条 submitted 记录
    输入：调用 rate_limiter.wait_if_needed()
    预期输出：阻塞直到次日 00:00（或等待时长 > 30000 秒）
    """
```

### TC-11: CookieStore — 过期检查
```python
def test_cookie_store_freshness():
    """
    验证 CookieStore.is_fresh(max_age_hours=12)
    
    场景 A：文件 1 小时前保存
        输入：调用 is_fresh(12)
        预期输出：True
    
    场景 B：文件 24 小时前保存（mock mtime）
        输入：调用 is_fresh(12)
        预期输出：False
    """
```

### TC-12: ApplyFlow 状态机 — 步骤检测
```python
async def test_apply_flow_detects_resume_step():
    """
    验证 ApplyFlow._detect_current_step() 能正确识别 Resume 步骤
    
    前置条件：mock HTML 页面包含 RESUME_SELECTION 元素
    输入：无
    预期输出：返回 ApplyStep.RESUME_SELECTION
    """
```

---

## 二、集成测试 (5个)

### TC-13: Browser + Stealth — 通过 bot.sannysoft.com 检测
```python
async def test_stealth_passes_bot_detection():
    """
    集成测试：浏览器打开 bot.sannysoft.com，验证没有红色检测结果
    
    前置条件：BrowserEngine + stealth patches 已启动
    输入：导航到 https://bot.sannysoft.com
    预期输出：
        - page.evaluate("navigator.webdriver") === undefined ✓
        - WebGL vendor 不是 'Google Inc.' 或空白 ✓
        - plugins 数组非空 ✓
    验证方式：Read 页面上的检测结果文本（如果元素可见）
    超时：30s
    """
```

### TC-14: HumanSimulator + Browser — 鼠标移动留下轨迹
```python
async def test_human_simulation_moves_mouse_realistically():
    """
    集成测试：HumanSimulator.move_to_element() 实际移动鼠标
    
    前置条件：BrowserEngine 在 headed 模式启动（x=1920, y=1080）
    输入：在页面渲染一个 100x100 的 div，调用 move_to_element(div)
    预期输出：
        - 鼠标位置从初始随机位置变化到目标中心
        - 鼠标坐标不是瞬变（至少经过 5 个不同坐标点）
    验证方式：page.evaluate() 读取 document.onmousemove 的最后一个事件坐标
    """
```

### TC-15: Login Flow — 未配置账号应报错
```python
async def test_login_handler_no_credentials_raises_error():
    """
    集成测试：没有 email/password 时，LoginHandler 抛出 LoginError
    
    前置条件：JobsDBConfig(email=None, password=None)
    输入：调用 ensure_logged_in()
    预期输出：抛出 LoginError，包含 "email and password not configured"
    """
```

### TC-16: Orchestrator + Queue + RateLimiter — 完整频率控制
```python
async def test_orchestrator_respects_rate_limits():
    """
    集成测试：Orchestrator 在连续投递中遵守频率限制
    
    前置条件：max_per_hour=2, min_delay_between=60s, mock 3 个职位
    输入：运行 Orchestrator.run(max_jobs=3)
    预期输出：
        - 第 1 和第 2 个 apply 之间间隔 ≤ 2 秒（首次）
        - 第 2 和第 3 个 apply 之间间隔 ≥ 60 秒（频率限制触发）
        - 最终统计成功率 ≤ 66%（部分可能被跳过）
    验证方式：mock BrowserEngine 和 ApplyFlow，记录时间戳
    """
```

### TC-17: Database + CookieStore — Session 持久化
```python
async def test_session_persistence_across_restarts():
    """
    集成测试：浏览器重启后 cookies 和 profile 仍然存在
    
    前置条件：BrowserEngine 使用同一个 user_data_dir
    执行：
        1. 启动 BrowserEngine，导航到任意页面
        2. 设置一个测试 cookie: session="abc123"
        3. browser.stop()
        4. 重新启动 BrowserEngine
    预期输出：
        - context.cookies() 中包含 session="abc123"
        - 页面引用 localStorage 中测试数据存在
    """
```

---

## 三、端到端测试 (3个)

### TC-18: 完整登录流程（真实 JobsDB）
```python
async def test_e2e_login_to_jobsdb_hk():
    """
    端到端：验证能成功登录 JobsDB HK
    
    前置条件：.env 中已配置正确的 email 和 password
    流程：
        1. start browser (headed, stealth on)
        2. navigate to https://www.jobsdb.com/hk
        3. handle cookie consent / popups
        4. click Sign in link
        5. fill email & password (HumanSimulator)
        6. click submit
        7. wait for navigation
        8. verify user avatar / dashboard visible
    
    预期输出：
        - LoginHandler.ensure_logged_in() 返回 True
        - 页面不出现 "Invalid email or password"
        - CAPTCHA 被检测到时暂停并提示用户（非失败）
    
    超时：60s
    危险等级：⚠️ 需要真实账号，请在受控环境执行
    """
```

### TC-19: 首页推荐职位抓取（真实 JobsDB）
```python
async def test_e2e_scrape_recommended_jobs():
    """
    端到端：登录后抓取首页推荐职位
    
    前置条件：已登录（cookie 有效或手动登录成功）
    流程：
        1. 导航到 https://www.jobsdb.com/hk
        2. 等待页面加载完成
        3. 滚动浏览页面（HumanSimulator.browse_homepage）
        4. 提取职位卡片（HomepageScraper.get_recommended_jobs）
    
    预期输出：
        - 返回的 jobs 列表长度 > 0
        - 每个 job 至少包含 id, title, company
        - id 是数字字符串（jobsdb 的 job id 格式）
        - 数据库中新增了对应的 jobs 记录
    
    超时：60s
    危险等级：⚠️ 需要真实账号，需要 headed 模式
    """
```

### TC-20: 完整投递流程（模拟表单，非真实提交）
```python
async def test_e2e_apply_flow_with_mock_page():
    """
    端到端：使用本地 HTML mock 测试完整的 ApplyFlow 状态机
    
    前置条件：运行一个 local HTTP server 提供 mock 投递表单
    mock HTML 包含：
        - Step 1: 默认简历选择（radio checked）
        - Step 2: 几个附加问题（dropdown, text, radio）
        - Step 3: 可选 cover letter (textarea)
        - Step 4: Review 页面 + Submit 按钮
        - Success message after submit
    
    流程：
        1. 打开 mock 页面
        2. ApplyFlow._detect_current_step() → RESUME_SELECTION
        3. _handle_resume_step() + click Next
        4. _detect_current_step() → QUESTIONS
        5. _handle_questions_step() + click Next
        6. _detect_current_step() → COVER_LETTER (skip)
        7. _detect_current_step() → REVIEW
        8. _handle_review_step() + click Submit
        9. _detect_current_step() → SUBMITTED
    
    预期输出：
        - 整个流程在 10 步内完成（max_steps=10）
        - ApplyResult.status == ApplyStatus.SUBMITTED
        - 每个步骤最多停留 1 次（没有循环）
        - 页面上最终出现 success message
    
    超时：60s
    危险等级：✅ 安全，使用本地 mock，不访问外部站点
    """
```

---

## 测试优先级

### P0（必须先过）
- TC-01 (stealth webdriver) — 反检测的基础
- TC-03 (bezier path) — 人类模拟的核心
- TC-08 (database idempotent) — 数据一致性
- TC-09 (queue filter) — 业务逻辑基础
- TC-13 (bot detection) — 反检测有效性的集成验证

### P1（重要）
- TC-02 (webgl fingerprint)
- TC-04 (path continuity)
- TC-05 (typing gaussian)
- TC-07 (human delay)
- TC-12 (state machine)
- TC-16 (rate limiting)
- TC-17 (session persistence)
- TC-20 (mock apply flow)

### P2（锦上添花）
- TC-06 (typo probability)
- TC-10 (daily cap)
- TC-11 (cookie freshness)
- TC-14 (mouse realistic)
- TC-15 (no credentials)

### P3（需要真实账号，最后执行）
- TC-18 (real login)
- TC-19 (real job scrape)

---

## 执行计划

```
Phase 1: 基础设施
  - 创建 tests/ 目录结构
  - 创建 conftest.py（共享 fixtures）
  
Phase 2: 单元测试（P0 + P1）
  - test_stealth.py → TC-01, TC-02
  - test_mouse.py → TC-03, TC-04
  - test_typing.py → TC-05, TC-06
  - test_timing.py → TC-07
  - test_database.py → TC-08, TC-09, TC-11
  - test_rate_limiter.py → TC-10, TC-16
  - test_apply_flow.py → TC-12

Phase 3: 集成测试
  - test_integration_stealth.py → TC-13, TC-14, TC-17
  - test_integration_login.py → TC-15

Phase 4: E2E 测试
  - test_e2e_login.py → TC-18（需账号）
  - test_e2e_scrape.py → TC-19（需账号）
  - test_e2e_apply.py → TC-20（mock，安全）

Phase 5: 运行全部
  - pytest -v -m "not e2e" -- 所有非 E2E 测试
  - pytest -v -m "e2e" -- 需要账号的真实测试
```

---

## 需要的 Fixtures (conftest.py)

```python
@pytest.fixture
async def browser_engine() -> BrowserEngine:
    """启动测试浏览器，结束后自动关闭"""
    
@pytest.fixture
async def mock_page(browser_engine) -> Page:
    """提供已注入 stealth 的空 page"""
    
@pytest.fixture
def temp_database(tmp_path) -> Database:
    """提供临时数据库（每个测试独立）"""
    
@pytest.fixture
def sample_jobs() -> List[JobListing]:
    """提供 5 个测试职位列表"""
    
@pytest.fixture
async def mock_apply_page(mock_page):
    """加载 mock 投递表单的 page"""
```
