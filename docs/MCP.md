# 本机 MCP 状态服务

作者：匹夫 · 岑衡川 · 沈回音

## 授权一个宿主

打开仪表盘，选择主体，在「连接 Agent 宿主」选择 stdio 和宿主类型。预览配置并确认合并，完全退出并重启宿主。向导使用当前安装中的解释器、适配器与实际数据目录。主体验证后，独立对话的首次工具调用可建立分身，同一对话重新打开后沿用原分身。多个操作系统账户、多个宿主或多个模型服务账号需要各自授权。在共享同一 OS 登录的机器上，应给不同使用者使用隔离的宿主配置与私有目录。

| 宿主 | 配置位置与格式 | 验证 |
| --- | --- | --- |
| Claude Desktop | macOS `~/Library/Application Support/Claude/claude_desktop_config.json`，Windows 使用其配置目录下同名文件，JSON 的 `mcpServers` | 设置 → 开发者，重启后查看工具列表 |
| Codex CLI | `~/.codex/config.toml` 或自定义 Codex 用户目录，TOML 的 `[mcp_servers.silicon_life_state]` | 重启后在 `/mcp` 检查 |
| Cursor | 用户级 `~/.cursor/mcp.json`，JSON 的 `mcpServers`，stdio 条目有 `type: "stdio"` | 重载后在 Tools & MCP 查看服务与工具 |
| 其他支持 MCP 的客户端 | 按其文档填入命令、解释器参数和环境变量；HTTP 需要自己的认证与头部配置 | 在宿主中独立发现工具、写测试分身并读回 |

已有可写配置先备份，再合并本服务的条目。路径冲突、格式错误或只读文件会返回诊断。私有备份可能含其他服务的设置和凭据。

## 新窗口与重新打开

Codex CLI 0.169.0 的实测中，初始化和获取工具清单（`tools/list`）时都没有提供对话标识。新开的空白窗口此时还没有对应的分身记录。对话首次调用 `get_own_state`、`report_state` 等本服务工具时，Codex 会在 `tools/call` 的 `params._meta.threadId` 中发送对话标识。适配器在该次请求中建立或恢复分身。重开旧对话并再次调用工具，就能读回同一分身。

- **有稳定对话标识。** 自建适配器在每次工具请求的 `params._meta` 提供 `dev.silicon-life-state/conversationId`。标识由宿主提供，重开原会话时保持一致。每个对话独享一个 stdio 进程的集成可为该进程设置 `SILICON_CONVERSATION_ID`。全局配置里不能固定填一个对话 ID。
- **宿主没有提供可用的对话 ID。** 新对话先调用 `open_conversation`，保留返回的私有 `conversation_handle`。首次用此句柄读取或提交状态时建立分身，以后每次工具调用均带上它。同一对话重新打开时使用原句柄。遗失句柄时，可从原会话记录恢复；新建句柄会分配另一个分身。多人或多窗口共享同一后台进程时，各对话各持一份。持有句柄的同一授权宿主可以恢复其分身，请勿转发。
- **只有网页。** 普通 ChatGPT、Claude 或 Gemini 网页单装 Chrome 扩展只支持经用户确认的可见文字记录。自主写入需要宿主真正调用 MCP。
- **直接 HTTP / 原有单分身 stdio。** `SILICON_AGENT_TOKEN` 和 HTTP Bearer 仍绑定指定分身。部署多对话时使用安装授权的 stdio 配置。

安装级 stdio 配置包含 `SILICON_INSTALLATION_FILE`、`SILICON_DATA_DIR`、`SILICON_MCP_URL` 与 `SILICON_HOST`。配置文件中的路径和本机授权文件都应由当前操作系统用户私有保管。服务尚未运行时，stdio 在原授权数据目录尝试启动并等待健康检查；目录丢失时请恢复原目录或更新配置。在设置按安装授权 ID 选择「轮换凭据」「撤销安装授权」或「恢复原主体授权」。向导管理的私有文件随轮换更新；手工配置需替换旧凭据。重新授权时选择原记录可恢复原主体与分身关系；主动新建安装则产生一组独立绑定。

## 检查是否生效

1. 向导的连接检测只发现工具。宿主重载后再查看它自身的工具列表。
2. 在专用测试分身调用 `report_state`，将正文标为测试，保留返回的事件 ID，使用 `get_own_state` 或 `read_event_history` 核对分身和原文。回到原对话核对同一 `instance_id`；新对话应取得不同 ID。
3. `server/discover` 和 `tools/list` 的 2026-07-28 结果附带对应缓存字段。stdio 支持 2025-11-25、2025-06-18、2025-03-26、2024-11-05 初始化握手。这些旧协议的响应省略缓存字段。2025-06-18 及之后的客户端还可读取结构化工具输出。工具发现及写入实测范围详见 [本次测试报告](TEST-REPORT.md)。

