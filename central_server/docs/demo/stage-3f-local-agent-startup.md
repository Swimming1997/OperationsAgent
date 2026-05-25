# Stage 3F：中央系统与 Local Agent 启动说明

## 架构（两套进程）

| 组件 | 进程 | 启动脚本 | 停止脚本 |
|------|------|----------|----------|
| 中央系统 | FastAPI + Vite | `cd central_server; .\scripts\start.ps1` | `cd central_server; .\scripts\stop.ps1` |
| Local Agent | `run_local_agent.py` | `cd local_agent; .\scripts\start.ps1` | `cd local_agent; .\scripts\stop.ps1` |

`central_server\scripts\start.ps1` **仅启动中央**（兼容旧习惯），不会启动 Local Agent。

开发演示一键：`分别运行 central_server\scripts\start.ps1 和 local_agent\scripts\start.ps1`（本窗口中央 + 新窗口 Agent）。

---

## 单机开发拓扑

同一台 Windows 开发机：

1. `cd central_server; .\scripts\start.ps1` → http://127.0.0.1:5173 + API :8000  
2. `cd local_agent; .\scripts\start.ps1` → 注册、心跳  
3. 管理员在 **Agent 管理**（`/agents`）将设备绑定到运营员工  
4. 员工 `/accounts` 发起登录 → Agent 认领会话并拉起 Chrome  

---

## 真实产品拓扑

- 中央服务器：只部署中央（`start_central` 等价物 + 生产构建）  
- 每名员工电脑：只运行 Local Agent（`start_local_agent` + 员工配置）  

---

## Agent 绑定员工（Web UI，无需改本地配置）

1. 启动中央，登录 **管理员或主管**  
2. **组织管理** 创建运营员工（若尚未创建）  
3. 员工电脑运行 `cd local_agent; .\scripts\start.ps1`，设备出现在 **Agent 管理**  
4. 选中设备 → **绑定运营员工** → 保存  

**未绑定的后果：**

- 管理员 `/agents` 可见设备，但「所属员工」为未绑定  
- 员工 `/accounts` 显示「本地 Agent 未连接」、绑定下拉「暂无可选项」  
- 登录会话停留在 `waiting_agent`，浏览器不会弹出  

本地 TOML 中的 `employee_id` 仅作可选覆盖，正常留空即可。

---

## 账号登录验收步骤

1. `cd central_server; .\scripts\start.ps1`  
2. 浏览器登录 → 创建管理员（若需）→ 创建运营员工  
3. `cd local_agent; .\scripts\start.ps1`（保持窗口打开，观察 `[Local Agent]` 日志）  
4. 管理员 `/agents`：设备 online → 绑定运营员工  
5. 员工 `/accounts`：Agent 状态卡「已连接」  
7. 创建运营账号 → 发起登录  
8. Agent 窗口应出现 `Claimed login session` → 启动 Chrome → 员工在浏览器内完成小红书登录  

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
[Local Agent] profiles_root=D:\AMiracle\profiles
[Local Agent] supports_account_login=True
[Local Agent] Registered as WIN-1 (agent_id=...)
[Local Agent] Heartbeat OK agent_id=... device=WIN-1
[Local Agent] Claimed 1 login session(s): ...
```

---

## 其它脚本

| 脚本 | 含义 |
|------|------|
| `分别运行 local_agent\scripts\stop.ps1 和 central_server\scripts\stop.ps1` | 停止中央 + Agent + 旧版 demo Chrome(9222) |
| `recentral_server\scripts\start.ps1` | 仅重启中央 |
| `recd central_server; .\scripts\start.ps1` | 同左 |
| `re分别运行 central_server\scripts\start.ps1 和 local_agent\scripts\start.ps1` | 全停后 `start_demo_all` |
| `cd central_server; .\scripts\reset.ps1` | 停中央+Agent，清空演示数据 |

---

## 当前「离线 / 暂无心跳」说明

若管理员看到 `WIN-1 · 离线 / 暂无心跳`，通常表示 **本机 Local Agent 进程未运行或未成功心跳**，而不是中央故障。

正确启动 `cd local_agent; .\scripts\start.ps1` 后应变为 **online + 心跳时间 + 版本**。

已处于 `waiting_agent` 的登录会话：Agent 上线并心跳正常后，会在下一轮 claim 中自动认领并拉起浏览器（无需员工重复点「发起登录」）。
