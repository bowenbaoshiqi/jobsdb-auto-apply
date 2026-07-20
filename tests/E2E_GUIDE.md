# 真实 E2E 测试 — 执行指南

## 环境准备

```bash
# 1. 确保 conda 环境已激活
conda activate jobsdb

# 2. 切换到项目目录
cd /Users/t91/AI_Project/resume
```

## 方式一：交互式输入（推荐，密码不保存）

```bash
python tests/test_e2e_live.py
```

运行后会提示你输入：
- JobsDB 邮箱
- JobsDB 密码（输入时隐藏）

## 方式二：通过 .env 文件配置

编辑 `.env` 文件：

```bash
# 用你喜欢的编辑器
nano .env
# 或
vim .env
```

填入账号：

```
JOBSDB_EMAIL=your-email@example.com
JOBSDB_PASSWORD=your-password
```

然后运行：

```bash
python tests/test_e2e_live.py
```

## 预期流程

```
🚀 启动浏览器...                    ← 会弹出真实浏览器窗口
✓ 浏览器已启动 (headed 模式)

🔐 开始登录流程...                  ← 观察浏览器中的操作
✅ 登录成功！

🔍 开始抓取首页推荐职位...           ← 浏览器会自动滚动浏览
✅ 抓取完成！共找到 N 个职位

-------------------------------------------
#    职位标题                          公司
-------------------------------------------
1    Software Engineer                ABC Tech
2    Senior Developer                 XYZ Corp
...
-------------------------------------------

💾 已保存到数据库: data/jobsdb_e2e.db

✅ E2E 测试完成！
```

## 可能需要人工干预的情况

### 1. 首次登录 — Cookie Consent

JobsDB 首页可能会弹出 Cookie 同意弹窗。脚本会自动点击 "Accept"，但如果选择器不匹配，你可能需要手动点击。

### 2. 验证码 / CAPTCHA

如果遇到：
- reCAPTCHA 勾选框
- "I'm not a robot"
- 图片选择验证

**请立即在浏览器窗口中手动解决**，然后按 Enter 继续。

脚本会暂停等待。

### 3. 两步验证 / 邮箱验证

如果你的账号开启了两步验证，需要在手机上确认或输入验证码。

### 4. 登录失败

可能原因：
- 账号密码错误 → 请重新输入
- 页面结构变化 → 需要更新选择器
- 网络问题 → 检查代理或重试

## 测试结果分析

### ✅ 成功标志
- "登录成功！"
- 浏览器中显示 dashboard / 用户头像
- 抓取到 ≥ 1 个职位

### ⚠️ 部分成功
- 登录成功但抓取到 0 个职位
- 可能原因：新账号没有推荐数据、需要完善资料

### ❌ 失败标志
- "登录失败"
- 截图保存在 `data/screenshots/login_failed_*.png`
- 请检查截图确认问题

## 调试模式

如果测试失败，可以查看详细日志：

```bash
# 实时查看日志输出
tail -f data/logs/jobsdb_*.log
```

或者在脚本运行前设置环境变量：

```bash
LOG_LEVEL=DEBUG python tests/test_e2e_live.py
```

## 下一步

E2E 测试成功后，可以进行：

1. **真实投递测试**（单个职位，谨慎操作）
2. **调整选择器**：根据实际页面结构更新 `src/jobsdb/selectors.py`
3. **优化 HumanSimulator**：观察鼠标/滚动行为是否自然
4. **运行完整投递**：`python -m src.main start --max-jobs 1`

## 安全提醒

- ⚠️ 不要分享 `.env` 文件
- ⚠️ 不要在公共仓库提交真实密码
- ⚠️ `.env` 已在 `.gitignore` 中，不会被 git 追踪
- ✅ cookie 和 profile 保存在本地 `data/` 目录
