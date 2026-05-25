# Stage 3F：双账号登录验收

## 前置

1. `分别运行 local_agent\scripts\stop.ps1 和 central_server\scripts\stop.ps1` → `central_server\scripts\start.ps1`（FastAPI + 前端）
2. 员工机运行 Local Agent：`python scripts/run_local_agent.py --config configs/local_agent.example.toml`
3. 中央已登录主管或运营员工账号

## Case A：第一个 XHS 账号

1. 进入 **账号管理** → **添加运营账号**
2. 填写备注名 `XHS-A`，平台默认小红书，绑定本人与 Agent（可无在线 Agent）
3. 保存后点击 **发起登录**
4. 若 Agent 在线：本机弹出独立 Chrome（`profiles/accounts/<account_id>/`，独立 CDP 端口）
5. 在浏览器完成小红书登录 → 页面轮询显示 **已登录**（无需整页刷新）

## Case B：第二个 XHS 账号

1. 再添加 `XHS-B` 并 **发起登录**
2. 应出现**第二个 Chrome 进程**与**不同 CDP 端口**
3. 使用另一小红书账号登录 → B 显示已登录，A 仍为 A

## Case C：隔离性

```text
profiles/accounts/<id_A>/   # 账号 A
profiles/accounts/<id_B>/   # 账号 B
```

- 中央库 `platform_accounts.profile_key` = `accounts/<uuid>`（逻辑键，非本机绝对路径）
- `account_sessions.profile_ref` 同样存逻辑键；`session_meta.cdp_url` 指向本机端口

## 无在线 Agent

1. 创建账号仍可成功
2. 发起登录后会话状态 `waiting_agent`，页面提示「等待本地 Agent 上线」
3. 启动 Agent 后自动 claim 并打开浏览器

## 自动化

```bash
pytest tests/test_account_login_api.py -q
cd frontend && npm test -- --run
```
