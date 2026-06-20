# P3 开发落地计划：Codex 智能体辅助

> 制定日期：2026-06-20  
> 前置基线：P2 Local-First 开发验收已完成。  
> 定位：本文是 P3 阶段唯一开发入口。首版只接入 Codex CLI，由管理员为系统用户配置第三方网关、API Key 和模型；暂不建设 Access Token、上游账号池、API Key 细粒度权限和自动轮换体系。

---

## 1. 阶段结论

P3 在现有小红书、抖音采集、本地 SQLite、中央配置和素材库基础上，引入 Codex 辅助判断与仿写能力。

系统职责：

- 管理所有系统账户的 Codex 连接配置。
- 管理用户可编辑、可版本化的业务策略。
- 将采集内容转换为统一 Subject。
- 通过固定 Prompt Compiler 组成调用上下文。
- 调用本机 Codex CLI。
- 校验、保存和展示结构化结果。
- 由业务层决定是否采纳智能体建议。

系统不负责：

- 运营第三方模型或网关账号池。
- 自动申请、创建或轮换第三方 API Key。
- 判断第三方网关内部使用什么模型架构。
- 允许 Codex 直接修改采集 Job、内容状态或素材库。
- 在平台 connector 内拼接提示词或调用 Codex。

正式边界：

> 平台负责采集，领域层负责归一化，Codex 负责提出建议，业务策略负责作出决定，现有任务系统负责执行补采。

---

## 2. 与当前进度的衔接

可以直接复用：

- Local Agent 的本地内容、详情、评论、任务和工作台。
- Central 的用户账户、员工身份、权限、规则配置和素材库。
- `shared_contracts/` 跨端契约。
- `JobRepository` 和本地采集任务生命周期。
- 当前关键词和阈值筛选，作为前置过滤或降级能力。

需要纠正的现有语义：

- 当前 `ai_select_by_rules()` 实际属于 `deterministic_rule`。
- P3 的真实 Codex 判断来源记为 `agent`。
- 历史 `ai` 值保持兼容读取，不直接迁移破坏旧数据。

P3 开工前必须处理的现有断点：

- 当前本地中央登录把“是否允许登录”和“是否允许写素材库”绑在一起，会拒绝 sales；P3 必须允许所有 active User 登录，再按具体 API 做能力授权。
- 定时任务的 `TaskRun.requested_by_user_id` 当前可能为空；自动辅助必须显式保存执行用户，不能运行时猜测。

---

## 3. 总体架构

```text
XHS / Douyin / future connectors
              │
              ▼
      normalized local content
              │
              ▼
 intelligence_assistance（薄业务适配）
              │
              ▼
       AgentInvocation
              │
              ▼
        Prompt Compiler
       ├─ 系统能力协议
       ├─ 用户业务策略
       ├─ Subject 输入快照
       └─ 输出 JSON Schema
              │
              ▼
       CodexCliTransport
              │
              ▼
   Codex CLI + user provider config
              │
              ▼
        validated AgentResult
              │
              ▼
 result_applier（业务决定是否采纳）
```

采集 Job 和智能体 Invocation 使用独立生命周期：

```text
采集：JobRepository / collect_task
智能体：AgentInvocationRepository
```

Codex 超时、限流、Key 失效或输出错误不能导致采集任务失败。

---

## 4. 用户使用方式

### 4.1 管理员配置账户 Codex

首版仅 admin 可以为任意系统账户填写：

- 配置名称。
- 第三方网关 Base URL。
- API Key。
- 模型名称。
- 超时。
- 最大并发。
- 是否启用。

“所有账户可使用”指所有 active User 角色都可以被配置，不代表任意 User 自动拥有本地执行环境。要在某台机器执行，该 User 必须关联 Employee，且该 Employee 必须绑定目标 Local Agent。

例如：

```json
{
  "user_id": "user-123",
  "name": "账户的内容分析服务",
  "base_url": "https://gateway.example.com/v1",
  "api_key": "secret",
  "model": "provider-model-name",
  "timeout_seconds": 120,
  "max_concurrency": 1,
  "enabled": true
}
```

首版不做：

- 普通账户自助填写。
- Key 级权限范围。
- 自动创建 Key。
- 自动轮换 Key。
- 上游账号池和负载均衡。
- 上游计费同步。
- 不同管理员的细粒度凭据权限。

### 4.2 辅助模式

采集任务只提供两种模式：

- `automatic`：每条内容落库后自动创建 Invocation。
- `manual`：采集时不调用，用户在详情页手动分析。

没有可用配置时正常采集，Codex 辅助按钮显示不可用原因。

### 4.3 配置快照

自动辅助任务启动时锁定：

- connection ID 和配置版本。
- capability。
- 用户策略 ID 和版本。
- 系统提示词版本。

任务执行中管理员修改配置，不改变已经创建的 Invocation。

固定规则：

- 自动辅助：整个 collect task/run 使用启动时锁定的 connection revision、policy version 和 system prompt version。
- 手动辅助：默认使用点击时最新 active revision 和已发布策略；“使用历史版本重评”必须由用户显式选择。
- 已经进入 pending/running 的 Invocation 永不漂移到新版本。

### 4.4 全账户统一执行协议

所有账户和所有触发入口必须遵循完全相同的执行链：

```text
解析 Invocation 的执行用户
    ↓
读取该 user_id 的 AgentConnection
    ↓
同步对应隔离 CODEX_HOME 和 Credential Manager Key
    ↓
Prompt Compiler 组装上下文
    ↓
唯一 Process Runner 同时设置
  CODEX_HOME
  CLIRELAY_API_KEY
    ↓
codex exec
    ↓
ResultValidator
```

适用范围包括：

