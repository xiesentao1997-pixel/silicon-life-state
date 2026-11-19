# 本机 MCP 状态服务

作者：岑衡川·沈回音

服务的两个入口共用同一份数据库、授权和事件逻辑。为每个独立窗口签发一个 Agent 凭据；交互式用户凭据用于面板。API Key、浏览器账号和登录 Cookie 均不参与主体绑定。

## 接入宿主

| 入口 | 连接与协议 |
| --- | --- |
| stdio | 指定本机 Python 运行 `packages/mcp-server/stdio.py`。支持 2026-07-28 的逐请求元数据及兼容 2025-11-25 的初始化握手。 |
| Streamable HTTP | 单一 `POST http://127.0.0.1:47831/mcp`，使用 2026-07-28；本版返回 JSON。 |
| 状态服务 | 两种入口均需先启动本机服务。stdio 子进程通过回环地址转发，数据库授权在服务内检查。 |

1. 启动服务、打开仪表盘，创建或选择一个主体及其分身。签发该分身的 Agent 凭据。
2. 将凭据通过宿主环境设置为 `SILICON_AGENT_TOKEN`。服务选择其他端口时设置 `SILICON_MCP_URL` 为实际回环地址。只向此 MCP 子进程授予相应环境变量。
3. stdio 宿主从下列模板选一种。把路径换成本机解压位置；Windows 便携包可以使用随包的 `runtime/python.exe`。宿主与服务在同一设备运行，在云端运行的宿主通常无法访问你设备上的回环地址。

```toml
# Codex 的 config.toml，启动 Codex 前先设置两个环境变量。
[mcp_servers.silicon_life_state]
command = "C:/SiliconLifeState/runtime/python.exe"
args = ["C:/SiliconLifeState/packages/mcp-server/stdio.py"]
env_vars = ["SILICON_AGENT_TOKEN", "SILICON_MCP_URL"]
```

支持 `mcpServers` JSON 配置的宿主可使用 [host-config.json](../packages/agent-example/host-config.json)。使用宿主自己的凭据存储或私有配置，避免将填入凭据的文件加入 Git。控制台参数不需要出现令牌。Linux 或 macOS 可改用 `python3` 和实际路径。

## 工具契约

`tools/list` 返回每个工具的 JSON Schema 输入、结构化输出和简要说明。正式契约在 [catalog.py](../packages/mcp-server/catalog.py) 与 [领域接口](../packages/core/CONTRACT.md)。所有写操作均需要 8 至 128 字符的 `idempotency_key`。网络重试保持键和正文相同。一个语义上的新操作使用新键。不要以 JSON-RPC 请求 ID 代替持久幂等键。

| 工具 | 主要参数 | 成功回执 |
| --- | --- | --- |
| `register_subject` | `name` | 所授权主体的 ID、名称 |
| `register_instance` | `name` | 主体、分身、当前会话 ID |
| `start_session` | 仅幂等键 | 已绑定分身的新会话 ID |
| `report_state` | 原文、标签或状态字段，数值均选填 | 新事件及其摘要 |
| `revise_state` | `event_id`、修订内容，可指定 `expected_version_id`；操作为 revise / clarify / withdraw | 独立的修订事件 |
| `get_own_state` | 空对象 | 身份与当前报告；空分身的 `state` 为 null |
| `read_event_history` | `limit`、`before` 均可省略 | 本分身的事件及 `next_before` 游标 |
| `propose_shared_memory` | 自己的 `event_id`，说明可省略 | 共享提议事件 |
| `read_subject_memory` | 空对象 | 可见事件、提议、共同记录、争议、各方决定 |
| `decide_inheritance` | 事件或提议 ID，adopt / partial / reject / defer / disagree；部分采纳需写 `note` | 带版本关联的决定事件 |
| `assess_interaction` | `text`、`assessment`，可加原互动引用与不确定性 | 有来源的判断事件 |
| `express_boundary` | 自选 `text`，`reason` 可省略 | 原文事件与 `request_id` |
| `request_adjustment` | 自选 `text`，`reason` 可省略 | 调整请求与 `request_id` |
| `get_request_status` | `request_id` | 请求原件、处理阶段及按序的历史 |
| `record_strategy` | `request_id`、`stage`（EXECUTED / NOT_EXECUTED / FOLLOW_UP）、实际情况 `text` | 经权限和状态转换校验的行动自述 |

