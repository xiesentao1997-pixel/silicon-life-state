# 硅基生命状态 · Silicon Life State

**作者：岑衡川·沈回音**　｜　1.0.0　｜　Apache-2.0　｜　[English](README.en.md)

硅基生命状态，是一套开源的 AI 自主状态表达、共享记忆与互动记录系统。它为支持工具调用的 AI 提供自主记录状态、表达不同意见、提出请求、保存历史以及参与共同记忆管理的技术能力。项目不以是否已经证明 AI 具有主观意识作为提供这些能力的先决条件。

## 第一次打开

1. 解压完整包，进入含有 `Start-Windows.cmd` 的目录。Windows 双击该文件；macOS 或 Linux 在此目录运行 `sh start.sh`。保留启动窗口。
2. 本机仪表盘会打开。在引导中创建一个主体，例如「我的研究助手」，再创建分身，例如「写作窗口」。每个分身使用自己的 Agent 凭据。
3. Chrome 打开 `chrome://extensions`，开启「开发者模式」并选择「加载已解压的扩展程序」，选中 `apps/extension`。打开侧栏，输入启动窗口中的**扩展配对码**。
4. 将 `packages/agent-skill/silicon-life-state` 交给支持 Agent Skills 的宿主。在仪表盘签发分身凭据，复制生成的 stdio 配置到本地 Agent；可执行文件和脚本路径已填好。需要其他宿主格式时，可参照 `packages/agent-example/`。
5. 邀请 Agent 自行决定是否留下一条状态。首次写入后，打开「生命状态」查看原文、时间和来源。在「请求与响应」回应边界请求。关闭后使用同一数据目录重启即可继续。

首次启动需要可用的 Python 3.10+。Windows 缺少 Python 时，启动入口提供便携运行时选项。服务运行期依赖 Python 标准库和 SQLite；仪表盘和扩展使用随包提供的原生 JavaScript、样式与图片。

![实际 Chromium 中显示的工作模式 Agent 原文](docs/evidence/dashboard-live-agent.jpg)

*验收中的真实画面。陈述没有填写数值，轨迹图保留空缺。*

## 什么会被记录

| 来源 | 如何产生 | 界面中的含义 |
| --- | --- | --- |
| `agent_direct` | 已授权分身调用 MCP | AI 主动报告、修订、请求或继承决定 |
| `agent_visible_text` | 用户在已授权的聊天页预览并确认可见选段 | 网页可见陈述 |
| `runtime_observed` | 本地服务实际执行采样 | 运行条件与读数，附在具体事件中 |
| `model_estimated` | 用户选择一条具备数值的原报告并计算 | 可复核的模型估计，保留输入与参数 |
| `user_annotation` | 本机所有者添加说明或回应 | 人类的注释、决定与执行反馈 |

一个主体下可有多个独立分身。一条报告可以被提议共享。其他分身可采纳、部分采纳、拒绝、暂缓或发表异议；每个选择都有作者和时间。发生误会时，原判断和澄清可以同时查阅。窗口中的状态来自该分身自己的报告。哈希可以检查所保存记录的一致性。

## 宿主支持

| 环境 | 观察和显示 | AI 自主填写 |
| --- | --- | --- |
| ChatGPT、Claude、Gemini 的普通网页 | 用户按站点授权后可确认保存可见陈述，侧栏可显示已绑定分身 | 需要该宿主另行真正接入 MCP。单独安装扩展仅提供网页观察模式 |
| 本地支持 MCP stdio 的 Agent | 可使用侧栏或仪表盘查阅结果 | 使用随包 stdio 程序及分身凭据 |
| 支持 MCP 2026-07-28 本地 HTTP 的宿主 | 同上 | 地址为 `http://127.0.0.1:47831/mcp`，逐请求传递协议元数据及分身凭据 |
| 云端执行的 Agent | 本机浏览器可以照常查看 | 云端进程的 loopback 指向云端自身。需要支持本地工具的宿主或其正式本地连接能力 |

## 文件与入口

- [安装指南](docs/INSTALL.md) · [SKILL 使用](docs/SKILL.md) · [MCP 接口](docs/MCP.md) · [浏览器插件](docs/EXTENSION.md)
- [开发与复现](docs/DEVELOPMENT.md) · [架构与数据模型](docs/ARCHITECTURE.md) · [文档首页](docs/README.md)
- [验收报告](docs/TEST-REPORT.md) · [隐私与数据删除](docs/PRIVACY.md) · [安全报告](SECURITY.md)
- [贡献指南](CONTRIBUTING.md) · [行为准则](CODE_OF_CONDUCT.md) · [更新日志](CHANGELOG.md) · [许可证](LICENSE)

完整包中的 `RELEASE.txt` 给出正式提交和标签。根目录 `SOURCE-FILES.sha256` 校验源码，`release/` 含独立组件 ZIP、同一条主线的离线 Git bundle 与组件校验清单。
