# 客户测试：从零首跑手册（reset 后）

本文按**真实操作顺序**编写，假设你已用 `reset_demo_environment.py` 把系统恢复到「空库 + 默认角色」状态。

---

## 0. 重置环境（先做）

在项目根目录 **双击 `cd central_server; .\scripts\reset.ps1`**（会打开黑色命令行窗口并保持到结束，请阅读输出后按任意键关闭），一条龙完成：

1. 自动 `分别运行 local_agent\scripts\stop.ps1 和 central_server\scripts\stop.ps1`（释放 8000 / 5173，解锁日志）
2. 控制台输入 **`YES`** 确认
3. 备份 SQLite 到 `backups/`
4. 清空全部业务数据
5. 删除 `profiles\` 下项目 Chrome 目录

无需任何参数。若提示日志被占用，先再运行一次 `分别运行 local_agent\scripts\stop.ps1 和 central_server\scripts\stop.ps1`，然后重新双击 `cd central_server; .\scripts\reset.ps1`。

如需仅预览、不执行，可手动运行：

```powershell
.\.venv\Scripts\python.exe scripts\reset_demo_environment.py --dry-run
```

---

## 1. 启动与停止中央系统

### 1.1 一键启动（推荐）

在项目根目录 **双击 `central_server\scripts\start.ps1`**（或 `recentral_server\scripts\start.ps1` 先停后启）。

将自动启动（仅中央服务）：

| 服务 | 地址 |
|------|------|
| 前端 Vite | http://127.0.0.1:5173 |
| 后端 FastAPI | http://127.0.0.1:8000 |

> 注意：`central_server\scripts\start.ps1` **不会启动 Chrome/CDP**。  
> 采集用 CDP 端口（如 `http://127.0.0.1:9222`）需按本文第 4 节单独启动浏览器实例。

CDP 快速自检（可选）：

```powershell
Invoke-WebRequest http://127.0.0.1:9222/json/version -UseBasicParsing
```

进程 PID 记录在 `logs/runtime/*.pid`，供 `分别运行 local_agent\scripts\stop.ps1 和 central_server\scripts\stop.ps1` 可靠结束进程。

### 1.2 一键停止

**双击 `分别运行 local_agent\scripts\stop.ps1 和 central_server\scripts\stop.ps1`**（不要直接关 central_server\scripts\start.ps1 窗口，那不会结束后台 uvicorn）。

等价命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop.ps1
```

停止后会校验 **8000 / 5173** 是否已释放；若你单独启动了 Chrome/CDP，再额外检查 9222（或对应端口）。

### 1.3 一键重启

**双击 `recentral_server\scripts\start.ps1`** = `分别运行 local_agent\scripts\stop.ps1 和 central_server\scripts\stop.ps1` + `central_server\scripts\start.ps1`。

### 1.4 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

浏览器打开：`http://127.0.0.1:5173`

若端口仍被占用，先 `分别运行 local_agent\scripts\stop.ps1 和 central_server\scripts\stop.ps1` 再 `central_server\scripts\start.ps1`。

---

## 2. 第一次进入系统（前端登录，不用 Swagger）

reset 后数据库仅有默认 **roles**，没有任何 **users**。打开前端 `http://127.0.0.1:5173` 会自动进入：

### 2.1 初始化管理员（仅首次）

页面：**「初始化管理员」**

填写：

| 字段 | 示例 |
|------|------|
| 用户名 | `admin` |
| 显示名 | `系统管理员` |
| 邮箱 | `admin@demo.local`（可选） |
| 密码 | 自行设置强密码 |

点击 **「创建并进入系统」**。系统会创建第一个 `admin` 用户并自动登录。

> 不要使用 Swagger `/docs` 创建用户。客户测试必须走该页面。

### 2.2 正常登录

若已有用户，将看到 **登录页**：

- 用户名 + 密码
- 登录成功后，顶部栏显示 **当前登录人** 与 **角色中文**

### 2.3 开发调试（可选，客户演示请关闭）

顶部栏点击 **「开发」** 可展开隐藏工具，启用「Header 模拟身份」。**客户验收时不要开启。**

---

## 3. 创建员工与用户（组织管理）

使用左侧导航 **「组织管理」**（仅 admin / supervisor 可见）。

### 3.1 推荐：创建员工账号（一体化）