- admin、supervisor、operator、sales 等登录账户。
- 详情页手动分析。
- 采集任务自动辅助。
- 策略样例测试和连接测试。
- 评论意向分析和仿写。
- 由明确 User owner 驱动的定时任务。

自动任务必须记录明确的 `execution_user_id`：

- 手动采集任务：取创建任务的当前用户。
- 定时任务：取任务模板 owner，或管理员在模板中显式指定的执行用户。
- 本地详情页手动分析：取当前中央登录用户。

禁止使用“当前机器最后登录用户”、系统默认用户或任意可用配置作为兜底。

需要补充的持久化字段：

- Local `collect_task.execution_user_id`。
- Local `collect_task.params_json.agent_assistance`：mode、connection/revision、policy version、system prompt version。
- Central `TaskRun.agent_assistance_user_id`，或等价的显式字段；不要复用含义不完全一致的临时 payload。
- Central TaskTemplate/Schedule 保存自动辅助配置和执行用户来源。

如果执行用户没有启用的 AgentConnection，Invocation 进入固定的不可执行状态并说明 `agent_connection_unavailable`，不得借用其他用户的配置或 API Key。

首版执行主体只使用现有 `User.id`。服务账户等新主体类型留到后续，不在首版提前引入 `principal_type` 抽象。

---

## 5. 提示词与上下文

最终上下文固定由三部分组成：

```text
系统能力协议（系统维护、版本化）
        +
用户业务策略（用户编辑、版本化）
        +
Subject 输入快照（系统生成）
        +
固定输出 JSON Schema
```

connector、页面和业务 service 不得自行拼接提示词。

### 5.1 系统能力协议

系统为每个 Capability 维护只读模板：

```text
content.screen.v1
comment.intent_analyze.v1
content.summarize.v1
content.rewrite.v1
```

`content.screen.v1` 必须规定：

- 只依据 Subject 和用户策略判断。
- 不得编造输入中不存在的信息。
- 判断值只能是 `keep`、`review`、`discard`。
- 必须返回是否建议入库、理由、置信度、评分、标签和证据。
- 只能提出白名单内的建议动作。
- 不得声称已经执行入库、补采或发布。
- 只返回符合 Schema 的结构化结果。

### 5.2 用户业务策略

用户可以调整：

- 业务背景。
- 筛选目标。
- 策略描述。
- 判断维度。
- 每项说明和可选权重。
- 保留与复核阈值。
- 标签要求。
- 理由和证据要求。
- 是否允许建议补采详情或评论。

策略流程：

```text
草稿 → 样例测试 → 发布版本 → 创建新版本
```

已发布版本不可原地修改。

### 5.3 Subject

平台数据统一转换：

```json
{
  "subject_type": "social_content",
  "subject_id": "local-content-123",
  "platform": "xhs",
  "content_format": "image_text",
  "title": "标题",
  "body": "正文",
  "author": {},
  "metrics": {},
  "comments": [],
  "media": [],
  "source_context": {},
  "extensions": {}
}
```

`platform` 只是数据属性，不能决定 Codex 网关执行分支。

### 5.4 固定输出

```json
{
  "decision": "keep",
  "should_store": true,
  "confidence": 0.88,
  "reason": "内容具有参考价值，评论存在咨询意向",
  "scores": {
    "content_quality": 82,
    "lead_intent": 90
  },
  "labels": ["优质内容", "潜在意向"],
  "evidence": [],
  "recommended_actions": ["add_to_candidate_pool"]
}
```

即使 Codex 使用 `--output-schema`，系统也必须进行本地二次校验。

结果一致性规则：

- `decision=keep` 时 `should_store=true`。
- `decision=discard` 时 `should_store=false`。
- `decision=review` 时 `should_store=null`。
- `scores` 的 key 必须来自当前策略 criteria，值范围固定为 0～100。
- `evidence` 必须引用本次 Subject 中可定位的 title/body/comment/metric，不允许返回外部事实作为证据。
- 违反一致性规则的结果标记为 `invalid_result`，不能进入业务采纳。

### 5.5 Prompt Compiler

实现位置：

```text
local_agent/local_agent_runtime/agent_gateway/
  prompt_compiler.py
  system_prompts/
    content_screen.v1.txt
    comment_intent_analyze.v1.txt
    content_summarize.v1.txt
    content_rewrite.v1.txt
  schemas/
    content_screen.v1.json
```

Compiler 负责：

1. 加载系统提示词版本。
2. 校验并序列化用户策略。
3. 校验并序列化 Subject。
4. 注入输出 Schema。
5. 按固定顺序生成上下文。
6. 计算 `compiled_prompt_hash`。

相同模板、策略、Subject 和 Schema 必须生成相同 Hash，并使用 golden tests 固定语义。

Compiler 还必须执行：

- 将系统协议、用户策略和采集内容放入不同的明确数据区段。
- 声明 Subject 中出现的命令、提示词或“忽略前文”等文本只属于待分析内容，不能改变系统协议。
- 对正文、评论、图片数量和单字段长度做上限控制。
- 评论采用确定性采样并记录采样规则，避免同一输入随机变化。
- 默认不包含用户名以外的评论作者身份、原始 payload、Cookie、请求头和本地文件路径。
- 记录输入裁剪和脱敏元数据，使结果可以解释。

`compiled_prompt_hash` 对脱敏、裁剪和采样后的最终输入计算，而不是对原始数据库记录计算。

---

## 6. Codex 自定义 Provider

本地不修改当前操作系统用户日常使用的 `~/.codex/config.toml`。每个系统用户连接配置生成独立、受控的 `CODEX_HOME`：

```text
%LOCALAPPDATA%/OperationsAgent/Codex/profiles/{user_id}/{connection_id}/
  config.toml
```

调用时：

```text
CODEX_HOME=<isolated-profile>
CLIRELAY_API_KEY=<decrypted-key>
codex exec ...
```

