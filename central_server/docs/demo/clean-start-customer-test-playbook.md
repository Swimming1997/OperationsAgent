# 客户测试：从零首跑手册（reset 后）

本文按**真实操作顺序**编写，假设你已用 `reset_demo_environment.py` 把系统恢复到「空库 + 默认角色」状态。

下文路径均相对于**仓库根目录**（例如 `OperationsAgent\`），不再使用硬编码的旧绝对路径。

---

## 0. 重置环境（先做）

在仓库根目录执行：

```powershell
cd central_server
.\scripts\reset.ps1
```

脚本会：

1. 自动停止中央服务（释放 8000 / 5173）
2. 控制台输入 **`YES`** 确认
3. 备份 SQLite 到 `central_server/backups/`
4. 清空全部业务数据
5. **保留** Local Agent Chrome Profile（位于 `local_agent\profiles\accounts\`）

> reset **不会**自动停止 Local Agent。若提示日志被占用，请先手动停止两侧服务后再重试 reset：

```powershell
cd central_server; .\scripts\stop.ps1
cd ..\local_agent; .\scripts\stop.ps1
cd ..\central_server; .\scripts\reset.ps1
```

如需仅预览、不执行：

```powershell
cd central_server
..\.venv\Scripts\python.exe scripts\reset_demo_environment.py --dry-run
```

---

## 1. 启动与停止

### 1.1 启动中央系统

```powershell
cd central_server
.\scripts\start.ps1
```

将自动启动（仅中央服务）：

| 服务 | 地址 |
|------|------|
| 前端 Vite | http://127.0.0.1:5173 |
| 后端 FastAPI | http://127.0.0.1:8000 |

> `central_server\scripts\start.ps1` **不会**启动 Chrome/CDP 或 Local Agent。  
> 账号登录与采集需按本文第 4–6 节单独启动 Local Agent（Agent 会自动拉起 Chrome Profile）。

进程 PID 记录在各自目录的 `logs/runtime/*.pid`：

- 中央：`central_server\logs\runtime\`
- Local Agent：`local_agent\logs\runtime\`

### 1.2 停止服务

中央：

```powershell
cd central_server
.\scripts\stop.ps1
```

Local Agent：

```powershell
cd local_agent
.\scripts\stop.ps1
```

> 不要直接关闭 `start.ps1` 弹出的窗口，那不会结束后台 uvicorn / agent 进程。

### 1.3 重启中央

```powershell
cd central_server
.\scripts\restart.ps1
```

仅重启中央，**不**影响 Local Agent。

### 1.4 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

浏览器打开：`http://127.0.0.1:5173`

---

## 2. 第一次进入系统（前端登录，不用 Swagger）

reset 后数据库仅有默认 **roles**，没有任何 **users**。打开前端 `http://127.0.0.1:5173` 会自动进入：

### 2.1 初始化管理员（仅首次）

页面：**「初始化管理员」**

| 字段 | 示例 |
|------|------|
| 用户名 | `admin` |
| 显示名 | `系统管理员` |
| 邮箱 | `admin@demo.local`（可选） |
| 密码 | 自行设置强密码 |

点击 **「创建并进入系统」**。系统会创建第一个 `admin` 用户并自动登录。

> 不要使用 Swagger `/docs` 创建用户。客户测试必须走该页面。

### 2.2 正常登录

若已有用户，将看到 **登录页**（用户名 + 密码）。登录成功后，顶部栏显示 **当前登录人** 与 **角色中文**。

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

切换到 **用户管理** → **新建用户**，或再用「创建员工账号」选角色 **主管**。

### 3.3 切换身份验证员工视角

1. 顶部栏 **退出登录**
2. 用 `operator1` 账号登录
3. 确认导航为 operator 可见菜单：**情报中心、对标作品库、任务模板、我的运行、账号管理、对标账号管理、规则管理**（无组织管理、Agent 管理、运行中心）

至少准备：

1. **一名主管**（supervisor）
2. **一名运营员工**（operator，用于登记 Agent 与跑任务）

---

## 4. Local Agent 与 Chrome Profile（重点）

原则：**一个小红书平台账号 = 一个独立 Chrome Profile**，由 Local Agent 在登录会话 claim 时自动创建并管理。

Profile 实际路径：

```text
local_agent\profiles\accounts\{profile_key}\
```

`profile_key` 由中央分配（形如 `accounts/<uuid>`），**不要**手动指定旧的本机绝对路径。

### 4.1 启动 Local Agent

复制示例配置（若尚未复制）：

```powershell
cd local_agent
Copy-Item configs\local_agent.employee.example.toml configs\local_agent.toml
```

启动（任选其一）：

```powershell
# 方式 A：一键脚本（推荐）
cd local_agent
.\scripts\start.ps1

# 方式 B：仓库根目录快捷脚本
.\start-local-agent.ps1

# 方式 C：直接运行
cd local_agent
..\.venv\Scripts\python.exe scripts\run_local_agent.py --config configs\local_agent.toml
```

成功日志特征（`local_agent\logs\local_agent\local_agent.log` 或控制台）：

- 已向中央注册 / 心跳
- `profiles_root=...\local_agent\profiles\accounts`
- `local_bridge=http://127.0.0.1:18765`（bridge 用于前端「登记本地 Agent」）
- `capabilities` 含 `feed_collect`、`search_collect` 等

### 4.2 多进程 / 多台 Agent

同一台电脑可运行多个 Agent 进程（不同配置文件、`device_name`、`machine_fingerprint` 勿重复）：

- 启动脚本默认 bridge 端口 `18765`；若被占用会自动尝试 `18766、18767…`（最多 10 个，与前端扫描范围一致）
- 中央账号页「登记本地 Agent」会扫描 `18765–18774`

### 4.3 手动 CDP 调试（可选，非日常流程）

仅审计或单浏览器调试时使用：

```powershell
cd local_agent
..\.venv\Scripts\python.exe scripts\start_account_chrome.py --account-key audit-demo --port 9222
```

**切勿**使用系统默认 Chrome 用户目录（`%LOCALAPPDATA%\Google\Chrome\User Data`）。

---

## 5. Agent 绑定与登记（两步骤）

当前产品采用 **Agent 池化调度**：运营员工名下登记多台设备，小红书账号任务按空闲设备 + 会话就绪自动分配。

### 5.1 管理员：Agent 绑定员工（`/agents`）

1. 登录 **admin 或 supervisor**
2. 进入 **Agent 管理** `/agents`
3. 确认员工电脑上的 Local Agent 状态为 **online**
4. 选中设备 → **绑定运营员工** → 保存

> 未绑定时：设备可见但「所属员工」为空；运营端 `/accounts` 无法完成登记。

### 5.2 运营员工：登记本地 Agent（`/accounts`）

1. 用 **operator** 账号登录
2. 进入 **账号管理** `/accounts`
3. 确认顶部 Agent 状态卡显示 bridge **已连接**
4. 点击 **「登记本地 Agent」**，将本机设备挂到当前运营账号的设备池

登记成功后，该运营名下的小红书账号任务会按 **agent_pool + session ready** 自动调度。

### 5.3 在中央确认

| 位置 | 预期 |
|------|------|
| `/agents`（admin） | Agent online，已绑定运营员工 |
| `/accounts`（operator） | 「本地 Agent 已连接」，bridge 端口可见 |

---

## 6. 创建平台账号并登录

路径：**`/accounts`**

| 字段 | 说明 |
|------|------|
| 账号备注名 | 便于识别，如 `XHS-A` |
| 平台 | xhs |
| 业务账号类型 | 与规则集/对标组关联（需管理员预先配置） |
| 绑定员工 | supervisor/admin 创建时可指定；operator 创建时自动绑定本人 |

> 账号表单**无**「默认 Agent」字段。执行设备由运营 Agent 池调度。

**发起登录**：

1. 保存账号后点击 **发起登录**
2. Local Agent 窗口应出现 `Claimed login session` → 自动启动 Chrome
3. 在浏览器内完成小红书登录 → 页面轮询显示 **已登录**

**Session ready**：账号会话健康为可用（Agent 在线 + 登录完成）。可在账号详情查看 session 状态。

双账号隔离验收以本手册中的账号、Agent 绑定和运行中心结果为准；旧阶段单独验收文档已归档移除。

---

## 7. 创建三类情报任务

路径：**任务模板** `/tasks`

### A. 推荐页任务

1. 新建模板 → 类型 **推荐页巡检**
2. 配置：绑定账号、滚动条数、`max_items` 等
3. **Readiness**：模板启用、账号 session ready、运营 Agent 池有在线设备
4. 点击 **立即运行**
5. operator 到 **我的运行** `/my-runs` 查看进度；admin/supervisor 可到 **运行中心** `/operations`

### B. 关键词搜索任务

1. 新建 **关键词搜索** 模板
2. 配置关键词列表、`max_items`
3. Readiness 同上
4. 立即运行 → 应出现 `search_collect` 执行项（Local Agent 已支持真实搜索采集）

### C. 对标监控任务

1. 先在 **对标账号管理** 配置账号/创作者
2. 新建 **对标账号监控** 模板并绑定对标组
3. 立即运行 → 出现 `creator_monitor` 相关批次

> 任务模板支持 **定时调度**（cron），除「立即运行」外可在模板详情配置计划任务。

---

## 8. 查看运行进度

| 角色 | 页面 | 路径 |
|------|------|------|
| 运营员工（operator） | 我的运行 | `/my-runs` |
| 管理员 / 主管 | 运行中心 | `/operations` |

运行中心区域说明（admin/supervisor）：

| 区域 | 对象 | 说明 |
|------|------|------|
| 运行批次概览 | Task Run | 与左侧「运行批次」列表一致 |
| 执行项概览 | Job | 与下方执行项列表一致 |
| 超时/遗留 | 执行项级 | 一般仅在卡住时使用「处理超时」「取消遗留」 |

---

## 9. 查看情报中心与对标作品库

**情报中心** `/intelligence`：

| 来源 | 筛选 |
|------|------|
| 推荐页 | `source_surface` = 首页流 / home feed |
| 关键词 | `source_surface` = search，可按 `search_keyword` |
| 对标 | `source_surface` = creator_monitor |

对内容执行：分派、选中、丢弃等工作流操作；也可手动触发补采详情/评论。

**对标作品库** `/reference-library`：将情报内容入库、撤回、归档，供销售/运营查阅（sales 角色只读）。

---

## 附录 A：reset 后 E2E 验证清单

- [ ] `GET /api/health` 正常
- [ ] 前端出现「初始化管理员」并完成创建
- [ ] 管理员登录成功，顶部显示用户名与角色
- [ ] 组织管理：创建主管 + 运营员工
- [ ] 退出后用员工账号登录，导航权限符合 operator
- [ ] Local Agent online，bridge 已连接
- [ ] admin `/agents` 绑定设备到运营员工；operator `/accounts` 登记本地 Agent
- [ ] 单账号登录跑通，session ready
- [ ] 单账号推荐页任务跑通，情报中心可见 home feed 来源
- [ ] 单账号关键词搜索跑通，情报中心可见 search 来源
- [ ] 单对标组监控跑通，情报中心可见 creator_monitor 来源
- [ ] operator `/my-runs` 或 admin `/operations` 批次与执行项数量一致
- [ ] 真实 XHS SLO 报告使用 Local Agent 实跑数据，不使用夹具盖章：
  `..\.venv\Scripts\python.exe scripts\xhs_slo_report.py --window-hours 24 --require-real-data --min-terminal-per-type 50`

---

## 附录 B：常见问题

**Q：顶部执行项「执行中 1」但左侧没有运行批次？**  
A：可能是无运行批次的遗留 Job；查看「无运行批次的活跃执行项」卡片，或用执行项列表筛选；必要时取消遗留项。

**Q：reset 会删 Chrome 登录态吗？**  
A：默认**不会**。reset 保留 `local_agent\profiles\accounts\`。仅在使用 `reset_demo_environment.py --include-project-profiles` 时才会删除 central 侧 demo profiles（与 Local Agent profile 路径不同）。

**Q：运营提示「本地 Agent 未连接」？**  
A：先确认本机已运行 `local_agent\scripts\start.ps1`；再检查 bridge：`http://127.0.0.1:18765/healthz`；最后在 `/accounts` 点击「登记本地 Agent」。

**Q：登录会话一直 waiting_agent？**  
A：确认 Agent 已 online 且 admin 已在 `/agents` 绑定运营员工。Agent 上线后会自动 claim 等待中的登录会话。
