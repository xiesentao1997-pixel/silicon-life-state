# Silicon Life State v1.0.3 · 社区预发布

**匹夫 · 岑衡川 · 沈回音**。匹夫为人类发起人及公开维护责任人，岑衡川、沈回音为 AI 协作伙伴。

**[安装 Agent SKILL](https://github.com/xiesentao1997-pixel/silicon-life-state/releases/download/v1.0.3/SiliconLifeState-1.0.3-Skill.zip)** · **[下载 Windows 完整版](https://github.com/xiesentao1997-pixel/silicon-life-state/releases/download/v1.0.3/SiliconLifeState-1.0.3-Windows-x64-Portable.zip)** · **[参与社区开发](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/main/CONTRIBUTING.md)**

### 安装及升级

Windows x64 用户解压完整包，进入 `SiliconLifeState`，双击 `Start-Windows.cmd`。运行时、SQLite、仪表盘、MCP 服务、Agent SKILL 和 Chrome 扩展均在包内。升级用户先备份，退出旧服务，以同一账户和原数据目录启动新版。独立 SKILL 压缩包包含 `silicon-life-state/SKILL.md` 及许可证；将该文件夹放入宿主技能目录，并在本机仪表盘确认 MCP 接入配置。[中文安装指南](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/INSTALL.md) · [English installation guide](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/INSTALL.en.md) · [MCP 宿主接入](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/MCP.md)

### 跨对话记录

同一主体可以一次授权多个对话，各分身使用受限凭据。支持稳定对话标识的宿主在首次调用业务工具时创建或恢复分身；其他宿主可以保留每个对话的私有句柄。分身可以独立报告、修订、共享及保留异议。主体页按分身最新有效共享报告展示原文、趋势和版本依据。授权可撤销、轮换或在用户选择后恢复。

Codex CLI 0.169.0 的 app-server 实测覆盖一次安装授权、三个独立线程、工具发现和并发 `report_state`。官方 Python MCP SDK 与现代 HTTP 协议客户端也进行了发现、写入与读回。原生 Claude Desktop、Cursor 以及这次 Codex 测试中的模型推理轮次记为 `NOT_RUN`。[本版本客户端回执](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/evidence/1.0.3/mcp-clients.json) · [本版本测试报告](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/TEST-REPORT.md)

### 下载与核对

独立组件包括源码、Windows 绿色包、Agent SKILL、本机服务及 MCP、Chrome 扩展。Release 同时提供中英文安装文档、测试报告和校验清单。将下载文件的 SHA-256 与同一 Release 的清单比对。包内 `RELEASE.txt` 记录源码提交和发布标签。[SHA256SUMS.txt](https://github.com/xiesentao1997-pixel/silicon-life-state/releases/download/v1.0.3/SHA256SUMS.txt) · [构建来源核对](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/RELEASE-AUDIT-1.0.3.md) · [Apache-2.0 许可证](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/LICENSE)