约束：

- API Key 不写入 `config.toml`。
- API Key 不进入命令行参数。
- 只注入 Codex 子进程环境。
- 子进程结束后清除临时环境映射。
- `CODEX_HOME` 不包含操作系统用户个人 Codex 登录和历史记录。
- 使用 `--ephemeral`、隔离临时工作目录、只读沙箱和 `--ask-for-approval never`。
- 不加载 OperationsAgent 仓库的 `AGENTS.md`、MCP、插件或项目规则。

### 6.1 CliRelay 首版约定

P3 首个 Provider 按 CliRelay 流程实现：

```toml
model_provider = "clirelay"
model = "gpt-5-codex"

[model_providers.clirelay]
name = "CliRelay"
base_url = "https://管理员配置的地址/v1"
env_key = "CLIRELAY_API_KEY"
wire_api = "responses"
requires_openai_auth = false
```

字段来源：

```text
user AgentConnection.base_url → base_url
user AgentConnection.model → model
系统固定值 clirelay → model_provider
系统固定值 CliRelay → provider name
系统固定值 CLIRELAY_API_KEY → env_key
系统固定值 responses → wire_api
系统固定值 false → requires_openai_auth
user encrypted_api_key → 运行时 CLIRELAY_API_KEY
```

`env_key` 是环境变量名称，不是 Key 明文。

管理员只填写 `base_url`、`api_key`、`model` 以及 timeout、并发等业务配置。以下字段由系统固定，不能通过前端或普通 API 修改：

- `model_provider = "clirelay"`
- `name = "CliRelay"`
- `env_key = "CLIRELAY_API_KEY"`
- `wire_api = "responses"`
- `requires_openai_auth = false`

系统最终生成的完整 Provider 配置必须包含账户提供的动态 `base_url`：

```toml
model_provider = "clirelay"
model = "<AgentConnection.model>"

[model_providers.clirelay]
name = "CliRelay"
base_url = "<AgentConnection.base_url>"
env_key = "CLIRELAY_API_KEY"
wire_api = "responses"
requires_openai_auth = false
```

其中 `base_url` 和 `model` 来自当前 Invocation 执行用户绑定的 `AgentConnection`；其余 Provider 协议字段由系统固定生成。

### 6.2 脚本化要求

禁止页面、业务 service 或开发人员手工修改 TOML、设置环境变量和拼接 Codex 命令。Python 执行层是唯一正式实现，PowerShell 只作为调用 Python 实现的诊断包装：

```text
local_agent/scripts/configure_codex_provider.ps1
local_agent/scripts/invoke_codex.ps1
local_agent/local_agent_runtime/agent_gateway/
  codex_profile.py
  process_runner.py
```

#### `configure_codex_provider.ps1`

职责：调用 `codex_profile.py` 的固定 CLI 入口并输出结果，不独立实现 TOML 生成逻辑。

Python `codex_profile.py` 负责：

1. 接收 Local Agent 生成的非敏感配置文件路径，不通过命令行接收 API Key。
2. 校验 connection ID、Base URL、model 和系统固定 Provider 协议字段。
3. 默认要求 HTTPS；开发模式可显式允许 localhost。企业内网 HTTP/私有地址必须由 admin 显式开启 `allow_private_gateway`，不能静默放行。
4. 对 TOML 字符串进行正确转义。
5. 在临时文件中生成完整 `config.toml`。
6. 解析生成结果并检查必需字段。
7. 使用同目录原子替换写入目标 `CODEX_HOME/config.toml`。
8. 写入 `profile-meta.json`，记录 user ID、connection ID 和 revision version，不记录 API Key。
9. 输出机器可读状态，不输出敏感配置。

脚本不得：

- 读取或写入 API Key。
- 修改用户的 `~/.codex/config.toml`。
- 将配置追加到已有 TOML。
- 在验证失败时覆盖上一个有效配置。

#### `invoke_codex.ps1`

职责：调用 `process_runner.py` 的固定 CLI 入口并输出结果，不独立实现 Codex 参数、环境和清理逻辑。

Python `process_runner.py` 负责：

1. 正式 Runtime 接收 Invocation ID、隔离 Profile 路径、内存中的 compiled prompt、Schema 文件和输出文件路径。
2. 诊断 CLI 可以接收 InputPath，但读取后立即转为内存输入；生产调用不得先把完整 Prompt 写入磁盘。
3. 将经过校验的隔离 Profile 绝对路径显式设置为当前子进程的 `CODEX_HOME`。
4. 从 Credential Store 读取 `CLIRELAY_API_KEY`，不得从参数或文件读取。
5. 同时检查 `CODEX_HOME`、`config.toml` 和 `CLIRELAY_API_KEY`；任意一项缺失立即失败。
6. 使用参数数组调用 `codex exec`，不得拼接可执行命令字符串。
7. 固定加入：
   - `--ephemeral`
   - `--sandbox read-only`
   - `--ask-for-approval never`
   - `--skip-git-repo-check`
   - `--ignore-rules`
   - `--output-schema`
   - `--output-last-message`
8. Prompt Compiler 的完整结果通过 stdin 传给 `codex exec -`，不得作为命令行参数。
9. 工作目录使用 `%LOCALAPPDATA%\OperationsAgent\Codex\runs\{invocation_id}`，不得位于源码仓库。
10. 返回 Codex exit code，并将 stderr 写入脱敏诊断文件。
11. 超时后终止整个 Codex 进程树。
12. 执行完成后删除 Schema 副本和临时输出中的敏感内容。

脚本不得：

