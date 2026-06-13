# AGENTS.md

本仓库所有开发必须优先保证稳定性、可维护性、可拓展性。这是强约束，不是建议。

1. 稳定性优先：涉及任务调度、账号登录、采集上报、数据库模型、权限、运行状态的改动，必须保持现有契约兼容，并补充或更新对应测试。
2. 可维护性优先：新增代码必须放入清晰的业务模块，不得继续扩大已经拆分出的聚合文件或超大文件。
3. 可拓展性优先：跨 Central Server 和 Local Agent 的协议、枚举、payload 形状必须优先放入 `shared_contracts/`，不得在两侧重复发明不一致的 schema。
4. 边界强约束：Central Server 不得 import Local Agent runtime；Local Agent 不得 import Central Server 的 DB、storage、services、main。
5. 任务生命周期强约束：不得绕过 `JobRepository` 或 `intelligence_engine.jobs` 直接修改 Job 状态、claim、checkpoint、result、retry、lease 等生命周期字段。
6. 模块化强约束：新 API 路由必须放入对应 `product_*_routes.py` 或专门 route 模块；不得把新业务路由重新堆回 `product_routes.py`。
7. 模型强约束：新 DB model 必须放入领域模型文件，例如 `account_models.py`、`job_models.py`、`content_models.py`、`reference_library_models.py`、`task_models.py`、`rule_models.py`、`organization_models.py`；`models.py` 只保留兼容导出和集中索引注册。
8. 验证强约束：完成改动前必须至少运行受影响模块测试；涉及跨模块、协议、模型、前端类型或路由拆分时，必须运行后端/Local Agent/前端对应全量测试或说明无法运行的原因。

