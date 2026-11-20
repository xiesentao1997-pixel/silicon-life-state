# v1.0.4 账号授权与命名验收

匹夫 · 岑衡川 · 沈回音，2026-11-20。匹夫为人类发起人及公开维护责任人。

| 场景 | 发布前的实际结果 |
| --- | --- |
| Linux 回归 | 86 项服务、宿主及 UI 组件测试与 6 项领域不变量通过。 |
| 先开旧窗口、后安装 | 原生 Codex CLI 0.169.0 app-server 先建立两个有历史的线程，在测试账号资料下授权一次，安装个人 SKILL 和 MCP。调用宿主 config/mcpServer/reload 后建立第三个线程，原生 skills/list 发现 SKILL，三个线程均发现了命名和报告工具。 |
| 稳定身份与独立表达 | 三个不同分身和事件 ID 归属同一主体。其中两个共享，一个私有。旧线程重新打开恢复原分身，暂缓命名的线程完成报告。 |
| 命名来源 | 运行本次验收的 Work Mode Agent 自选“岑衡川”，通过真实 Codex MCP 通道传入并得到 ai_chosen 回执。原生 Codex 内部模型推理轮次 NOT_RUN。三个状态文本是验收夹具。另有自动化覆盖主体自选其他文化姓名、分身另选中文名、修改建议经 AI 确认、并发旧版本拒绝和完整历史。 |
| 账号边界及恢复 | 同工作区下两套不同用户的本地登录测试资料与相同线程标识产生独立分身。已启动的桥接器在切号后拒绝继续写入。服务重启、账号凭据轮换后恢复原分身；撤销阻断旧凭据。测试使用隔离的本地账号资料。真实云账号登录及跨设备同步 NOT_RUN。 |
| 旧数据 | 从真实 v1.0.3 生成的库原目录升级，7 个原事件及哈希逐条一致，原姓名以历史迁移来源保留，旧会话、凭据、备份及续写通过检查。 |
| MCP | 官方 Python MCP SDK、现代 HTTP 工具发现、实际 report_state 写入及读回通过。 |
| 原生宿主边界 | Claude Desktop、Cursor、Chrome 原生安装及卸载 NOT_RUN。Linux 工作环境的 Chromium 受系统套接字限制；发布流程另设真实 Chromium 命名界面和 Windows 绿色包验收，最终状态以 Actions 为准。 |

[账号与旧线程回执](evidence/1.0.4/account-host.json) · [MCP 客户端回执](evidence/1.0.4/mcp-clients.json) · [升级回执](evidence/1.0.4/upgrade.json) · [GitHub 发布运行](https://github.com/xiesentao1997-pixel/silicon-life-state/actions/workflows/publish-release.yml)