在 **员工管理** 标签页点击 **「创建员工账号」**：

| 字段 | 示例 |
|------|------|
| 用户名 | `operator1` |
| 显示名 | `运营小王` |
| 密码 | 初始密码 |
| 角色 | 运营员工（operator） |

一次操作会同时创建 **User + Employee**。

### 3.2 创建主管账号

切换到 **用户管理** → **新建用户**：

- 用户名 `supervisor1`
- 角色填 `supervisor`
- 设置密码

或再用「创建员工账号」选角色 **主管**。

### 3.3 切换身份验证员工视角

1. 顶部栏 **退出登录**
2. 用 `operator1` 账号登录
3. 确认导航仅显示员工可见菜单（情报中心、任务、账号等；无组织管理、规则、Agent 等）

至少准备：

1. **一名主管**（supervisor）
2. **一名运营员工**（operator，用于绑定 Agent 与跑任务）

---

## 4. 每个员工如何准备本地多账号（重点）

原则：**一个平台账号 = 一个独立 Chrome Profile + 一个 CDP 端口**。

### 4.1 推荐目录结构

```text
D:\AMiracle\profiles\
  xhs_acc001\     # 账号 1
  xhs_acc002\     # 账号 2
```

### 4.2 推荐端口规划

| 账号 | debugging port | CDP URL |
|------|----------------|---------|
| acc001 | 9222 | http://127.0.0.1:9222 |
| acc002 | 9223 | http://127.0.0.1:9223 |
| acc003 | 9224 | http://127.0.0.1:9224 |

### 4.3 启动两个 Chrome 实例（PowerShell）

账号 1：

```powershell
cd D:\AMiracle
.\.venv\Scripts\python.exe scripts\start_account_chrome.py --account-key acc001 --port 9222
```

账号 2（新终端）：

```powershell
.\.venv\Scripts\python.exe scripts\start_account_chrome.py --account-key acc002 --port 9223
```

分别在打开的浏览器中登录**不同**小红书账号。登录态保存在各自 profile，互不干扰。

### 4.4 手动命令（等价）

```powershell
$Chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
& $Chrome `
  --user-data-dir="D:\AMiracle\profiles\xhs_acc001" `
  --remote-debugging-port=9222 `
  "https://www.xiaohongshu.com/explore"
```

**切勿**使用系统默认 Chrome 用户目录（`%LOCALAPPDATA%\Google\Chrome\User Data`）。

---

## 5. 创建 Local Agent 配置

复制示例：

```powershell
Copy-Item configs\local_agent.example.toml configs\local_agent.toml
```

多账号 `local_agent.toml` 示例（`[accounts]` 的 key 填中央系统里的 `platform_accounts.id`）：

```toml
center_url = "http://127.0.0.1:8000"
agent_id = ""   # 首次留空，注册后填入
# employee_id 留空；在 Admin「Agent 管理」界面绑定运营员工
device_name = "演示员工电脑"
machine_fingerprint = "demo-pc-001"
cdp_url = "http://127.0.0.1:9222"  # 默认 CDP，单账号时用
supported_job_types = ["feed_collect", "creator_monitor", "detail_fetch", "comment_fetch", "search_collect"]

