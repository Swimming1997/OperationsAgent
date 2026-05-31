# Stage 3F：双账号登录验收

## 前置

1. 启动中央：

```powershell
cd central_server
.\scripts\start.ps1
```

2. 启动 Local Agent（保持窗口打开）：

```powershell
cd local_agent
.\scripts\start.ps1
```

3. 管理员在 `/agents` 将设备绑定到运营员工；运营在 `/accounts` 完成 **登记本地 Agent**
4. 中央已登录主管或运营员工账号

## Case A：第一个 XHS 账号

1. 进入 **账号管理** → **添加运营账号**
2. 填写备注名 `XHS-A`，平台默认小红书
3. 保存后点击 **发起登录**
4. Agent 在线时：本机弹出独立 Chrome（`local_agent\profiles\accounts\<profile_key>\`，独立 CDP 端口）
5. 在浏览器完成小红书登录 → 页面轮询显示 **已登录**（无需整页刷新）

## Case B：第二个 XHS 账号

1. 再添加 `XHS-B` 并 **发起登录**
2. 应出现**第二个 Chrome 进程**与**不同 CDP 端口**
3. 使用另一小红书账号登录 → B 显示已登录，A 仍为 A

## Case C：隔离性

```text
local_agent/profiles/accounts/<profile_key_A>/   # 账号 A
local_agent/profiles/accounts/<profile_key_B>/   # 账号 B
```

- 中央库 `platform_accounts.profile_key` = `accounts/<uuid>`（逻辑键，非本机绝对路径）
- `account_sessions.profile_ref` 同样存逻辑键；`session_meta.cdp_url` 指向本机端口

## 无在线 Agent

1. 创建账号仍可成功
2. 发起登录后会话状态 `waiting_agent`，页面提示「等待本地 Agent 上线」
3. 启动 Agent 并完成绑定/登记后，自动 claim 并打开浏览器

## 自动化

```powershell
cd central_server
..\.venv\Scripts\python.exe -m pytest tests/test_account_login_api.py -q

cd frontend
npm test -- --run
```