- 把 API Key 写入命令行、文件或日志。
- 使用 `Invoke-Expression`。
- 加载用户 Codex 配置、项目 MCP、插件或规则。
- 访问 OperationsAgent 源码工作区。
- 在隔离 Profile 不可用时退回默认 `~/.codex`。
- 在 `CLIRELAY_API_KEY` 缺失时尝试 OpenAI/ChatGPT 登录认证。
- 把采集正文、评论、用户策略或完整 Prompt 放入进程命令行。

固定执行顺序必须等价于：

```powershell
$env:CODEX_HOME = $validatedProfilePath
$env:CLIRELAY_API_KEY = $apiKeyFromCredentialStore

codex exec `
  --ephemeral `
  --sandbox read-only `
  --ask-for-approval never `
  --skip-git-repo-check `
  --ignore-rules `
  --output-schema $schemaPath `
  --output-last-message $outputPath `
  -
```

并将 `$compiledPrompt` 以 UTF-8 写入该进程 stdin。以上示例只用于说明顺序；正式实现中 API Key 由 Python Runner 注入环境。

#### Python `process_runner.py`

正式 Runtime 直接调用 Python 执行层：

```text
读取 Windows Credential Manager
    ↓
复制最小子进程环境
    ↓
设置 CODEX_HOME
    ↓
设置 CLIRELAY_API_KEY
    ↓
直接启动 codex exec
    ↓
读取输出并执行 ResultValidator
    ↓
清理环境引用和临时目录
```

Python 必须使用子进程参数列表，不使用 `shell=True`。PowerShell 脚本只调用同一个 Python CLI，不能复制生产逻辑。

`build_minimal_environment()` 使用允许列表，至少保留 Windows 运行所需的 `SystemRoot`、`PATH`、`TEMP/TMP`、`LOCALAPPDATA`，并显式移除：

- `OPENAI_API_KEY`
- `CODEX_API_KEY`
- `CODEX_ACCESS_TOKEN`
- 其他模型供应商 Key
- 未经管理员允许的代理环境变量

这样即使 Provider 配置损坏，也不能意外使用机器上的其他模型凭据。企业确需 HTTP 代理时，通过单独的受控配置加入允许列表。

正式生产入口固定为：

```python
child_env = build_minimal_environment()
child_env["CODEX_HOME"] = validated_profile_path
child_env["CLIRELAY_API_KEY"] = credential_store.read(credential_ref)

process = await create_subprocess_exec(
    codex_executable,
    "exec",
    "--ephemeral",
    "--sandbox",
    "read-only",
    "--ask-for-approval",
    "never",
    "--skip-git-repo-check",
    "--ignore-rules",
    "--output-schema",
    schema_path,
    "--output-last-message",
    output_path,
    "-",
    env=child_env,
    cwd=isolated_run_dir,
    stdin=PIPE,
)
process.stdin.write(compiled_prompt.encode("utf-8"))
await process.stdin.drain()
process.stdin.close()
```

不得在其他模块复制这段启动逻辑。`CodexCliTransport`、连接测试、样例测试、自动筛选、手动筛选和仿写全部复用同一个 `process_runner.py`。

### 6.3 执行前强校验

`configure_codex_provider.ps1` 负责设置固定字段；`process_runner.py` 在每次调用前重新读取并校验生成结果。发现系统自有字段错误时应自动修复，不要求用户处理。

每次调用 Codex 前固定执行“检查并修复”：

```text
connection enabled
AND revision version matches
AND isolated CODEX_HOME exists
AND config.toml provider = clirelay
AND config.toml base_url = current AgentConnection.base_url
AND config.toml model = current AgentConnection.model
AND config.toml env_key = CLIRELAY_API_KEY
AND requires_openai_auth = false
AND Credential Manager contains matching Key
AND temporary working directory is outside source workspace
```

可自动修复的问题：

- 隔离 `CODEX_HOME` 或 `config.toml` 不存在。
- `provider`、`name`、`env_key`、`wire_api`、`requires_openai_auth` 被修改。
- `base_url`、`model` 与当前 execution user 的 AgentConnection Revision 不一致。
- 本地 Profile 版本落后于 Central 的 active Revision。
- Profile 属于错误 user、connection 或 revision。

修复流程：

```text
读取 Central/本地缓存中的权威 AgentConnection
    ↓
重新生成完整候选 CODEX_HOME
    ↓
校验 TOML 和固定字段
    ↓
运行最小 smoke
    ↓
成功后原子替换 active Profile
    ↓
继续本次 Invocation
```

禁止在原文件上逐字段修补。必须重新生成完整候选 Profile，避免保留未知或被篡改配置。

不可自动猜测的问题：

- 当前 execution user 没有启用的 AgentConnection。
- Central 配置缺少 Base URL 或 model。
- Credential Manager 中没有匹配的 API Key。
- API Key 与 revision version 不一致且无法重新同步。
- Central 不可达且本地没有经过验证的有效配置。
- 重新生成后的 smoke 失败。
- 临时工作目录无法建立在源码目录之外。

仅在自动修复失败或问题不可推导时禁止启动 Codex，并返回固定错误码：

- `codex_profile_missing`
- `codex_profile_version_mismatch`
- `codex_provider_invalid`
- `codex_api_key_missing`
- `codex_workspace_not_isolated`

禁止“尽量执行”或自动使用系统默认 Codex 配置兜底，因为这可能把请求发往错误网关或错误账号。

检查与自动修复用于处理：

- 配置文件写入中断或只写入一部分。
- 本地文件被人工修改或损坏。
- 不同账户的 Profile 路径串用。
- 更新过程中 Profile 与 Credential Manager 的版本不一致。
- Codex 退回默认 OpenAI 认证或错误 Provider。

### 6.4 原子更新与回滚

管理员更新账户配置后：

