# XHS HomeFeed Probe

本探针只验证本地已登录小红书 Chrome 会话、推荐流卡片采样、FeedCandidate 标准化和现有 ingestion 链路。

## 方式一：连接已开放 CDP 的 Chrome

先用独立 profile 启动 Chrome：

```powershell
& "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="D:\AMiracle\profiles\xhs_probe"
```

在该 Chrome 中手动登录小红书，然后运行：

```powershell
.\.venv\Scripts\python.exe scripts\xhs_homefeed_probe.py `
  --job-id <feed_job_id> `
  --account-id <account_id> `
  --cdp-url http://127.0.0.1:9222 `
  --target-count 50
```

## 方式二：由 Playwright 启动指定 profile

```powershell
.\.venv\Scripts\python.exe scripts\xhs_homefeed_probe.py `
  --job-id <feed_job_id> `
  --account-id <account_id> `
  --user-data-dir "D:\AMiracle\profiles\xhs_probe" `
  --chrome-executable-path "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" `
  --target-count 50
```

## 输出说明

脚本输出 JSON：
- `session_status`: `ready` / `expired` / `manual_verify_required` / `unavailable`
- `report.target_count`: 目标采样数
- `report.actual_count`: 实际采样数
- `report.unique_candidate_count`: 页面采样阶段去重后的数量
- `report.field_success`: 每个字段的解析数量与比例
- `ingestion.results`: Intelligence Engine ingestion 返回结果
