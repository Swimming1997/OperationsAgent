# P1 工程验收结果

> 验收时间：2026-06-14  
> 范围：P1 开发落地计划中的任务调度闭环、XHS 账号资产读取、对标素材准备、规则解释、权限/边界、真实 Local Agent SLO。

## 1. 总结

P1 总验收清单 9/9 已完成，详见 `p1-development-plan.md`。

| 验收项 | 结果 |
|---|---|
| 任务模板可立即运行和定时运行 | PASS |
| 运行中心能查看失败原因、错误码、账号、Agent、重试状态 | PASS |
| XHS 账号资产至少一个只读能力完成正式 Job 闭环 | PASS |
| 对标作品可生成或维护素材准备记录 | PASS |
| 规则命中解释在情报详情或对标详情中可见 | PASS |
| sales 仍只读，运营/主管/管理员权限矩阵不回退 | PASS |
| Central / Local Agent 边界扫描通过 | PASS |
| 后端 pytest、前端 test/build、Local Agent smoke 通过 | PASS |
| 使用真实 Local Agent 数据输出 24h XHS SLO 报告 | PASS |

## 2. 真实 XHS SLO

命令：

```powershell
cd central_server
..\.venv\Scripts\python.exe scripts\xhs_slo_report.py --window-hours 24 --require-real-data --min-terminal-per-type 50
```

结果：

| job_type | success_rate | terminal | real | fixture | 结果 |
|---|---:|---:|---:|---:|---|
| feed_collect | 100.0% | 51 | 51 | 0 | PASS |
| search_collect | 98.1% | 53 | 53 | 0 | PASS |
| detail_fetch | 100.0% | 64 | 64 | 0 | PASS |
| comment_fetch | 100.0% | 54 | 54 | 0 | PASS |

`stale_running_over_30m = 0`。

### search_collect 失败样本说明

`search_collect` 有 1 条历史失败样本：

- job_id：`b1e78aa0-caac-4ea8-ab8c-112558fce09e`
- 最终错误：`session_connect_failed`
- 直接原因：重试时账号浏览器 CDP `127.0.0.1:9431` 未监听，Playwright `connect_over_cdp` 被拒绝。
- 结论：该样本属于当时本地会话环境不可用，不是当前搜索采集逻辑缺陷。

该 job 首次运行暴露过 `XhsSearchProbe` 未导入问题，已修复并加入回归测试；后续真实 `search_collect` 样本成功率满足 SLO。

## 3. 本轮真实环境修复

- `xhs_account_posted_notes` 支持当 `query_self` 未返回 user_id 时，从已登录页面“我”的 profile 链接 fallback 解析当前账号。
- Local Agent `run_forever` 遇到中心服务瞬时 `httpx.RequestError` 时记录 warning 并继续轮询，避免长跑 SLO 过程中因短暂读错误退出。
- 本机 Local Agent 配置补齐 `xhs_account_posted_notes` job type，确保能力上报与真实 claim 一致。

## 4. 验证命令

```powershell
cd local_agent
..\.venv\Scripts\python.exe -m pytest tests\test_local_agent_runtime.py -q
```

结果：`13 passed`。

已完成过的全量验证：

- `central_server` 后端 pytest：通过。
- `local_agent` pytest：通过。
- `central_server/frontend` test/build：通过。
- Central / Local Agent 边界扫描：通过。
- Local Agent XHS smoke：login、homefeed、search、detail、comments、suggest 真实链路通过。

## 5. 收尾状态

- P1 开发计划验收清单已全部勾选。
- 本地服务已停止，避免继续消费 pending 任务或触发平台风控。
- 真实 SLO 报告使用 Local Agent 实跑数据，不使用 fixture 样本。