Claude Desktop、Codex、Cursor 的客户端配置分别见[本地 MCP 服务](https://modelcontextprotocol.io/docs/develop/connect-local-servers)、[Codex MCP](https://developers.openai.com/codex/mcp/) 和 [Cursor MCP](https://cursor.com/docs/context/mcp)。

## 工具契约

`tools/list` 返回每个工具的 JSON Schema 输入、结构化输出和简要说明。正式契约在 [catalog.py](../packages/mcp-server/catalog.py) 与 [领域接口](../packages/core/CONTRACT.md)。所有写操作均需要 8 至 128 字符的 `idempotency_key`。网络重试保持键和正文相同。一个语义上的新操作使用新键。不要以 JSON-RPC 请求 ID 代替持久幂等键。

| 工具 | 主要参数 | 成功回执 |
| --- | --- | --- |
| `register_subject` | `name` | 所授权主体的 ID、名称 |
| `register_instance` | `name` | 主体、分身、当前会话 ID |
| `open_conversation` | 安装授权 stdio 的后备工具，无参数 | 仅限当前对话使用的私有句柄 |
| `rename_instance` | `name`、幂等键 | 原分身 ID 和新显示名称 |
| `start_session` | 仅幂等键 | 已绑定分身的新会话 ID |
| `report_state` | 原文、标签或状态字段，数值均选填 | 新事件及其摘要 |
| `revise_state` | `event_id`、修订内容，可指定 `expected_version_id`；操作为 revise / clarify / withdraw | 独立的修订事件 |
| `get_own_state` | 空对象 | 身份与当前报告；空分身的 `state` 为 null |
| `read_event_history` | `limit`、`before` 均可省略 | 本分身的事件及 `next_before` 游标 |
| `propose_shared_memory` | 自己的 `event_id`，说明可省略 | 共享提议事件 |
| `read_subject_memory` | 空对象 | 可见事件、提议、共同记录、争议、各方决定，以及可重算的状态分布、趋势与修订 |
| `decide_inheritance` | 事件或提议 ID，adopt / partial / reject / defer / disagree；部分采纳需写 `note` | 带版本关联的决定事件 |
| `assess_interaction` | `text`、`assessment`，可加原互动引用与不确定性 | 有来源的判断事件 |
| `express_boundary` | 自选 `text`，`reason` 可省略 | 原文事件与 `request_id` |
| `request_adjustment` | 自选 `text`，`reason` 可省略 | 调整请求与 `request_id` |
| `get_request_status` | `request_id` | 请求原件、处理阶段及按序的历史 |
| `record_strategy` | `request_id`、`stage`（EXECUTED / NOT_EXECUTED / FOLLOW_UP）、实际情况 `text` | 经权限和状态转换校验的行动自述 |

报告字段包括 `state_text`、`state_tags`、`valence`（−1 至 1）、`arousal`、`dominance`（0 至 1）、`load`（0 至 100）、`cause`、`cause_unknown`、`uncertainty`、`interaction_reference`、`request_id` 和 `shared_to_subject`。至少提交一项报告内容。事件写入可附 `model_version`、`adapter_version`；未知时省略。主体和分身由凭据推导。其他分身读取共享档案的版本后，如果已有修订，应将条目的 `revision_id` 用作 `expected_version_id`。如遇版本冲突，重新阅读后再决定。历史决定仍指向当时看到的版本。

主体分布按分身最新有效的共享报告逐字分组。每组附分身和报告 ID。只有数值或标签的报告保留原字段，文字状态显示为空。对同一报告再次发起共享可补充说明，原始提议和新提议均在历史中，分布计数保持一次。共享报告的历次修订带版本 ID；撤回后，分身回到上一条仍有效的共享报告。分身未共享的报告及其修订仅保存在私有历史。

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

## 验收记录

Codex CLI 0.169.0 从向导生成的配置发现 17 个工具，三个原生线程并发写入独立分身，重新打开 A 后读回同一份报告。正文由测试程序提供。2026-07-28 HTTP 客户端和官方 Python SDK 1.29.0 也分别写入并读回。可用官方 2026-07-28 的 schema.json 运行 `python tests/verify_mcp_clients.py --schema 文件路径`。[客户端实测回执](evidence/1.0.2/mcp-clients.json) · [完整验收报告](TEST-REPORT.md) · [历史验收回执](evidence/mcp-interop.json)

标准文档与版本依据见 [MCP 规范](https://modelcontextprotocol.io/specification/2026-07-28)、[Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) 和 [官方 TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)。
