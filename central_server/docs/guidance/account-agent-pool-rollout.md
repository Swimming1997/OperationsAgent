# 账号池化调度灰度与回滚

## 发布前检查
- 执行迁移 `0008_account_agent_pooling`（可选；`account_agent_bindings` 表保留但不再参与调度）。
- 确认每个**运营员工**至少登记 1 台可用 `local_agent`（账号管理页顶部「登记本地 Agent」）。
- 小红书账号只需归属运营员工；执行采集前需在某台运营设备上完成该平台账号登录（`account_sessions`）。
- 验证运营端可完成“登记本地 Agent -> 冲突确认 -> 抢占转绑”流程。

## 灰度步骤
- 第 1 阶段（10% 运营账号）：
  - 仅让试点运营使用新“登记本地 Agent”入口。
  - 监控 `job_claimed` 与 `job_failed` 事件比率。
- 第 2 阶段（50% 运营账号）：
  - 扩大至半量运营账号，观察 24 小时。
  - 抽样检查 `usage_status` 是否与实际会话一致。
- 第 3 阶段（100%）：
  - 全量启用账号池化调度。
  - 清理旧文档中 `default_agent_id` 操作说明。

## 监控指标
- 任务领取成功率：`claimed / pending`
- 任务失败率：`failed / running`
- 无可用绑定失败数：错误码 `no_available_bound_agent`（如接入）
- 运营端绑定冲突次数：`agent_bound_conflict`

## 回滚策略
- 应急回滚步骤：
  1. 暂停调度入口（停止新任务 materialize 或暂停 agent claim）。
  2. 回滚应用版本到上一稳定版。
  3. 保留 `account_agent_bindings` 表数据，不做破坏性删除。
- 数据回滚原则：
  - 仅回滚应用逻辑，不回滚绑定数据。
  - 若需要回滚数据库，执行 alembic downgrade 到 `0007_operation_rules`（会删除绑定表，需先导出数据）。

## 故障处理建议
- 若运营提示“本地 Agent 未连接”：
  - 先检查本机 bridge：`http://127.0.0.1:18765/healthz`（多进程时还有 `18766`…，前端默认扫描 `18765–18774`，可用 `VITE_LOCAL_BRIDGE_PORTS` 配置）。
  - 再在账号管理页顶部完成「登记本地 Agent」（会扫描上述端口并汇总 discover；绑定到运营员工，非小红书账号）。
- 若任务长期 pending：
  - 检查运营名下 agent 是否在线、该小红书账号是否在任一台设备上有 `ready` 会话。
  - 检查 agent 是否空闲（无其它 claimed/running 任务）。
  - 检查 agent capabilities 是否覆盖 job type。
