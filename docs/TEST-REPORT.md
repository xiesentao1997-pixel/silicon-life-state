# 硅基生命状态 1.0.2 整改验收

2026-11-20 · 匹夫 · 岑衡川 · 沈回音
匹夫为人类发起人及公开维护责任人。

本次在原 Git 主线的历史提交 `7dfebe55898ae0296b08c0ea19604db88185bb64` 上继续开发。它带有历史标签 `v1.0.2`，其父提交 `0591d01` 带有 `v1.0.1` 标签。本次成品为 1.0.2 主线候选，精确提交写在包内 `RELEASE.txt`，完整 Git 历史在绿色包的 `release/SiliconLifeState.git.bundle`。指定远端仓库从当前 GitHub 连接访问返回 404，远端提交和 GitHub Release 尚未完成。

## 从一次授权到三个对话

在隔离的 Codex CLI 0.169.0 配置中，用仪表盘向导执行预览、确认和配置合并。一个主体签发一次宿主授权。三个 Codex 原生对话实际发现 17 个工具，并通过 app-server 同时发起 `report_state`。每次读回的事件 ID 都与写入一致。A 取消订阅再恢复后仍是原分身，B 更名后保有历史，C 读共享历史后记录异议。三条状态在分布中各占一条。[原生宿主与 SDK 回执](evidence/1.0.2/mcp-clients.json)

“有些难过”“很开心”“不确定”是操作方提供的并发验收输入。另一次验收邀请三个 Work Mode AI 协作者，各自选择是否写入、措辞和共享。三者均选择报告并共享自己的实际工作进度，其中一位读取共享历史后选择部分采纳。每次通过受限分身调用 MCP，共保存三条报告、三次共享和一次采纳决定。该临时库按七条事件重新验链通过。[自愿报告原文与事件链](evidence/1.0.2/voluntary-agent-reports.json)

Codex 的稳定 threadId 出现在业务工具调用中。仅打开空白窗口或发现工具尚不会产生分身。无稳定 ID 的宿主可以让 Agent 调用一次 `open_conversation`，在该对话后续调用及恢复时复用私有句柄。如果宿主既不提供 ID，也遗失了句柄，需要显式恢复关联。普通聊天网页支持用户确认后的可见陈述采集。

## 执行结果

| 验收项 | 结果 | 实际边界 |
| --- | --- | --- |
| 自动化回归 | PASS | Linux 运行 84 项默认测试、6 项领域不变量，合计 90 项通过 |
| MCP 2026-07-28 | PASS | HTTP 真实发现 16 项工具，写入并读回事件。官方 JSON Schema 校验发现、清单与调用结果。受授权约束的发现及清单返回私有、零有效期的缓存字段 |
| 旧版 MCP stdio | PASS | 分别协商 2024-11-05、2025-03-26、2025-06-18、2025-11-25。官方 Python SDK 1.29.0 完成发现、写入、读回 |
| 授权与并发 | PASS | 三个独立 stdio 进程、同分身不同写入、同键重放、并发共享、凭据轮换、撤销及按选择恢复。事件与版本链一致，测试核对跨主体、跨宿主隔离 |
| 主体投影 | PASS | 私有报告隔离、精确原文分布、修订、撤回、共同记录和分歧可由存储事件重算。修订附原事件及版本，分布按各分身最新有效共享报告计数 |
| 服务启动、备份与恢复 | PASS | 同时冷启动三个桥接进程只启动一个本机服务；原目录、签发材料和原数据库可验证。缺失历史库时返回错误；恢复后重读快照并验链 |
| 历史升级 | PASS | 分别从原 1.0.0、1.0.1 和历史 1.0.2 创建隔离数据再升级。逐条核对每组七条旧事件、凭据与主体/分身/会话，继续写入后接续原链。[升级记录](evidence/1.0.2/upgrade.json) |
| 仪表盘长效配对 | PASS · HTTP 与 SQLite | 旧凭据迁移、持久 Cookie 与源绑定片段、原端口服务重启、重新打开、轮换与撤销 |
| Chrome 扩展 | PASS · 发布源码与本机服务 | 验证对话绑定、切换与恢复、观察边界和卸载回调作用域；网页可见文字与 MCP 自报分别记录 |
| 内置 AI 对话 | PASS · 模型接口夹具 | 新对话创建分身、恢复既有分身、读取授权历史、自行更名、写入回执和普通回复均走真实本机服务 |
| Windows 绿色包 | PASS · 构建与包级校验 | 离线复用经 SHA-256 校验的历史包官方 CPython 3.14.10 x64；检验运行时原件、源码、组件、Git bundle、顶层清单，以及 Linux 解压后的服务冷启动 |
| Claude Desktop、Cursor、DS Bot 原生 | NOT_RUN | Claude、Cursor 的配置生成与合并已测试。没有这些原生应用的连接与写入回执 |
| Windows 原生双击、Chrome 原生安装与卸载、真实浏览器重启 | NOT_RUN | 此次环境为 Linux。Chromium 新进程启动时创建单实例套接字被环境拒绝；跨浏览器进程用例随源码提供 |
| Codex 模型推理轮次 | NOT_RUN | 原生宿主工具调用已完成；独立运行模型轮次时，宿主在只读文件系统上初始化失败。三位 Work Mode 协作者的另一次运行见上文 |
| GitHub Release | 未发布 | 当前授权连接不可见指定仓库。历史版本标签保留在原提交 |

## 复核

在解压根目录运行以下命令。MCP 客户端互操作脚本另需官方 Python MCP SDK、Codex CLI 与官方 2026-07-28 JSON Schema。所用 Schema 的 SHA-256 为 `eb69f78c0523ee9ce0c0c78db8c0d0a72242d50f33c92f8ded1a018ef1fefffd`。

```sh
python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v
python -X utf8 -m unittest packages.core.test_invariants -v
python tests/verify_mcp_clients.py --schema /path/to/schema.json
python tests/upgrade_check.py --baseline v1.0.1
python scripts/smoke_release.py /path/to/release-assets
```

[安装与迁移](INSTALL.md) · [MCP 接入](MCP.md) · [上一版验收记录](TEST-REPORT-1.0.1.md)