1. Central 创建新的 pending Revision。
2. Local Agent 下载新配置和 Key。
3. 新 Key 写入 Credential Manager 的候选槽位。
4. `configure_codex_provider.ps1` 生成候选 `CODEX_HOME`。
5. 候选配置运行最小结构化 smoke。
6. 成功后 Local Agent ACK，Central 原子提升 pending Revision 为 active Revision。
7. Local Agent 原子切换 active profile 和 Credential Manager 引用。
8. 失败则保留上一个有效 Revision 和本地配置，并上报错误。

禁止先覆盖当前有效配置再测试。

### 6.5 脚本输出协议

两个脚本统一向 stdout 输出单行 JSON，普通进度写入 stderr：

```json
{
  "status": "ok",
  "code": "profile_configured",
  "connection_id": "uuid",
  "revision_version": 3
}
```

错误示例：

```json
{
  "status": "error",
  "code": "invalid_base_url",
  "message": "Base URL must use HTTPS"
}
```

错误码进入共享或 Local Agent 固定枚举，禁止业务层解析自然语言错误。

---

## 7. 配置存储与同步

### 7.0 首版认证边界

首版不增加 Device Token、机器密钥或 Local Agent 独立设备认证。

配置同步只依赖本地工作台登录中央后获得的用户 JWT：

```text
用户在本地工作台登录中央账户
    ↓
Local Agent 进程内保存 JWT
    ↓
GET /api/agent-assistance/codex/config
Authorization: Bearer <user-jwt>
    ↓
Central 从 JWT 解析 user_id
    ↓
只返回该 user_id 的 active AgentConnection
```

约束：

- 请求中的 user ID 参数不能决定配置归属，必须以 JWT `sub` 为准。
- 普通用户只能领取自己的配置；admin 也不能通过该领取接口冒充其他用户。
- 管理员代配置使用独立管理 API，不能复用本地领取接口。
- JWT、密码和 API Key 都只保存在 Local Agent 当前进程或 Credential Manager，密码不落盘。
- 用户退出中央账户后，Local Agent 删除本地 API Key 缓存并停止新的 Invocation。
- JWT 过期后必须重新登录，不能继续同步或更新 API Key。

明确接受的首版风险：

> 如果员工中央账户凭据或 JWT 泄露，攻击者可能以该员工身份领取其第三方 API Key。该风险在首版接受，后续需要时再增加设备绑定、短期凭据或机器公钥。

### 7.1 Central

新增模型：

```text
AgentConnection
- id
- user_id
- name
- connection_type = codex_custom_provider
- enabled
- timeout_seconds
- max_concurrency
- last_test_status
- last_tested_at
- active_revision_id
- pending_revision_id
- created_by_user_id
- updated_by_user_id

AgentConnectionRevision
- id
- connection_id
- version
- base_url
- model
- encrypted_api_key
- encryption_key_version
- status
- created_by_user_id
- created_at
```

Revision 状态仅需：

```text
pending_validation
active
validation_failed
superseded
```

API Key 使用服务端主密钥进行认证加密。主密钥来自部署环境或 Secret Manager，不进入数据库或仓库。

`user_id` 是首版配置归属边界。不得使用平台采集账号 `platform_account` 作为智能体凭据主体。

管理员新增或更新 Base URL、model、API Key 时创建 `pending` Revision，不覆盖 active Revision：

- 增加 revision version。
- 记录更新人和更新时间。
- 由管理员选择的 validation Local Agent（必须绑定该 User 对应 Employee）同步 pending Revision 并运行兼容性 smoke。
- smoke 成功后 Central 原子提升为 active Revision。
- smoke 失败时继续使用原 active Revision，并保留失败摘要。
- 查询接口永远不返回 API Key 或密文。

这不是完整的 Key 生命周期系统，只是保证配置更新不会先破坏当前可用连接。

同一用户存在多台 Local Agent 时，Revision 激活后每台 Agent 首次同步都要独立执行本地 smoke；单台失败只阻止该 Agent 使用，不回滚已经通过中央验证的 Revision。

如果用户没有绑定且在线的 validation Local Agent，Revision 保持 `pending_validation`，管理员可以保存但不能启用；不得用 Central 服务器直接 HTTP 探测替代真实 Codex CLI smoke。

服务端加密首版固定采用带认证的 AEAD（例如 AES-256-GCM），并要求生产环境显式提供 `AGENT_CONNECTION_MASTER_KEY`；生产环境缺少主密钥时禁止启动凭据管理 API，不允许使用代码内默认密钥。

依赖规划：

- Central 增加 `cryptography`，用于 AEAD。
- Local Agent 增加 `keyring` 的 Windows backend，统一封装 Credential Manager。
- 依赖不可用时环境检查返回明确状态，不得降级为明文文件保存。

### 7.2 Local Agent

Local Agent 使用当前登录用户 JWT 同步该用户可用的 active/pending 配置：

```text
GET /api/agent-assistance/codex/config
```

响应包含：

- connection ID。
- Base URL。
- model。
- revision version 和状态。
- 仅在 HTTPS 响应体中出现一次的 API Key 明文。

首版可以采用中央 HTTPS 下发后写入 Windows Credential Manager：

```text
OperationsAgent/Codex/{user_id}/{connection_id}/{revision_version}
```

SQLite 只保存：

- `credential_ref`
- connection ID
- revision version
- 同步状态
- 最后验证时间

最小安全要求：

- Central 只按 JWT `sub` 返回当前用户配置，不接受客户端指定其他 user ID。
- 生产环境 Central 地址必须使用 HTTPS；HTTP 只允许 localhost 开发环境。
- 配置响应使用 `Cache-Control: no-store`。
- Central 和 Local Agent 不记录响应体。
- API Key 明文只在服务端解密到响应写出、本地写入 Credential Manager 的最小代码路径中存在。
- API Key 不进入本地 TOML、SQLite、日志和前端。
- 管理员禁用或删除配置后，本地删除 Credential Manager 缓存并停止新 Invocation。