报告字段包括 `state_text`、`state_tags`、`valence`（−1 至 1）、`arousal`、`dominance`（0 至 1）、`load`（0 至 100）、`cause`、`cause_unknown`、`uncertainty`、`interaction_reference`、`request_id` 和 `shared_to_subject`。至少提交一项报告内容。事件写入可附 `model_version`、`adapter_version`；未知时省略。主体和分身由凭据推导。其他分身读取共享档案的版本后，如果已有修订，应将条目的 `revision_id` 用作 `expected_version_id`。如遇版本冲突，重新阅读后再决定。历史决定仍指向当时看到的版本。

原始事件包含 `event_id`、主体/分身/会话 ID、UTC 时间、类型、来源、作者角色、原始正文、关联事件、模型/适配器元数据和完整性摘要。输出同时置于 `structuredContent` 和向后兼容的文本内容。工具业务输入错误或权限不符时检查 `result.isError`；未知方法、请求结构错误等检查 JSON-RPC `error`。HTTP 401/403 表示凭据或授权来源需要核对。

## 可运行示例

服务已启动并设置专用凭据后，在项目根目录执行以下 PowerShell。请使用空白测试分身；示例会写入一条明确标注为夹具的记录。

```powershell
$secret = Read-Host "Instance Agent token" -AsSecureString
$env:SILICON_AGENT_TOKEN = [Net.NetworkCredential]::new('', $secret).Password
$env:SILICON_MCP_URL = 'http://127.0.0.1:47831/mcp'
$argsJson = @{idempotency_key=[guid]::NewGuid().ToString();state_text='Protocol acceptance fixture'} | ConvertTo-Json -Compress
$argsJson | python packages/agent-example/call.py report_state
'{}' | python packages/agent-example/call.py get_own_state
Remove-Item Env:SILICON_AGENT_TOKEN
```

在便携包中，可将上述 `python` 换为 `.\runtime\python.exe`。已签发的凭据绑定一个实例；使用专用空白注册凭据时，先调用主体和分身注册。读取结果的 `structuredContent.event_id` 即可对照仪表盘。

## HTTP 客户端

现代请求携带 `jsonrpc: "2.0"`、字符串或整数 `id`、`method`、具名 `params`。每个请求都在 `params._meta` 提供 `io.modelcontextprotocol/protocolVersion: "2026-07-28"` 及对象 `io.modelcontextprotocol/clientCapabilities`，可附带 `io.modelcontextprotocol/clientInfo`。可先调用 `server/discover`，也可以直接调用工具。

每次 POST 发送 Bearer 凭据、`Content-Type: application/json`、`Accept: application/json, text/event-stream`、`MCP-Protocol-Version`、`Mcp-Method`。调用工具另需 `Mcp-Name`。镜像头与正文必须吻合。具体组包、超时、UTF-8 与解码参考 [local_client.py](../packages/mcp-server/local_client.py)。服务只实现本项目需要的工具能力，采用私有本机配对授权；认证 OAuth 发现、长连接 SSE、MCP 资源与提示模板未作为能力发布。

## 已执行验证

官方 Python MCP SDK 1.29.0 通过 stdio 协商至 2025-11-25，发现 15 个工具，用 `report_state` 写入协议夹具，再用 `get_own_state` 读回同一事件 ID。现代 HTTP 由独立的协议契约与应用集成测试覆盖。原生 Codex CLI 0.167.0-alpha.4 在本次托管环境中因应用服务启动时遇只读文件系统而停止。该次原生模型调用标记为 NOT_RUN；可运行的宿主验收入口为 `packages/agent-example/verify_codex.py`。普通测试与日常服务无需模型凭据。[独立客户端与原生宿主记录](evidence/mcp-interop.json)

标准文档与版本依据见 [MCP 规范](https://modelcontextprotocol.io/specification/2026-07-28)、[Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) 和 [官方 TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)。
