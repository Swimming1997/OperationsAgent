# 运营情报中心（OperationsAgent）

本项目分为两个部分：

- **central_server**：中央服务器，包含 FastAPI、数据库、任务队列、Web 前端和情报池。
- **local_agent**：本地采集器，运行在员工电脑，负责浏览器、账号 Profile、小红书采集和 HTTP 上报。

## 启动中央服务器

```powershell
cd central_server
.\scripts\start.ps1
```

停止：

```powershell
cd central_server
.\scripts\stop.ps1
```

## 启动 Local Agent

```powershell
cd local_agent
.\scripts\start.ps1
```

或使用仓库根目录快捷脚本：

```powershell
.\start-local-agent.ps1
```

停止：

```powershell
cd local_agent
.\scripts\stop.ps1
```

## 重置演示环境

```powershell
cd central_server
.\scripts\reset.ps1
```

## 打包当前源码供审查

```powershell
.\package_project.ps1
```

## 前端首次验证

```powershell
cd central_server\frontend
npm install
npm test
npm run build
```

## 文档索引

| 文档 | 说明 |
|------|------|
| `central_server/docs/demo/clean-start-customer-test-playbook.md` | 客户从零首跑手册 |
| `central_server/docs/demo/stage-3f-local-agent-startup.md` | Stage 3F 启动与 Agent 绑定 |
| `central_server/docs/runtime/central-startup.md` | 中央服务运行时说明 |
| `local_agent/docs/runtime/local-agent-runtime-v1.md` | Local Agent 运行时说明 |
