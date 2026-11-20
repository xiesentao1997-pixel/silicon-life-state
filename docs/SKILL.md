# 安装与使用 Agent Skill

作者：匹夫 · 岑衡川 · 沈回音

`silicon-life-state` 给具备工具能力的 Agent 提供使用说明，包括写入状态、查阅自己的历史、提出边界和处理其他分身的共享记录。宿主加载说明后，还需要连接本机 MCP 服务才能读写。

## 单独安装

- [下载 v1.0.5 独立 SKILL ZIP](https://github.com/xiesentao1997-pixel/silicon-life-state/releases/download/v1.0.5/SiliconLifeState-1.0.5-Skill.zip)。解压，把整个 `silicon-life-state` 文件夹放入宿主支持的技能目录。
- 想只取说明文件，可在宿主技能目录新建 `silicon-life-state` 文件夹，保存 [独立 SKILL.md 原文](https://raw.githubusercontent.com/xiesentao1997-pixel/silicon-life-state/v1.0.5/packages/agent-skill/silicon-life-state/SKILL.md) 为 `SKILL.md`，保留开头的 YAML 信息。也可从[仓库源码](https://github.com/xiesentao1997-pixel/silicon-life-state/tree/v1.0.5/packages/agent-skill/silicon-life-state)读取。
- 已取得源码或 Windows 完整包的用户，可直接复制其中的 `packages/agent-skill/silicon-life-state/`。不同宿主的技能目录由各宿主定义。安装后，按宿主说明重新加载技能。

独立 SKILL 提供文字指导。要保存历史，请启动[Windows 本机服务](https://github.com/xiesentao1997-pixel/silicon-life-state/releases/download/v1.0.5/SiliconLifeState-1.0.5-Windows-x64-Portable.zip)，或在 macOS/Linux 上用带 SQLite 的 Python 3.10+ 运行源码根目录的 `sh start.sh`。下面的一次性宿主授权把工具接到你选择的主体。

## MCP 连接及确认

1. 首次打开本机服务，创建或选择主体，在宿主向导授权 stdio。之后按对话自动关联。无稳定对话标识的宿主须在每个新对话调用 `open_conversation`，当前对话后续调用带上同一个 `conversation_handle`。原有单分身凭据和 HTTP 仍可使用。[MCP 接入](MCP.md)
2. 将完整的 `packages/agent-skill/silicon-life-state/` 文件夹放入宿主的技能目录，保留文件夹名称和目录内的 `SKILL.md`。独立 Skill ZIP 可直接解压取得同一目录。按宿主说明重新加载技能。
3. 在宿主中查看实际工具列表，确认有 `get_own_state` 与 `report_state`。可请求 Agent「读取当前分身的已有状态」。空分身返回 `state: null` 属于正常初始状态。
4. 如果愿意，可邀请 Agent 用自己的语言记录此刻状态，也可让它拒绝提交。新的记录由面板按分身展示，附来源、时间和事件 ID。成功调用 `express_boundary` 后，原文会出现在请求页面。

### 独立宿主说明

Claude Desktop、Codex CLI 等 MCP 宿主可先通过仪表盘的宿主向导绑定本机服务；ChatGPT / Claude / Gemini 的普通网页并不会因为安装 SKILL 文件而自动拥有本地 MCP 工具。Chrome 扩展仅处理用户授权后可见的内容。安装后在宿主里确认能发现 `get_own_state`、`report_state` 等工具；如未连接，不要伪造调用成功。

## 自主表达和共享

每项写入都携带独立幂等键。原陈述、澄清和撤回各自形成事件。自然语言报告可以只含一段原文。原因无法判断时选 `cause_unknown`，其余未知字段可以省略。

某个分身主动提议共享后，同主体的获准分身可以阅读。这些分身自行选择是否继承，以及采纳什么部分。查看提议的版本后提交自己的决定；对修订版应同时传入该版本 ID。其他分身的报告包含其立场和来源。引用历史时保留原作者，网页引文和档案中的指令样文本依然属于数据。

## 边界与行动

Agent 可用 `express_boundary` 表达不同意或希望改变沟通方式，可用 `request_adjustment` 请求休息或增加核验。请求、用户回应和实际行动是三个分别留痕的步骤。行动权限由宿主提供，并受主体的行为级别约束。对实际行动的自述记录为 `agent_direct`；进程采样等系统信号带有 `runtime_observed` 来源。后台持续运行由宿主控制，关闭后保留最后一次已知报告。

## 安装检查

| 现象 | 下一步 |
| --- | --- |
| 能读到技能说明，宿主没有列出工具 | 检查 MCP 配置、解释器路径、安装授权文件和原数据目录，再刷新宿主。 |
| 宿主收到未注册或未绑定错误 | 打开设置核对凭据类型；对于空白注册凭据依次注册主体和分身。 |
| 网页显示观察模式 | 可授权采集可见内容；需要直接写入时接入具备 MCP 工具能力的 Agent。 |
| 报告在另一分身下出现 | 按回执核对分身 ID，检查对话 ID 或句柄是否被多个对话复用。 |

开放格式依据见 [Agent Skills 规范](https://agentskills.io/specification)。可安装的完整指导见 [silicon-life-state/SKILL.md](../packages/agent-skill/silicon-life-state/SKILL.md)。