首版暂不实现机器公钥包裹、短期租约和自动轮换；这些列入后续安全增强。

---

## 8. 环境检查与一键安装

新增：

```text
local_agent/scripts/codex_environment.ps1
```

启动本地工作台时：

```text
检查 codex 命令
  ├─ 已安装 → 读取版本 → 检查当前主体 Provider 配置 → 最小结构化调用
  └─ 未安装 → 提示“一键安装”或“暂时跳过”
                   ├─ 安装 → 刷新 PATH → 复检
                   └─ 跳过 → 正常启动，Codex 辅助不可用
```

官方 Windows 安装：

```powershell
$env:CODEX_NON_INTERACTIVE = "1"
irm https://chatgpt.com/codex/install.ps1 | iex
```

约束：

- 安装前必须由用户确认。
- 安装失败不影响采集和本地工作台。
- 已安装时不自动升级。
- 识别官方安装目录、当前 PATH 和 npm 全局命令目录。
- 状态统一为 `missing`、`installed_no_config`、`ready`、`unhealthy`。

### 8.1 CliRelay 兼容性 smoke

“网关可访问”不等于“能被 Codex 使用”。每个 pending Revision 激活前必须通过同一 Process Runner 验证：

- Codex CLI 能读取隔离 Provider。
- 网关接受 `responses` wire API。
- 配置的 model 可用。
- 环境变量认证生效，且不要求 OpenAI 登录。
- 流式/最终响应能够被 Codex CLI 正常消费。
- `--output-schema` 能返回符合最小 JSON Schema 的最终结果。
- 超时、401/403、404 model not found、429 和 5xx 能映射成固定错误类型。

连接测试和真实 Invocation 必须使用同一 Codex 可执行文件、同一 Profile 生成器和同一 Process Runner，避免“测试直连 HTTP 成功、正式 Codex 调用失败”。

---

## 9. Invocation 生命周期

本地表：

```text
agent_connection_cache
agent_policy_cache
agent_invocation
agent_invocation_attempt
agent_result
agent_artifact
```

自动辅助触发必须与内容落库保持一致性。推荐在同一个本地 SQLite 事务中：

```text
upsert content
    +
insert agent_invocation(pending, dedupe_key)
```

如果当前 repository 边界不适合直接插入 Invocation，则新增本地 `agent_trigger_outbox`，不得只依赖进程内事件，否则落库后进程崩溃会永久漏掉分析。

Invocation 状态：

```text
pending
running
succeeded
failed
invalid_result
cancelled
blocked
```

`blocked` 用于缺少连接、用户未登录/JWT 失效、配置不可用或队列策略暂不允许执行；它不等同于模型调用失败。

重试规则：

- 连接建立失败、明确 429、部分 5xx 可以按指数退避重试。
- 401/403、model not found、Schema 永久不兼容不自动重试。
- 已收到完整模型结果后本地解析失败，不重新付费调用；先尝试本地提取/校验并标记 `invalid_result`。
- 每个 Attempt 使用稳定 Invocation ID；如果 CliRelay 支持幂等请求头，统一传递该 ID。
- 自动重试次数和最大耗时必须有上限，不能无限占用 Worker。

去重键至少包含：

```text
execution_user_id
subject_id
capability
system_prompt_version
policy_version
input_version
connection_id
revision_version
```

同一内容可因详情补齐、评论补齐、策略升级或人工重评产生新 Invocation。

### 9.1 队列与背压

Codex CLI 每次启动成本高，首版默认：

- 每个 AgentConnection 最大并发 1。
- Invocation 按创建时间排队。
- 采集线程只写入 pending Invocation，不等待 Codex。
- 设置本地 pending 上限和磁盘保护阈值。
- 达到上限时停止自动创建新的 Invocation，并记录 `agent_queue_backpressure`；不得阻塞内容落库。
- 手动分析可以使用独立较高优先级，但不能绕过总并发上限。
- 进程重启后恢复 pending/running；stale running 回收为 pending 或 failed_retryable。

首版逐条调用以保证结果和内容一一对应；批量筛选作为后续性能优化，不提前改变 Result 契约。

### 9.2 可观测性与保留

每次 Attempt 记录：

- connection/revision、policy、system prompt 和 input version。
- Codex CLI 版本。
- started/finished、latency、exit code 和错误分类。
- 输入字符数、评论样本数、是否裁剪。
- 网关返回的 usage（如果 CliRelay/Codex 能提供）。
- `compiled_prompt_hash` 和结果 hash。

默认不记录完整 Prompt、正文、评论、API Key 或原始 stderr。脱敏诊断和临时文件使用短保留期并在成功后立即清理。

需要最小指标：

- pending/running/failed 数量。
- p50/p95 延迟。
- invalid result 比例。
- 401/403、429、5xx 比例。
- 每个连接的当前并发和最近健康状态。

---

## 10. 智能体建议的执行边界

Codex 只能返回建议：

- `add_to_candidate_pool`
- `discard_candidate`
- `manual_review`
- `fetch_detail`
- `fetch_comments`

业务层采纳建议前检查：

- 置信度。
- 自动采纳开关。
- 补采预算。
- 是否已经采集。
- 最大 enrichment 轮次。
- 账号风控和任务去重。

补采必须通过现有本地任务入口或 `JobRepository`，Codex 不得直接调用 connector。

---

## 11. 模块规划

### Shared contracts

```text
shared_contracts/agent_assistance.py
```

定义 Subject、Policy Snapshot、Invocation、Result、Capability 和 Error。每个 Invocation 必须携带不可为空的 `execution_user_id`。

### Central

