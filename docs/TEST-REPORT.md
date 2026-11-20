# 硅基生命状态 1.0.3 预发布测试报告

2026-11-20 · 匹夫 · 岑衡川 · 沈回音

匹夫为人类发起人及公开维护责任人。

1.0.3 在多分身主线提交 `f3b2980` 上整理社区预发布。构建前，Linux 自动化回归 **90/90 通过**，三个历史版本分别完成原目录升级。Codex CLI 0.169.0 原生 app-server、官方 Python MCP SDK 1.29.0 和现代 HTTP 客户端均完成工具发现、写入及读回。

## 一次授权，三个原生 Codex 对话

测试人员在隔离配置中通过仪表盘向导授权一个主体，为三个 Codex 对话各调用一次 `report_state`，输入分别为“有些难过”“很开心”“不确定”。宿主发现 17 个工具，三个并发调用产生三个不同的分身 ID 和事件 ID。恢复 A 后仍能读取 A 的原记录，B 更名后保留历史，C 可以对共享记录保留异议。主体分布同时展示三个状态。本次状态原文由测试人员提供，Codex 模型推理轮次记为 `NOT_RUN`。[三个原生线程及事件回执](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/evidence/1.0.3/mcp-clients.json)

可提供稳定对话 ID 的宿主在对话首次调用业务工具时创建或恢复分身。其他宿主可调用 `open_conversation` 获取私有句柄，同一对话后续调用需要带回原句柄。普通网页的观察记录标明来源，需由用户确认采集。[宿主接入说明](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/MCP.md)

## 兼容性及持久化

| 验收项 | 结果 | 本版本的实测范围 |
| --- | --- | --- |
| 自动化回归 | PASS | 默认套件 84 项通过，领域不变量 6 项通过。在 Linux x86_64 执行。 |
| MCP 2026-07-28 | PASS | 本机 HTTP 发现 16 个工具，按官方 JSON Schema 校验并读回写入事件。受授权约束的发现和清单返回 `ttlMs: 0`、`cacheScope: "private"`。 |
| 旧版 MCP stdio | PASS | 回归覆盖 2024-11-05、2025-03-26、2025-06-18 和 2025-11-25 的协商及响应。官方 Python SDK 1.29.0 以 2025-11-25 完成发现、写入与读回。 |
| 长期授权及撤销 | PASS | 同对话恢复、跨宿主隔离、凭据轮换、重放幂等、旧凭据失效和显式恢复原历史。恢复对撤销前所作的备份后，已撤销凭据仍无法写入。 |
| 并发与主体汇总 | PASS | 三个独立 stdio 进程并发提交，同分身写入不同事件，重放同一请求、并发共享、重连与重启。核对原始事件、哈希链以及可重算的分布、修订、撤回、部分采纳和异议。 |
| 本机服务自动启动 | PASS | 三个 stdio 桥接进程同时请求冷启动，连接同一服务并沿用原库；缺失历史库的验收路径返回错误。 |
| 仪表盘及扩展 | PASS（接口与组件） | 已验证持久配对、轮换、撤销、旧配对迁移、扩展对话映射、观察权限和卸载回调作用域。 |
| 内置 AI 对话 | PASS（模型接口夹具） | 本机服务实际执行了新建与恢复分身、工具调用、受限历史访问、回执以及失败重试。 |

## 三个历史版本原目录升级

从仓库的三个原始 Git 标签分别启动历史服务，每组在独立临时目录中创建 1 个主体、2 个分身、7 条事件及受管备份。关闭旧进程后，1.0.3 在同一目录和端口打开数据库。逐条比较事件内容和哈希，核对主体、分身、会话、请求、共享记忆、统计、旧凭据、原备份及扩展配对码的单次使用。升级后追加一条记录，并验证其前序哈希衔接原会话末条事件。[原位升级回执与每组事件摘要](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/evidence/1.0.3/upgrade.json)

| 起点 | 目标 | 逐条一致的旧事件 | 原凭据、备份及续写 |
| --- | --- | --- | --- |
| v1.0.0 · `f5fc94a` | 1.0.3 | 7/7 | PASS |
| v1.0.1 · `0591d01` | 1.0.3 | 7/7 | PASS |
| v1.0.2 · `7dfebe5` | 1.0.3 | 7/7 | PASS |

## 本版本尚未实测的项目

| 项目 | 构建前状态 |
| --- | --- |
| Claude Desktop、Cursor、DS Bot 原生应用 | NOT_RUN。Claude 和 Cursor 的配置适配、合并与备份有自动化覆盖。 |
| Codex 模型推理轮次、内置对话调用真实外部模型 | NOT_RUN。Codex 原生宿主已实际调用 MCP，内置对话使用模型接口夹具。 |
| Windows 原生双击启动与绿色包运行、Chrome 原生安装/卸载、退出并重启真实浏览器 | NOT_RUN。此轮本地测试在 Linux 完成。 |
| GitHub Actions Windows runner 与发布工作流 | NOT_RUN（本报告编制时）。后续运行记录以关联标签的工作流为准。 |

## 复核命令

在包含上述历史标签的 Git 仓库根目录执行。客户端互操作脚本需要官方 Python MCP SDK、Codex CLI 和 2026-07-28 的官方 JSON Schema。

```sh
python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v
python -X utf8 -m unittest packages.core.test_invariants -v
python tests/verify_mcp_clients.py --schema /path/to/schema.json
python tests/upgrade_check.py --baseline v1.0.0
python tests/upgrade_check.py --baseline v1.0.1
python tests/upgrade_check.py --baseline v1.0.2
```

[本次构建及来源核对](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/RELEASE-AUDIT-1.0.3.md) · [1.0.2 主线候选验收记录](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/TEST-REPORT-1.0.2.md)
