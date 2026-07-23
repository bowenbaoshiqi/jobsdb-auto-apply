---
name: start-apply
description: 启动 JobsDB 真实投递会话(前台浏览器)。当用户说"帮我投5个"、"投10个"、"开始投递"、"投简历"、"投几个职位"等时触发。从用户话语中解析数量 N,默认 5。
---

# start-apply — 启动 JobsDB 投递

## 1. 解析数量

从用户消息提取职位数 N("帮我投5个"→5,"投10个"→10)。没有数字则 N=5。不要反问,直接跑。

## 2. 启动(后台)

```bash
scripts/run_apply.sh N
```

用 run_in_background=true 启动。脚本自带跑前检查(cookies 存在性)和参数校验;若退出码非 0,把 stderr 原样报告给用户并停止。

## 3. 监控节奏

每 60–90 秒 tail 一次输出文件,盯这些关键标记:

- `Selected 'Don't include a cover letter'` — 求职信步骤 OK
- `Unknown step, Continue button found` — 向导中间页推进中(正常)
- `Auto-filled N empty select(s)` — 校验兜底触发(正常,选的是最后一个有效选项)
- `Clicking submit button` — 到最后一步
- `record_application` 行尾 — `✅ submitted` / `⏭️ skipped` / `❌ failed`
- `Session Summary` — 会话结束,读 Successful/Failed/Skipped

注意:职位标题会串台(已知 scraper 小问题),标题里夹杂的大段相邻卡片文本忽略即可,只看开头的职位名和行尾状态。

## 4. 结果判读规则(2026-07-22 e2e 沉淀)

| 现象 | 结论 | 动作 |
|------|------|------|
| `⏭️ skipped` / "not quick-apply" | 标准 Apply 职位,符合 v1.0 既定策略 | **不是失败**,正常汇报 |
| `Stuck at ... Continue not advancing` | 视口外元素点击落空 | 查 `src/simulation/mouse.py` 的 `scroll_into_view_if_needed` |
| `Failed at step: review` 但用户看到成功页 | 成功文案不在指标里 | 读日志中 post-submit page text,补 `_SUCCESS_INDICATORS`(src/jobsdb/apply/detectors.py) |
| `Element is not attached to the DOM` 单次 | DOM 重渲染,orchestrator 有 3 次重试 | 观察即可;连续 2 次失败会话才会中止 |
| 长时间无日志 | 检查是否有 wait_for_selector 超时单位 bug(秒 vs 毫秒) | PageController 超时单位是**秒** |
| cookies 检查失败(退出码 3) | 未登录 | 让用户先手动登录一次 |

## 5. 汇报模板(会话结束后按此格式)

```
✅ 投递会话结束(N 个职位,成功率 X%)

| # | 职位 | 结果 |
|---|------|------|
| 1 | xxx | ✅ 已投递 |
| 2 | xxx | ⏭️ 跳过(标准 Apply) |
| 3 | xxx | ❌ 失败:原因 |

汇总:成功 A / 跳过 B / 失败 C
```

若有 ❌,附日志中的 error_message 和截图路径;不要只说"失败了"。

## 6. 硬约束(不可违背)

- 只投 quick apply;标准 Apply 一律 SKIPPED(v1.0 既定策略)
- UNKNOWN 页面策略:一路点 Continue,漏填系统会提示
- 自动补填下拉:选**最后一个**有效选项(如最高学位)
- 连续 2 个职位失败 → 会话自动中止(检测保护),此时停下来排查,不要直接重启
- 绝不 commit:`accounts/*.json`、`.env`、`data/`、日志文件
