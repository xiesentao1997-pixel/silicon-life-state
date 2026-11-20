# Silicon Life State v1.0.5 验收报告

匹夫 · 岑衡川 · 沈回音

| 场景 | 实际结果 |
| --- | --- |
| Windows 桌宠与 Chrome 读取同一条 MCP 报告 | PASS。GitHub 托管 Windows 原生运行器安装并启动 WinForms 桌宠，自动轮询。向真实 MCP 服务写入后，Win32 窗口和同机加载的 MV3 扩展均显示报告原文、直接报告来源与同一事件 `evt_f123d2c2b46a435e87f2a8e2867dc0f9`。 |
| 请求及窗口操作 | PASS。窗口显示 `request_adjustment` 原文和事件 ID。原生窗口收到鼠标拖动消息后实际坐标改变。隐藏后进程继续运行，退出后服务、事件及哈希链仍可读。此次为自动化 GUI 验收。 |
| 浏览器生命周期 | PASS。真实 Chromium 进行了侧栏配对、绑定、读取、回应请求、打开小窗口及仪表盘操作。关闭浏览器后再次从服务读回原事件。普通页面持续显示网页观察模式。 |
| 实际 Agent 与协议 | PASS。Work Mode Agent 通过原生 Codex app-server 调用 `report_state`，桌宠和插件各自的授权读口得到同一条记录。官方 Python SDK 1.29.0 和 2026-07-28 HTTP 协议均完成工具发现与写入。 |
| 账号与三个分身 | PASS。Codex CLI 0.169.0 使用隔离测试登录资料。两个已有线程和一个新线程发现 SKILL/MCP，三个分身各自写入，重开旧线程恢复原身份。 |
| 升级到 v1.0.5 | PASS。从真实 v1.0.4 标签启动，创建安装授权与对话绑定，再用新服务打开原目录。7 条事件逐字段相等，名称、会话、共享与请求记录一致，原始安装与分身凭据继续有效，新写入延续旧链。 |
| 自动化回归 | PASS。Linux 88 项服务、展示和授权测试，以及 6 项领域不变量。涵盖三种状态同时保存、共享选择、修订与撤回、网页来源及桌宠只读权限。 |
| 发布复验 | 发布流程在 Windows 编译标签源码，将 EXE 同时编入独立桌宠安装包和完整版，核对组件与 Git 源码，解压完整版后重跑 Windows 桌宠和浏览器联动。最终作业结果见发布工作流。 |

[Windows 与 Chromium 同机验收日志](https://github.com/xiesentao1997-pixel/silicon-life-state/actions/runs/44744576930) · [实时 Agent 回执](evidence/1.0.5/live-agent.json) · [账号验收回执](evidence/1.0.5/account-host.json) · [MCP 协议回执](evidence/1.0.5/mcp-clients.json) · [升级回执](evidence/1.0.5/upgrade.json) · [发布工作流](https://github.com/xiesentao1997-pixel/silicon-life-state/actions/workflows/publish-release.yml)

**NOT_RUN**：个人 Windows 10/11 物理桌面、多显示器和高 DPI 人工体验，实际登录系统验证开机自启、Windows 通知中心人工点选、品牌 Chrome 上的站点权限弹窗和真实聊天网站、Claude Desktop 与 Cursor 原生验收。Codex 验收使用真实宿主工具通道，测试未在宿主内部购买或调用模型推理服务。

[上一版本的实测范围](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/74205039962e783f329d81de7e75216f53322c13/docs/TEST-REPORT.md)
