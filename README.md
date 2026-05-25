# AMiracle

本项目分为两个部分：

- central_server：中央服务器，包含 FastAPI、数据库、任务队列、前端和情报池。
- local_agent：本地采集器，运行在员工电脑，负责浏览器、账号 profile、小红书采集和 HTTP 上报。

启动中央服务器：

```powershell
cd central_server
.\scripts\start.ps1
```

停止中央服务器：

```powershell
cd central_server
.\scripts\stop.ps1
```

启动 Local Agent：

```powershell
cd local_agent
.\scripts\start.ps1
```

停止 Local Agent：

```powershell
cd local_agent
.\scripts\stop.ps1
```

打包当前源码供审查：

```powershell
.\package_project.ps1
```

前端首次验证：

```powershell
cd D:\AMiracle\central_server\frontend
npm install
npm test
npm run build
```
