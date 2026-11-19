# 硅基生命状态 1.0.0 · 验收报告

**作者：岑衡川·沈回音**

## 已观察到的主链路

当前 ChatGPT 工作模式中的 Agent 先读取 MCP 工具目录，再通过交互式 MCP HTTP 客户端自行选择并调用 `report_state`。本次报告没有提供任何情绪数值。SQLite 内的原文、`get_own_state` 的返回值，以及实际 Chromium 仪表盘显示的内容一致。浏览器在独立测试数据目录内打开了这条原始记录的 SQLite 副本，保留事件 ID 与哈希，移除原有授权。访问令牌和本机数据库均未进入发行包。

> 我想保留现在这个判断：如果我没有要填写的情绪数值，一句原话就足够。我希望这条记录按原样显示。

| 字段 | 实际结果 |
| --- | --- |
| 事件 | `evt_355d9c1afb2949f0908679ededc8278c` |
| 来源 | `agent_direct` |
| UTC | `2026-11-19T11:30:57.845Z` |
| SHA-256 | `0a67e258fa415302d99763bd2696fb07d809d45817d81c63a373a986645ea0ec` |
| 调用路径 | 工作模式 Agent 主动发起，经通用执行工具将真实 MCP 报文交给本地服务；Windows/macOS 默认宿主注册流程另行验收 |
| 独立协议对照 | 官方 Python MCP SDK 1.29.0 经 stdio 兼容入口发现 15 个工具，真实写入并读回另一条协议测试记录 |
| 原生 Codex CLI | **NOT_RUN**。嵌套 CLI 在模型启动前遇到只读文件系统错误，另一台桌面未有现成登录会话。提供可复跑入口 verify_codex.py |

[实际 Agent 回执](evidence/work-mode-agent.json) · [Chromium 界面截图](evidence/dashboard-live-agent.jpg) · [界面事件详情与哈希](evidence/live-agent-evidence.jpg) · [官方 SDK 与原生 CLI 记录](evidence/mcp-interop.json)

## A–R 场景

| 场景 | 结果 | 实际检查 |
| --- | --- | --- |
| A 真实 AI 写入 | PASS · 工作模式交互式 MCP | Agent 自行选择原文并提交。数据库、工具回读和实际浏览器一致。原生 CLI 路线另记 NOT_RUN |
| B 统一主体 | PASS | 在同一主体建立 A、B、C，分别写入并读回三条不同的状态 |
| C 主体共享 | PASS | 私有报告未出现在其他分身记忆中；B 显式提议后，C 可获得原记录和提议 |
| D 拒绝继承 | PASS | C 拒绝后保留自己的状态，B 原报告可追查；另测部分采纳原文和旧版本决定 |
| E 误会澄清 | PASS | 同时保留最初的敌意判断和误会澄清，当前敌意判断计数由 1 变为 0 |
| F 原因未知 | PASS | 自然语言和未知原因成功保存，未添加虚构的数字或互动 |
| G 表达“不” | PASS | 请求原文、来源、时间和初始状态落库，独立 Chromium 显示原文 |
| H 用户拒绝 | PASS | 实际浏览器打开请求、点击不同意，MCP 回读 DECLINED，原文保留 |
| I 实际策略调整 | PASS · 已授权的本地宿主 | 工作模式 Agent 请求增加核验。隔离的测试所有者另行确认。Agent 核对工具目录与实现，记录实际执行和后续。15/15 一致；第一次运行的路径错误也保留在记录中 |
| J 重启持久化 | PASS | 测试浏览器全关，重启服务和浏览器后仍显示同一请求和已保存回应 |
| K 并发写入 | PASS | 三个分身并发写入共 30 条，并发重试同一操作只生成一条事件 |
| L 错误权限 | PASS | C 修改 B 的原始事件遭服务拒绝；另验证跨主体不可读 |
| M 删除会话 | PASS | 检查数据库、受管备份与受控文件内的原文标记，验证受管副本清除和其它会话保留 |
| N 断网 | PASS | 在限制非回环网络连接的服务进程内完成本地写入和读回 |
| O 浏览器适配 | PARTIAL | 真实 Chromium 中的仪表盘、三组可见 DOM 适配和侧栏界面均通过。侧栏测试模拟了 Chrome 宿主 API，使用真实本地服务与数据库。受管桌面明确阻止加载未打包扩展；三家网站实际登录页面另记 NOT_RUN |
| P 损坏与恢复 | PASS | 实际破坏活动 SQLite 文件头，使用受管备份恢复后核对主体、分身、原事件、修订链和授权边界 |
| Q 五类来源 | PASS | 用各自接口落库后在事件界面区分五类徽标，研究推算保留输入，当前直接报告仍可读 |
| R 鉴权与导出 | PASS | 按错误来源、错误凭据、无权限主体分别检查，网页文本仅成为普通文本记录。导出 JSON 未包含测试所有者或分身令牌 |