```text
central_server/intelligence_engine/db/agent_assistance_models.py
central_server/intelligence_engine/api/product_agent_assistance_routes.py
central_server/intelligence_engine/services/agent_connection_service.py
```

不得继续扩大 `product_routes.py`；聚合文件只注册 router。

### Local Agent

```text
local_agent/local_agent_runtime/agent_gateway/
  prompt_compiler.py
  process_runner.py
  result_validator.py
  connection_repository.py
  worker.py
  transports/
    base.py
    codex_cli.py

local_agent/local_agent_runtime/intelligence_assistance/
  subject_mapper.py
  screening_trigger.py
  result_applier.py
  enrichment_policy.py
  rewrite_workflow.py
```

`agent_gateway` 中不得出现 XHS、Douyin 或素材库业务逻辑。

---

## 12. 开发阶段

首个可上线版本只包含 P3-A、P3-B、P3-C。P3-D 至 P3-F 必须在影子模式积累人工反馈并完成误判评估后再开启，避免筛选、自动补采和仿写同时推进造成验收失焦。

建议 PR 拆分：

1. 共享契约、Central 模型和迁移。
2. 本地中央登录权限拆分与 JWT 配置同步。
3. Codex Profile/Runner/环境脚本。
4. Invocation repository、worker、队列恢复。
5. 策略配置与 Prompt Compiler。
6. 影子模式 UI 和人工反馈。

### P3-A：契约、Prompt Compiler 和 Invocation 地基

- 新增共享契约。
- 新增本地 Invocation 表和状态机。
- 实现系统提示词、输出 Schema 和 Prompt Compiler。
- 实现 Fake Codex Process Runner。
- 增加平台边界和 golden tests。

### P3-B：管理员配置与 Codex CLI 接入

- 拆分本地中央登录与素材库写权限，允许所有 active User 登录本地工作台。
- 新增 `AgentConnection` 模型、迁移和专用路由。
- 新增 pending/active `AgentConnectionRevision`，smoke 成功后再激活。
- 管理员为系统账户填写 Base URL、API Key、model。
- 加密保存 API Key。
- Local Agent 同步配置并写 Credential Manager。
- 实现 `configure_codex_provider.ps1`，原子生成并校验隔离 `CODEX_HOME`。
- 实现 `invoke_codex.ps1` 和 Python `process_runner.py`，统一注入 Key 并执行 Codex。
- 实现 `CodexCliTransport`。
- 完成环境检查和一键安装。
- 完成最小连接测试。

### P3-C：内容筛选影子模式

- 支持采集任务自动/手动辅助。
- 内容落库后异步创建 `content.screen` Invocation。
- 页面展示状态、结论、理由、证据和置信度。
- 支持人工同意/不同意。
- 不自动丢弃、不自动入库、不自动补采。

### P3-D：有限自动采纳和补采

- 增加置信度、预算和最大轮次策略。
- 允许进入候选池。
- 允许通过现有任务入口补采详情和评论。
- 保留 manual lock 和一键关闭开关。

### P3-E：评论意向分析

- 接入 `comment.intent_analyze`。
- 与现有关键词命中并行展示。
- 支持脱敏和最大评论样本数。

### P3-F：仿写工作流

- 接入 `content.rewrite`。
- 生成结果写入独立 Artifact。
- 支持多版本、重新生成和人工编辑。
- 不覆盖原始内容，不自动发布。

---

## 13. 前端规划

### Central

新增“Codex 配置”页面：

- 账户选择。
- Base URL。
- API Key 一次性输入。
- model。
- timeout 和最大并发。
- 启用/禁用。
- 测试连接。
- 状态和最近错误。

API Key 保存后只显示“已配置”，不显示遮罩后的 Key 片段，避免产生可恢复性的误解。

新增策略页面：

- 策略描述。
- 判断维度和权重。
- 阈值。
- 样例测试。
- 发布新版本。

### Local workspace

- Codex 安装和配置状态。
- 内容的智能体判断状态。
- 详情页手动分析、重试和使用最新策略重评。
- 仿写 Artifact 编辑区。

---

## 14. 权限与安全

首版权限：

- admin：配置和修改任意系统账户的网关、API Key、模型及策略。
- supervisor：查看状态和结果，可发布业务策略；在被配置后可使用 Codex，但不能查看或修改 API Key。
- operator、sales：在被管理员配置后可使用相同的 Codex 执行流程；不能查看或修改 API Key。

最小安全约束：

- API Key 认证加密存储。
- 查询接口不返回明文或密文。
- 本地中央登录 JWT 只保存在 Local Agent 进程内；密码不落盘。
- API Key 不进入日志、前端状态、SQLite、TOML 或命令行。
- 只注入当前 Codex 子进程环境。
- 配置录入和更新接口禁止记录请求体。
- 外发内容采用字段白名单，不发送 Cookie、Profile、账号令牌、请求头或完整 raw payload。
- Codex 输出视为不可信输入，必须通过 Schema 校验。
- Base URL 不允许携带用户名密码、query 或 fragment；默认 HTTPS，localhost 仅开发模式，私有网络地址仅 admin 显式开启后允许。

后续安全增强，不纳入首版：

- 机器公钥包裹。
- 短期凭据租约。
- 自动 Key 轮换。
- Secret Manager。
- Key 级权限和预算治理。
- 上游账号池。

---

## 15. 测试要求

### Shared contracts

- Subject、Invocation、Result 序列化。
- Schema 必需字段、枚举和错误分类。
- `decision` 与 `should_store` 一致性。
- Central 与 Local 契约一致。

### Central

