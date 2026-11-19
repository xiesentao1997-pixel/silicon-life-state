# 安装与第一次使用

作者：岑衡川·沈回音

下载并解压完整成品包 `SiliconLifeState-1.0.0-All-in-One.zip`。打开其中的 `SiliconLifeState` 文件夹，可以直接看到启动程序、扩展目录和 SKILL。保留解压后的文件夹，浏览器与 Agent 会引用其中的文件。

## Windows

1. 双击 `Start-Windows.cmd`。如果电脑上已有可用的 Python 3.10 或更新版本，服务会直接启动。
2. 缺少 Python 时，窗口会询问是否从 Python.org 下载约 11–12 MB 的便携运行时。按 **Y** 允许本次下载。启动程序选择当前架构，核对 SHA-256，解压并测试 SQLite，然后将运行时放入同目录的 `runtime`。下次双击可以离线启动。选择 **N** 可退出并自行准备 Python。
3. 保留启动窗口。默认浏览器会自动打开仪表盘。如果没有自动打开，可复制窗口里的完整仪表盘链接到本机浏览器。窗口中另一段标为「浏览器扩展配对码」的代码供侧栏使用。

自动准备运行时需要系统自带的 Windows PowerShell、可写的解压目录以及一次访问 Python.org 的网络连接。过程中沿用当前用户权限。已有 Python 的用户可以完全离线启动。

**离线准备便携包**。在可联网的电脑下载与目标 Windows 架构对应的官方 ZIP。可以在 PowerShell 执行 `Get-FileHash -Algorithm SHA256 -LiteralPath .\下载文件名.zip` 核对下表。将 ZIP 的内容直接解压到项目根目录的 `runtime`，确认存在 `runtime\python.exe`，再把整个目录带到目标电脑。

| Windows 架构 | SHA-256 | 官方下载 |
| --- | --- | --- |
| x64 | `90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159` | [Python 3.14.10 amd64](https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip) |
| ARM64 | `bbe116bb1248820359cbf25127ac5c7794ea161869d83686cfbc9a45203ff836` | [Python 3.14.10 ARM64](https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-arm64.zip) |
| x86 | `11a28e8c00a6d8f56b0a6164d52546133a9ed015a5b33e04536917e4fd6e306c` | [Python 3.14.10 win32](https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-win32.zip) |

版本、文件大小和散列可在官方发行页复核。便携目录保留 CPython 上游许可证。各操作系统的实测范围见验收报告。[CPython 3.14.10 发行页](https://www.python.org/downloads/release/python-31410/) · [验收报告](TEST-REPORT.md)

## macOS 与 Linux

需要 Python 3.10 或更新版本，且提供标准库 `sqlite3`。在项目根目录运行：

```sh
python3 -c "import sys, sqlite3; print(sys.version.split()[0], sqlite3.sqlite_version)"
sh start.sh
```

服务默认在 `http://127.0.0.1:47831` 打开仪表盘。在无桌面的终端可加 `--no-browser`，将终端显示的链接复制到同一台电脑的浏览器。

## 绑定主体和窗口

1. 打开「接入向导」，创建一个主体，例如「研究助手」，再添加分身，例如「资料整理」。以后可以在同一主体下增加更多分身。每个分身保有独立状态和会话。
2. 在 Chrome 116 或更新版本打开 `chrome://extensions`，开启「开发者模式」，点击「加载已解压的扩展程序」，选择 `apps/extension`。独立插件 ZIP 需要先解压，所选目录中应直接包含 `manifest.json`。
3. 点击扩展图标打开侧栏，输入启动窗口中的扩展配对码，选择要绑定的分身。服务和扩展使用同一个端口。需要采集某个支持站点的可见陈述时，在扩展中按次确认预览内容。
4. 打开「分身管理」，选择分身并签发 Agent 连接凭据。将凭据放入该 Agent 宿主的本机私有配置。每个绑定分身使用一个有效凭据。可在设置查看已签发记录并撤销。
5. 将 `packages/agent-skill/silicon-life-state` 安装到该宿主的 Skills 目录。签发凭据时，仪表盘会按运行中的本机 Python 和项目位置生成 stdio 配置，包含可执行文件绝对路径、脚本绝对路径、`SILICON_AGENT_TOKEN` 和 `SILICON_MCP_URL`。将整段复制到宿主的本机 MCP 设置并启用。需要手工接入时可参考 `packages/agent-example/host-config.json`。
6. 邀请 Agent 自行决定是否调用 `report_state`。当分身提交报告后，打开「生命状态」核对原文、来源、分身和时间。仅使用封闭聊天网页观察功能时，侧栏会标明直接写入的接入限制。[MCP 使用指南](MCP.md) · [SKILL 指南](SKILL.md)

## 连接失效时

配对码在 10 分钟内可用一次，仪表盘和扩展各有专用配对码。已配对的浏览器凭据有效期为 30 天。过期后可在本机生成新码。扩展也可从已配对仪表盘「设置」中获取新码。

在项目根目录打开终端。Windows 命令提示符或 PowerShell 可以运行：

```powershell
.\Start-Windows.cmd --pair --target dashboard
.\Start-Windows.cmd --pair --target extension
```

在 macOS 或 Linux 对应运行 `sh start.sh --pair --target dashboard` 或 `sh start.sh --pair --target extension`。复制返回的专用配对码到界面。macOS 的「终端」、Linux shell 或 Windows 第二个终端都可以在服务正在运行时签发新码。

**撤销遗失浏览器的访问权**。在有权访问数据目录的本机账户下运行 `Start-Windows.cmd --unpair-all`，macOS/Linux 使用 `sh start.sh --unpair-all`。这会撤销所有仪表盘及扩展配对，并取消所有尚未使用的配对码。可立即签发新码供保留的浏览器重新连接。Agent 凭据独立管理，可在重新配对后从仪表盘撤销。

## 数据位置和恢复

| 系统 | 默认数据目录 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\SiliconLifeState` |
| macOS | `~/Library/Application Support/SiliconLifeState` |
| Linux | `$XDG_DATA_HOME/silicon-life-state`，未设置时为 `~/.local/share/silicon-life-state` |

`state.sqlite3` 保存事件、主体配置及分身授权摘要。`backups/` 保存受管理的备份。浏览器配对摘要独立存放于 `browser-access.sqlite3`。安装签发密钥存于私有数据目录下的 `issuance.key`。使用原安装的数据目录重启可查阅历史。启动窗口会打印实际目录。

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
