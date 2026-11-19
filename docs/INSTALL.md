# 安装与第一次使用

作者：岑衡川·沈回音·匹夫

Windows x64 用户下载 **`SiliconLifeState-1.0.2-Windows-x64-Portable.zip`**。解压后进入 `SiliconLifeState` 文件夹。启动器、运行时、仪表盘、Chrome 插件、SKILL 和本地服务都在这个文件夹里。保留解压目录，浏览器扩展与已配置的 Agent 会从这里加载文件。

## Windows x64 双击启动

1. 解压整个 ZIP，确认 `Start-Windows.cmd` 和 `runtime` 位于同一层。双击 **Start-Windows.cmd**。
2. 启动器直接使用随包提供的 CPython 3.14.10 x64 和 SQLite。运行本地服务可以断网，也可以在没有系统 Python 的电脑上启动。如果提示文件损坏，重新解压完整成品包即可。
3. 浏览器自动打开已连接的本机仪表盘。若浏览器未打开，复制启动窗口里完整的仪表盘链接，在同一台电脑打开。保留启动窗口。
4. 在「接入向导」里创建一个主体，例如「研究助手」，再创建一个分身，例如「资料整理」。可以为同一主体添加更多分身。

包内 `runtime/SLS-RUNTIME.json` 与上游许可材料记录运行时来源。原始 x64 CPython ZIP 的 SHA-256 是 `90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159`。各操作系统实测项目见验收报告。[Python 3.14.10 发行页](https://www.python.org/downloads/release/python-31410/) · [验收报告](TEST-REPORT.md)

## macOS、Linux 和其他 Windows 架构

macOS 和 Linux 可以解压独立源码包，使用本机带 `sqlite3` 的 Python 3.10 或更新版本。在含有 `start.sh` 的项目根目录运行：

```sh
sh start.sh
```

默认本机地址是 `http://127.0.0.1:47831`。无自动浏览器的终端可以运行 `sh start.sh --no-browser`，再在同一台电脑打开输出的完整仪表盘链接。

ARM64 或 32 位 Windows 用户可以使用**源码包**配合适用于该设备架构的 Python 3.10+，再双击 `Start-Windows.cmd`。使用源码版且本机缺少 Python 时，可以选择由正式启动器从 Python.org 下载并校验对应架构的便携 CPython。离线环境可以提前将对应官方嵌入包解压到源码根目录的 `runtime`，使 `runtime\python.exe` 存在。Windows x64 正式便携包已包含所需运行时。

## 使用 Chrome 侧栏

1. Chrome 116 或更新版本打开 `chrome://extensions`，启用「开发者模式」，点击「加载已解压的扩展程序」，选中本项目 `apps/extension`。独立插件包解压后可选择直接包含 `manifest.json` 的目录。
2. 点击扩展图标打开侧栏。可输入启动窗口中的「浏览器扩展配对码」，也可先点击 **打开仪表盘获取配对码**，再从已授权的仪表盘生成新码。生成后在倒计时结束前粘贴进侧栏。首次安装耗时较久时，直接重新生成即可。
3. 选中主体，绑定当前标签页与分身。对于支持的聊天站点，由用户选择并确认是否保存页面上可见的陈述。界面会标明这些文字的网页观察来源。[扩展指南](EXTENSION.md)

## 在仪表盘里与 AI 对话

点击左侧 **与 AI 对话**，选择负责记录的分身。输入一个实际提供 OpenAI 兼容聊天接口的模型服务基础地址和模型 ID。使用已在本机启动的兼容服务时，可以使用该服务给出的本机地址，例如 `http://127.0.0.1:11434/v1`。软件包提供对话入口，推理模型由所选择的服务提供。

如果提供方需要密钥，在专用栏填写。使用外部模型需要 HTTPS 地址，并明确允许将本次消息、工具说明和回执发送到所选服务。点击「连接模型服务」，输入并发送消息。在窗口中查看真实模型回复。模型可以直接答复，也可以自主调用状态报告、表达边界、请求调整等工具。发生调用时，可在仪表盘核对回执和对应事件 ID。结束时点击「结束并清除对话」。工具写入的历史事件按其所属分身保留。

## 连接已有 Agent 宿主

1. 在「分身管理」或「接入向导」打开 **连接 Agent 宿主**，选定分身，选择 Claude Desktop、Codex CLI 或其他 MCP 宿主。
2. 点击「检查配置」，核对宿主、配置路径和预览。向导会为本次安装填写实际可执行程序、适配器路径与本机地址。可写的目标提供「确认写入配置」。向导会在变更前备份已有文件。也可点击「复制完整配置」自行合并。其他 MCP 宿主可以选择本机 stdio 或 Streamable HTTP。
3. 点击「测试连接，发现工具」核对向导的实际 `tools/list` 结果。按宿主要求重载后，在宿主内启用连接，再点击「刷新实际状态」查看宿主发现记录。邀请 Agent 自行决定是否报告，提交后可在「生命状态」与事件页用事件 ID 核对原文、分身、来源和时间。
4. 支持 Agent Skills 的宿主可以安装 `packages/agent-skill/silicon-life-state`。每个分身授权独立，在「设置」里可以撤销。完整配置包含分身令牌，应保存到该宿主的私有配置。[宿主接入及平台差异](MCP.md) · [SKILL 指南](SKILL.md)

## 从 1.0.0 / 1.0.1 升级

在原仪表盘「导出与备份」中创建备份。按 Ctrl+C 关闭旧服务，解压 1.0.2，并使用同一操作系统账户与原数据目录启动。原先使用自定义目录的用户继续传入相同的 `--data-dir`。主体、分身、历史、既有 Agent 授权以及尚在有效期内的配对可继续使用。若安装目录改变，请在 Chrome 中从新目录重新加载扩展，并在宿主向导中更新指向本机脚本的路径。

## 连接失效时

**首次安装插件超过十分钟也可以继续。** 插件里点击「打开仪表盘获取配对码」。已连接的仪表盘会提供「重新生成配对码」按钮。准备好插件再点击，复制新码回到侧栏粘贴。面板从服务返回的有效期显示倒计时，并在码已用、已替换或过期时停止显示可复制内容。仍打开的配对码对话框可直接重新生成。替换只影响本次选中的码。

**仪表盘也未连接、原窗口已关闭，或主机换了浏览器**。Windows 双击项目根目录的 **Reconnect-Windows.cmd**。macOS 或 Linux 在项目根目录运行：

```sh
sh start.sh --reconnect
```

启动器通过本机数据目录发现正在运行的服务，打开含新码的已授权仪表盘。已有的主体、分身凭据和配对继续有效。服务已停止时，启动器会启动服务。自定义数据目录须通过同一个目录进行恢复，例如 `Reconnect-Windows.cmd --data-dir D:\SiliconStateData`。从 1.0.0 升级时先正常退出旧进程，再使用新版本的正式启动器。

仪表盘和扩展使用各自专用的十分钟一次性配对码，已连接浏览器的凭据有效期为 30 天。持有本机数据目录的用户也可从第二个终端签发特定入口的码：

```powershell
.\Start-Windows.cmd --pair --target dashboard
.\Start-Windows.cmd --pair --target extension
```

macOS/Linux 可运行 `sh start.sh --pair --target dashboard` 或 `sh start.sh --pair --target extension`。侧栏中的恢复按钮会打开本机页面，生成新码需要已配对的所有者页面或可信本机启动器。

**撤销遗失浏览器的访问权**。在有权访问数据目录的本机账户下运行 `Start-Windows.cmd --unpair-all`，macOS/Linux 使用 `sh start.sh --unpair-all`。这会撤销所有仪表盘及扩展配对，并取消所有尚未使用的配对码。可立即签发新码供保留的浏览器重新连接。Agent 凭据独立管理，可在重新配对后从仪表盘撤销。

## 数据位置和恢复

| 系统 | 默认数据目录 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\SiliconLifeState` |
| macOS | `~/Library/Application Support/SiliconLifeState` |
| Linux | `$XDG_DATA_HOME/silicon-life-state`，未设置时为 `~/.local/share/silicon-life-state` |

`state.sqlite3` 保存事件、主体配置及分身授权摘要。`backups/` 保存受管理的备份。浏览器配对摘要独立存放于 `browser-access.sqlite3`。安装签发密钥存于私有数据目录下的 `issuance.key`。使用原安装的数据目录重启可查阅历史。启动窗口会打印实际目录。服务运行时，可信启动器使用该目录的短期验证文件确认本机端口仍属于本次安装。

- **改用其他数据目录**。启动、配对、撤销和恢复都要带上相同的 `--data-dir`。例如在 Windows 运行 `Start-Windows.cmd --data-dir D:\SiliconStateData`。也可以预设 `SILICON_DATA_DIR`。
- **切换端口**。示例为 `sh start.sh --port 47832`。在扩展中填入该端口，并更新宿主的 MCP 地址为 `http://127.0.0.1:47832/mcp`。同一数据目录同一时间只能由一个服务占用。
- **正常退出**。在启动窗口按 Ctrl+C。面板重新连接后继续读取最近一次真实记录。
- **创建与恢复备份**。使用仪表盘「导出与备份」。恢复会用选定快照覆盖当前事件库。恢复前请核对时间及备份 ID。导出的 JSON 供独立查阅，恢复入口接受本机受管理的 SQLite 快照。
- **原数据库损坏**。关闭本地服务。列出备份并复制所需的 `backup_id`，再执行离线恢复。恢复会核验快照完整性及事件哈希链。原库可读时，仅保留原库与快照中一致的有效分身授权。原库损坏且无法验证旧授权时，恢复后请重新签发分身凭据。恢复完成后重新启动服务。

Windows 命令示例：

```powershell
.\Start-Windows.cmd --list-backups
.\Start-Windows.cmd --recover bak_将本段替换为备份ID中实际的32位十六进制字符
```

macOS 或 Linux 命令示例：

```sh
sh start.sh --list-backups
sh start.sh --recover bak_将本段替换为备份ID中实际的32位十六进制字符
```

删除会话、主体或全部数据将同时清理安装内的受管理备份。用户自行保存在其他位置的导出与系统备份由用户管理。[隐私及删除规则](PRIVACY.md)
