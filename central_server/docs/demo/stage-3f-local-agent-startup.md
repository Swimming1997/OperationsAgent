# Stage 3F：中央系统与 Local Agent 启动说明

下文路径均相对于**仓库根目录**。

---

## 架构（两套进程）

| 组件 | 进程 | 启动脚本 | 停止脚本 |
|------|------|----------|----------|
| 中央系统 | FastAPI + Vite | `cd central_server; .\scripts\start.ps1` | `cd central_server; .\scripts\stop.ps1` |
| Local Agent | `run_local_agent.py` | `cd local_agent; .\scripts\start.ps1` | `cd local_agent; .\scripts\stop.ps1` |

`central_server\scripts\start.ps1` **仅启动中央**，不会启动 Local Agent 或 Chrome。

开发演示需**分别启动**两侧（两个终端窗口）：

```powershell
# 终端 1
cd central_server; .\scripts\start.ps1

# 终端 2
cd local_agent; .\scripts\start.ps1
```

或使用仓库根目录快捷脚本启动 Agent：`.\start-local-agent.ps1`

---

## 单机开发拓扑

同一台 Windows 开发机：

1. `cd central_server; .\scripts\start.ps1` → http://127.0.0.1:5173 + API :8000
2. `cd local_agent; .\scripts\start.ps1` → 注册、心跳、Local Bridge（默认 :18765）
3. 管理员在 **Agent 管理**（`/agents`）将设备 **绑定到运营员工**
4. 运营员工在 **账号管理**（`/accounts`）点击 **「登记本地 Agent」**，将设备挂入运营 Agent 池
5. 员工 `/accounts` 创建小红书账号 → **发起登录** → Agent claim 会话并拉起 Chrome

---

## 真实产品拓扑

- **中央服务器**：只部署中央（`central_server\scripts\start.ps1` + 生产前端构建）
- **每名员工电脑**：只运行 Local Agent（`local_agent\scripts\start.ps1` + 员工配置）

---

## Agent 绑定与登记（Web UI）

完整流程分两步，**无需**在本地 TOML 填写 `employee_id`（正常留空即可）。

### 步骤 1：管理员绑定员工（`/agents`）

1. 启动中央，登录 **管理员或主管**
2. **组织管理** 创建运营员工（若尚未创建）
3. 员工电脑运行 `cd local_agent; .\scripts\start.ps1`，设备出现在 **Agent 管理**
4. 选中设备 → **绑定运营员工** → 保存

### 步骤 2：运营登记设备（`/accounts`）

1. 运营员工登录
2. 进入 **账号管理**，确认 bridge **已连接**（Local Agent 须在本机运行）
3. 点击 **「登记本地 Agent」**

**未完成的后果：**

| 缺失步骤 | 表现 |
|----------|------|
| Agent 未运行 | `/agents` 离线；`/accounts` bridge 未连接 |
| 未绑定员工 | 设备可见但无所属员工；运营无法登记 |
| 未登记到运营池 | 任务 pending；readiness 报 `agent_pool_*` 相关错误 |
| 登录会话 waiting_agent | 浏览器不会弹出，直到 Agent online 并 claim |

---

## 账号登录验收步骤

1. `cd central_server; .\scripts\start.ps1`
2. 浏览器登录 → 创建管理员（若需）→ 创建运营员工
3. `cd local_agent; .\scripts\start.ps1`（保持窗口打开，观察 `[Local Agent]` 日志）
4. 管理员 `/agents`：设备 online → 绑定运营员工
5. 运营 `/accounts`：bridge 已连接 → **登记本地 Agent**
6. 创建运营账号 → **发起登录**
7. Agent 窗口应出现 `Claimed login session` → 启动 Chrome → 员工在浏览器内完成小红书登录

双账号隔离见：`stage-3f-dual-account-login.md`。

---

## 启动日志示例

### cd central_server; .\scripts\start.ps1

```text
========================================================================
 AMiracle Central (API + Web UI)
========================================================================
  This script does NOT start Local Agent.
  For account login / Chrome profiles on this PC, run:
    cd local_agent; .\scripts\start.ps1
...
  Backend ready: http://127.0.0.1:8000/api/health
  Frontend ready: http://127.0.0.1:5173
```

### cd local_agent; .\scripts\start.ps1

```text
[Local Agent] Config file: configs\local_agent.employee.example.toml
[Local Agent] Connecting to http://127.0.0.1:8000
[Local Agent] device_name=WIN-1
[Local Agent] employee binding: assign in Admin /agents after this device registers
[Local Agent] profiles_root=...\local_agent\profiles\accounts
[Local Agent] local_bridge=http://127.0.0.1:18765
[Local Agent] supports_account_login=True
[Local Agent] Registered as WIN-1 (agent_id=...)
[Local Agent] Heartbeat OK agent_id=... device=WIN-1
[Local Agent] Claimed 1 login session(s): ...
```

---

## 其它脚本

| 脚本 | 含义 |
|------|------|
| `central_server\scripts\stop.ps1` | 停止中央（8000 / 5173） |
| `local_agent\scripts\stop.ps1` | 停止 Local Agent 及脚本追踪的 Chrome/CDP |
| `central_server\scripts\restart.ps1` | 仅重启中央 |
| `local_agent\scripts\restart.ps1` | 重启 Local Agent |
| `central_server\scripts\reset.ps1` | 停中央 + 清空演示数据（**保留** Local Agent profiles） |
| `start-local-agent.ps1`（仓库根） | 转发到 `local_agent\scripts\start.ps1` |

---

## 当前「离线 / 暂无心跳」说明

若管理员看到 `WIN-1 · 离线 / 暂无心跳`，通常表示 **本机 Local Agent 进程未运行或未成功心跳**，而不是中央故障。

正确启动 `cd local_agent; .\scripts\start.ps1` 后应变为 **online + 心跳时间 + 版本**。

已处于 `waiting_agent` 的登录会话：Agent 上线并心跳正常后，会在下一轮 claim 中自动认领并拉起浏览器（无需员工重复点「发起登录」）。
