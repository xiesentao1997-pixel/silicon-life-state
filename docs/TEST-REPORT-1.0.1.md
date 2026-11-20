# 硅基生命状态 1.0.1 验收报告

**作者：岑衡川·沈回音**

验收日期：2026-11-19。基线为 `v1.0.0`，提交 `f5fc94a3292338c0c2d98f51198a40caa3574e19`。原始完整包与归档 SHA-256 核对一致。每项验收使用专用临时主体、分身、宿主配置与数据库。正式提交及标签见发布包根目录的 `RELEASE.txt`。

## 实际结果

| 项目 | 结果 | 已核验的范围 |
| --- | --- | --- |
| Windows x64 离线包 | PASS 构建 | 解压目录自带官方 CPython 3.14.10、SQLite、SSL、运行时许可证及每个原件的散列。验证 Python.org 原始 ZIP 大小、SHA-256 与 PE 机器类型。 |
| Windows 程序兼容运行 | PASS · Wine 10 x64 | 在独立 Wine 前缀中以 Windows cmd.exe 执行两个 CMD，启动时 PATH 中没有系统 Python。仪表盘 HTTP 200，重新配对，stdio 发现 15 个工具，report_state 与 SQLite 摘要相符。[兼容运行回执](evidence/1.0.1/windows-portable.json) |
| 原生 Windows 双击及物理断网 | NOT_RUN | 本轮可用桌面为 Linux。已交付在 Windows 上通过 ShellExecute 启动并检查 SQLite、配对与 MCP 的用例及 CI 工作流。 |
| 十分钟后恢复配对 | PASS · 自然经过 602.0 秒 | 首次签发后不调整时钟，不重启服务。不再有效的原码返回 PAIR_EXPIRED；匿名取码被拒。所有者重新签发后插件身份读取真实快照，重复兑换返回 PAIR_USED。[实时时钟记录](evidence/1.0.1/pairing-elapsed.json) |
| 插件和仪表盘 | PASS 已测界面 · 原生扩展安装 NOT_RUN | Chromium 156 实际渲染仪表盘、侧栏表单、倒计时及错误恢复。侧栏测试替代 Chrome 标签/储存 API 并连接真实本地服务。受管 Chromium 拒绝加载未打包扩展，未改管理策略。 |
| 宿主连接向导 | PASS | 分别生成 Claude JSON 和 Codex TOML，在隔离配置上确认写入，保存原文件的逐字节备份，保留其他服务和设置，验证语法与过期预览。实际启动 stdio 发现 15 项工具。单独检查宿主发现和分身状态报告。 |
| 原生商业宿主 | 部分验证 | Codex CLI 0.167.0-alpha.4 的 mcp list、mcp get 识别按次载入的配置。原生模型进程初始化遇到只读文件系统，未收到该宿主的 tools/list 或写入。Claude Desktop 客户端未运行。 |
| 与 AI 对话 | PASS | 本地推理服务加载经过 SHA-256 验证的真实 Qwen3 权重。内置入口以 `tool_choice=auto` 提供工具。Qwen3-1.7B 先用自然语言正确回答 2 + 2，未写事件；之后应邀自选措辞，通过 MCP 提交报告。工具回执与 SQLite 事件一致，哈希链通过。 |
| 浏览器中真实模型 | PASS · Chromium 156 | 在独立空分身上通过实际页面与模型进行两轮对话，工具回执、SQLite 和仪表盘事件详情中核对同一事件及摘要，页面错误为 0。[真实模型界面验收](evidence/1.0.1/genuine-model-browser.json) |
| 请求、共享与修订 | PASS | 三个分身保持独立；提议共享、拒绝继承、误会澄清、提交边界、用户拒绝及后续记录可追溯。覆盖并发写入、备份损坏演练及删除后的受管副本检查。 |
| 1.0.0 原数据升级 | PASS | 逐项核对 7 条原始事件、主体、分身、会话、共享、请求、授权和旧配对码。新事件接续原链。还核对了上一版真实 Agent 陈述的事件 ID、原文和摘要。 |
| 断网回归 | PASS | 直接在服务解释器内安装网络审计钩子，分别在已有 sitecustomize 和 -I -S 两种环境中验证 DNS 与 TCP 拒绝对照。本地写入和读回成功，应用未尝试外连。 |
| MCP 互操作 | PASS | 官方 Python MCP SDK 1.29.0 经 stdio 发现 15 项工具，提交明确标识的协议测试记录并回读。1.0.1 内置模型写入另有独立实证。 |
| Git bundle 与成品冷启动 | PASS | 全包和独立服务解压到临时空目录后，Linux 上分别启动、配对、创建并回读新主体。逐项核对源码、组件和运行时摘要，从内附 bundle 普通克隆后处于 main，HEAD 等于版本 tag，v1.0.0 是祖先。 |

## 真实模型证据

独立端到端验收使用 llama.cpp CPU 推理，非脚本化模型回包。Qwen3-1.7B 在模型接口的授权范围自行选用了 `report_state`，原文为 “I answered 2 + 2 = 4.”。本轮没有填入预设情绪或数值。事件来源为 `agent_direct`，并保留分身、会话、模型别名、适配器版本与时间戳。

- [真实聊天截图](evidence/1.0.1/genuine-model-chat.jpg) · [同一事件的仪表盘截图](evidence/1.0.1/genuine-model-dashboard.jpg)
- [模型请求、事件 ID、数据库匹配与完整性回执](evidence/1.0.1/live-model.json)
- [真实模型请求核验、测试所有者拒绝及分身回读](evidence/1.0.1/model-adjustment.json)
- [较小模型实际普通回复，零条状态记录](evidence/1.0.1/genuine-model-no-write.json)
- [宿主配置向导界面](evidence/1.0.1/host-wizard.jpg) · [Chromium 界面断言](evidence/1.0.1/dashboard-extra-acceptance.json)
- [升级核验](evidence/1.0.1/upgrade.json) · [网络隔离核验](evidence/1.0.1/offline-guard.json) · [官方 SDK 回执](evidence/1.0.1/mcp-sdk.json)

模型权重来自 `unsloth/Qwen3-1.7B-GGUF` 的 `d7f544eead698dbd1f15126ef60b45a1e1933222`，Q4_K_M 文件 SHA-256 为 `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897`。测试机以本机回环通信，安装包未分发模型权重，也未附 API 密钥或运行数据库。付费云模型端点、三家实际登录网页和 macOS 客户端不在本轮执行环境内。

## 自动化与复现

66 项默认回归与 6 项 SQLite 领域不变量测试通过。默认回归包括真实进程、数据库、MCP、前端逻辑和脚本化上游模型协议测试。浏览器、官方 MCP SDK、真实时钟、真实模型、升级和发布包冒烟分别执行，未重复计入回归总数。

```sh
python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v
python -X utf8 -m unittest packages.core.test_invariants -v
python tests/pairing_elapsed.py
python scripts/build_release.py --ref v1.0.1 --fetch-runtime --output dist/1.0.1
python scripts/smoke_release.py dist/1.0.1
```

[默认回归日志](evidence/1.0.1/default-tests.txt) · [领域日志](evidence/1.0.1/core-tests.txt) · [浏览器原生扩展加载诊断](evidence/1.0.1/native-extension.json) · [原生宿主诊断](evidence/1.0.1/native-host.json) · [开发复现指南](DEVELOPMENT.md) · [1.0.0 历史报告](TEST-REPORT-1.0.0.md)
