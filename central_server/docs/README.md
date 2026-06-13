# OperationsAgent 文档索引

本文档是当前需求和运行说明的唯一入口。未列在这里的历史计划、阶段说明和评审记录不再作为开发依据。

## 当前需求与验收

| 文档 | 用途 |
|---|---|
| `guidance/p0-intelligence-center-design-v1.md` | P0 运营情报中心当前设计、API、权限、边界与验收清单 |
| `guidance/p0-acceptance-results.md` | P0 性能与 XHS SLO 验收记录 |
| `guidance/p1-development-plan.md` | P1 开发落地计划、范围边界、主线拆解与验收清单 |

## 运行与排障

| 文档 | 用途 |
|---|---|
| `runtime/central-startup.md` | 中央服务启动、停止、数据与媒体文件说明 |
| `../README.md` | central_server 本地开发、迁移和测试入口 |
| `../../local_agent/docs/runtime/local-agent-runtime-v1.md` | Local Agent 启动、配置、Profile 与 JobType |
| `../../local_agent/docs/runtime/xhs-engine-capability-matrix.md` | XHS 当前能力矩阵和真实验收状态 |
| `demo/clean-start-customer-test-playbook.md` | reset 后从零首跑手册 |

## 工程边界

| 文档 | 用途 |
|---|---|
| `refactor/module-boundaries-v1.md` | Central / Local Agent / shared_contracts 模块边界 |
| `runtime/central-boundary-check.md` | 中央侧禁止依赖 Local Agent runtime 的检查命令 |
| `../../local_agent/docs/runtime/local-agent-boundary-check.md` | Local Agent 禁止依赖中央 DB / service 的检查命令 |

## 文档维护规则

- 新需求先更新 P0/current 文档，再开发实现。
- 历史方案、评审草稿、一次性阶段手册不要继续新增到主文档树。
- 若需要保留旧材料，请放到外部归档，不作为仓库内开发入口。