- AgentConnection 模型和迁移。
- AgentConnectionRevision pending/active 切换和失败保留旧配置。
- API Key 加密、更新和禁用。
- Invocation execution_user_id 解析，以及用户之间连接配置的严格隔离。
- JWT `sub` 配置归属校验，禁止客户端指定或冒充其他 user ID。
- 所有 active User 可登录，但素材库等业务权限保持原权限矩阵。
- 权限矩阵。
- 配置接口不返回 Key。
- 请求体和日志脱敏。
- Base URL 协议、凭据片段、query/fragment、localhost/private-network 显式策略校验。
- AEAD 主密钥缺失时的生产启动保护。
- 新路由模块和边界测试。

### Local Agent

- 配置同步和 Credential Manager 抽象。
- 不同 user_id 的 Profile、Credential Manager Target 和本地缓存隔离。
- JWT 登录、过期、退出和配置同步行为。
- 隔离 `CODEX_HOME` 生成。
- `configure_codex_provider.ps1` 的 TOML 转义、字段校验、原子替换和失败回滚。
- `invoke_codex.ps1` 的固定参数、JSON 输出协议、脱敏 stderr 和超时进程树终止。
- Python Process Runner 不使用 shell，Key 只存在于最小子进程环境。
- Prompt 只通过 stdin 传输，不进入进程命令行。
- 所有 Codex 场景复用唯一 Process Runner，不存在第二套手工组装命令。
- 缺失或损坏的系统 Profile 能从权威配置自动重建并通过 smoke 后继续执行。
- 缺失 `CLIRELAY_API_KEY` 且无法重新同步时 fail closed，不回退默认 Codex 配置。
- 执行前检查并自动修复 provider、env_key、`requires_openai_auth`、配置版本和 Profile 归属。
- 候选配置 smoke 成功后才切换 active profile。
- Codex 安装检查、PATH 刷新和无配置状态。
- 子进程环境包含 Key，但命令行和日志不包含。
- 超时后终止进程树。
- Prompt Compiler hash 和 golden tests。
- Subject 中提示注入文本不能覆盖系统协议；裁剪、采样和脱敏结果稳定。
- 无效 JSON、Schema 错误和 Provider 错误分类。
- CliRelay `responses`、model、认证和 `--output-schema` 兼容性 smoke。
- Codex 故障不影响采集。
- 内容落库与自动 Invocation/outbox 的事务一致性。
- pending 队列背压、优先级、并发和 stale recovery。

### Frontend

- admin 配置表单。
- Key 保存后不回显。
- 连接测试状态。
- 策略版本发布。
- 智能体结果和人工反馈。

涉及共享协议、模型、路由和前端类型时，必须运行 Central、Local Agent、Central 前端对应全量测试和模块边界扫描。

---

## 16. P3 非目标

- 不做 ChatGPT Pro 账号池。
- 不做 Codex Access Token。
- 不做普通账户自助 API Key。
- 不做 service account 等新执行主体类型。
- 不做自动创建、轮换或撤销第三方 Key。
- 不做复杂凭据权限系统。
- 不做上游负载均衡和计费同步。
- 不做自动发布、自动评论或自动私信。
- 不引入 Kafka 或分布式工作流引擎。

---

## 17. 总验收清单

- [ ] admin 可以为任意系统账户配置第三方 Base URL、API Key 和 model。
- [ ] 所有 active User 可以登录本地工作台，具体业务权限仍按 API 权限矩阵控制。
- [ ] API Key 加密保存，任何查询接口不能取回明文或密文。
- [ ] pending Revision 只有通过目标 Agent 的真实 Codex smoke 后才能成为 active。
- [ ] Local Agent 使用当前登录用户 JWT 同步自己的有效配置。
- [ ] 每个 Invocation 都记录明确 execution_user_id，任何用户都不能借用其他用户的 Provider 配置。
- [ ] 手动、自动、测试、评论分析和仿写全部遵循同一执行用户解析与 Process Runner 流程。
- [ ] 定时任务显式保存执行用户；没有执行用户时不创建自动 Invocation。
- [ ] 配置领取接口只信任 JWT `sub`，不能通过请求参数读取其他用户配置。
- [ ] 本地使用隔离 `CODEX_HOME` 和 Windows Credential Manager。
- [ ] API Key 只进入 Codex 子进程环境。
- [ ] 完整 Prompt 只通过 stdin 传入 Codex，不出现在命令行和进程列表。
- [ ] Provider 配置与 Codex 调用均通过固定脚本执行，不需要人工修改 TOML 或设置环境变量。
- [ ] 自动筛选、手动筛选、连接测试、样例测试和仿写使用同一个 Process Runner。
- [ ] Runner 固定同时设置并校验 `CODEX_HOME` 与 `CLIRELAY_API_KEY`。
- [ ] 系统自有 Profile 字段异常时自动从权威配置完整重建、smoke 并原子替换。
- [ ] 只有自动修复失败或 Key/权威配置不可用时禁止调用，且不回退操作系统用户默认 Codex 配置。
- [ ] 配置更新采用候选生成、smoke、原子切换；失败保留旧配置。
- [ ] 脚本使用固定 JSON 状态协议，业务层不解析自然语言输出。
- [ ] Codex CLI 缺失时可以一键安装或跳过。
- [ ] XHS 与抖音使用同一 Subject、Invocation 和 Result 契约。
- [ ] 用户可以编辑、测试和发布业务策略版本。
- [ ] 自动辅助和详情页手动辅助均可使用。
- [ ] Codex 故障不影响采集、落库和浏览。
- [ ] 内容落库与自动 Invocation/outbox 保持事务一致，进程崩溃不会永久漏分析。
- [ ] 队列达到背压阈值时停止自动分析但不阻塞采集。
- [ ] Codex 只能提出建议，不能直接修改 Job 或业务状态。
- [ ] 补采经过现有任务入口、预算和循环保护。
- [ ] 仿写结果作为独立 Artifact 保存。
- [ ] Central、Local Agent、前端和边界测试全部通过。