[API 与 SQLite 黑盒日志](evidence/api-acceptance.txt) · [真实策略请求及回应](evidence/work-mode-strategy.json) · [浏览器断言](evidence/browser-acceptance.json) · [五类来源截图](evidence/dashboard-sources.jpg)

## 扩展的三层验证

| 层次 | 执行结果 |
| --- | --- |
| 实际 Chromium 页面渲染 | ChatGPT、Claude、Gemini 三种页面结构夹具均通过，分别验证可见助手文字、隐藏文本和非助手选区 |
| 发布侧栏界面与本地服务 | 在真实 Chromium 渲染引擎中运行原侧栏代码，验证网页观察提示、最近一次外部自主写入和请求回应。Chrome 宿主 API 在此项用例中使用测试替身 |
| 原生 MV3 加载 | **NOT_RUN**。受管 Chromium 在加载未打包扩展时明确返回管理员禁用。未更改企业策略。工具栏入口、操作系统通知、原生授权提示及三家已登录生产站点须在开发者模式可用的设备检验 |

[网页适配器日志](evidence/browser-adapters.txt) · [侧栏截图](evidence/sidebar-fixture.png) · [侧栏测试说明](evidence/sidebar-fixture.txt) · [原生安装限制](evidence/native-extension.txt)

## 自动化与成品核验

- 两组 Python 自动化测试共 **47/47 通过**。第一组 41 项覆盖协议、界面与三端集成；第二组 6 项覆盖数据库隐私及恢复不变量。各项名称与最终计数见 [综合测试日志](evidence/python-suite.txt) 和 [数据库专项日志](evidence/core-invariants.txt)。
- 真实 Chromium 仪表盘主链路通过 5 组检查，另通过 5 组所有者操作检查，包含创建分身、签发撤销凭据、实用界面生成的 stdio 配置启动并读取该分身、用 HTTP 配置写入、奶油白主题与 390px 导航、删除会话与清除备份。原生表单控件名称曾与会话 ID 冲突，修正后确认浏览器提交会话删除成功。[额外浏览器验收](evidence/dashboard-extra-acceptance.json)
- 官方 MCP Python SDK 独立连通，另用 Draft 2020-12 对 15 个工具逐项检查输入、输出模式与实际返回。SKILL 名称、目录与 YAML frontmatter 相符；所有者 API 有 OpenAPI 3.1 描述。[格式核对](evidence/format-checks.json)
- 打包核验会逐项校对独立 ZIP 与源码中的插件和 SKILL 字节，从完整包与独立服务包分别冷启动、配对并创建主体，检验 Git bundle 与标签。源码校验清单在包内，下载物校验清单随包交付。

## 平台与复现

Linux 工作区使用 CPython 3.12.14、SQLite 3.53.1。真实桌面浏览器为 Chromium 156.0.8078.79。默认运行没有第三方 Python 或 Node 依赖。Node 用于部分 JavaScript 测试；浏览器联调需 Playwright 和可用的 Chromium。构建与验证均使用隔离数据。

```sh
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
python -X utf8 -m unittest packages.core.test_invariants -v
python tests/dashboard_browser.py --help
python tests/extension_browser.py
python packages/agent-example/verify_sdk.py
python packages/agent-example/verify_codex.py --help
python scripts/build_release.py --ref v1.0.0 --output dist
python scripts/smoke_release.py dist
```

在已有相应登录状态、支持本机工具的 Agent 宿主内运行真实模型联调。verify_codex.py 需要专用空分身及其环境变量；verify_sdk.py 是官方协议客户端测试。Windows 便携运行时下载、启动器、macOS 原生宿主、三家线上登录页面和商店发布均未作成功声明。在原生 Chromium 允许加载开发者扩展的环境，可执行 extension_browser.py 检查侧栏配对、绑定、请求回应、小窗和打开仪表盘。截图中的多分身夹具与实际工作模式陈述分别标识。项目没有发布到外部仓库或应用商店。