[accounts]
"00000000-0000-0000-0000-000000000001" = { platform = "xhs", session_mode = "cdp", cdp_url = "http://127.0.0.1:9222" }
"00000000-0000-0000-0000-000000000002" = { platform = "xhs", session_mode = "cdp", cdp_url = "http://127.0.0.1:9223" }
```

---

## 6. 启动 Local Agent

```powershell
cd D:\AMiracle
.\.venv\Scripts\python.exe scripts\run_local_agent.py --config configs\local_agent.toml
```

**同一台电脑多台 Agent**（每个进程一个 bridge 端口）：

- 一键 `cd local_agent; .\scripts\start.ps1`（或根目录 `start-local-agent.ps1`）会读配置里的首选端口（默认 `18765`）。
- **若该端口已被占用**，启动脚本会自动尝试 `18766、18767…`（最多 10 个，与前端扫描范围一致），并在控制台打印 `bridge port 18765 in use, using 18766`。
- 多台设备请使用**不同配置文件**（`device_name`、`machine_fingerprint` 不要相同），可多次双击启动脚本，无需手写 `--bridge-port`。

```powershell
# 也可手动指定首选端口（仍会在被占用时自动递增）
.\.venv\Scripts\python.exe scripts\run_local_agent.py --config configs\local_agent_2.toml --bridge-port 18765
```

中央账号管理页「登记本地 Agent」会扫描 `18765–18774`（或前端 `VITE_LOCAL_BRIDGE_PORTS`），一次登记多台。

成功日志特征（`logs/local_agent/local_agent.log`）：

- 已向中央注册/心跳
- `capabilities` 含 `feed_collect`、`search_collect` 等

### 6.1 在中央确认

前端 **`/agents`**：

- Agent 状态 **online**
- `job_types` / capabilities 包含三类采集类型

---

## 7. 在中央创建平台账号并绑定 Agent

路径：**`/accounts`**

每个账号填写：

| 字段 | 说明 |
|------|------|
| 平台 | xhs |
| 显示名 | 便于识别 |
| 业务账号类型 | 与规则集/对标组关联 |
| 默认 Agent | 选上一步注册的 Local Agent |

**Session ready**：账号会话健康为可用（Agent 心跳 + CDP 可连）。可在账号详情查看 session 状态。

---

## 8. 创建三类情报任务

### A. 推荐页任务

1. 进入 **任务中心** `/tasks`
2. 新建模板 → 类型 **推荐页巡检**
3. 配置：绑定账号、滚动条数、`max_items` 等
4. **Readiness**：模板启用、账号 session ready、Agent online
5. 点击 **立即运行** → 到 **运行中心** `/operations` 看运行批次与执行项

### B. 关键词搜索任务

1. 新建 **关键词搜索** 模板
2. 配置关键词列表、`max_items`
3. Readiness 同上
4. 立即运行 → 运行中心应出现 `search_collect` 执行项

### C. 对标监控任务

1. 先在 **对标组** 配置账号/创作者
2. 新建 **对标账号监控** 模板并绑定对标组
3. 立即运行 → 运行中心出现 `creator_monitor` 相关批次

---

## 9. 查看运行中心

路径：**`/operations`**

| 区域 | 对象 | 说明 |
|------|------|------|
| 运行批次概览 | Task Run | 与左侧「运行批次」列表一致 |
| 执行项概览 | Job | 与下方执行项列表一致 |
| 左侧列表 | 运行批次 | 按「运行批次·执行中」等筛选 |
| 中间列表 | 执行项 | 单条采集/补采任务 |
| 超时/遗留 | 执行项级 | 一般仅在卡住时使用「处理超时」「取消遗留」 |

正常运营**不需要**频繁手动清理队列。

---

## 10. 查看情报中心

路径：**`/intelligence`**（或项目内情报列表路由）

| 来源 | 筛选 |
|------|------|
| 推荐页 | `source_surface` = 首页流 / home feed |
| 关键词 | `source_surface` = search，可按 `search_keyword` |
| 对标 | `source_surface` = creator_monitor |

对内容执行：分派、选中、丢弃等工作流操作。

---

## 附录 A：reset 后 E2E 验证清单

- [ ] `GET /api/health` 正常
- [ ] 前端出现「初始化管理员」并完成创建
- [ ] 管理员登录成功，顶部显示用户名与角色
- [ ] 组织管理：创建主管 + 运营员工（一体化表单）
- [ ] 退出后用员工账号登录，导航权限符合 operator
- [ ] 两个 Chrome profile + 两个 CDP 端口均可打开小红书
- [ ] Local Agent online，多账号 session ready
- [ ] 单账号推荐页任务跑通，情报中心可见 home feed 来源
- [ ] 单账号关键词搜索跑通，情报中心可见 search 来源
- [ ] 单对标组监控跑通，情报中心可见 creator_monitor 来源
- [ ] 运行中心：运行批次概览「执行中」与左侧筛选「运行批次·执行中」数量一致
- [ ] 运行中心：执行项概览与执行项列表口径一致

---

## 附录 B：常见问题

**Q：顶部执行项「执行中 1」但左侧没有运行批次？**  
A：可能是无运行批次的遗留 Job；查看「无运行批次的活跃执行项」卡片，或用执行项列表筛选；必要时取消遗留项。

**Q：reset 会删系统 Chrome 吗？**  
A：不会。仅 `--include-project-profiles` 时删除 `D:\AMiracle\profiles\` 下子目录。
