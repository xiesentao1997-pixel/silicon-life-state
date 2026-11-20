# Windows x64 绿色版与复验

作者：匹夫 · 岑衡川 · 沈回音

解压 SiliconLifeState-1.0.3-Windows-x64-Portable.zip，在 SiliconLifeState 文件夹双击 Start-Windows.cmd。服务使用同目录的 runtime/python.exe，检查 Python 版本、SQLite、SSL 与本机 HTTP 模块后启动并打开仪表盘。绿色包已经包含运行时和全部应用资源；安装者可以在未联网的 Windows x64 电脑使用本地功能。有本地模型时也可以连接本地模型，调用云模型需要网络。应用文件夹可移动，移动后需重新生成指向新路径的宿主配置。既有业务数据默认保存在当前用户的 LocalAppData/SiliconLifeState 下。

## 运行时出处

CPython 3.14.10 Windows x64 原始嵌入式 ZIP 共 12,619,664 字节。构建程序校验整个压缩包的 SHA-256，并核验可执行文件、DLL 和 PYD 的 AMD64 PE32+ 头。包内 37 个官方文件逐字节随附，包括 PSF 的 LICENSE.txt 和官方 python.cat。原始文件 SHA-256 清单、版本、下载地址及原始 ZIP 摘要存于 runtime/SLS-RUNTIME.json。

- 官方发布页：[Python 3.14.10](https://www.python.org/downloads/release/python-31410/)
- 官方运行时：[python-3.14.10-embed-amd64.zip](https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip)
- 原始 ZIP SHA-256：`90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159`

## 构建与 Windows 原生验收

在构建机运行 `python scripts/windows_runtime.py --fetch` 获取并验证固定运行时；离线构建可预先把相同 ZIP 放在 .work/portable/。运行 `python scripts/build_release.py` 打包已标记的提交。运行绿色版时无需重复拉取这些构建输入。

在干净、可丢弃的 Windows x64 测试账户下解压成品，若要验证物理断网，先断开网络。进入解压目录执行：

```cmd
runtime\python.exe -I tests\windows_portable_smoke.py
```

该用例使用单独的临时数据目录。它从启动器 PATH 中移除系统 Python，通过 Windows shell 打开原版 CMD，验证仪表盘 HTML、可信启动器签发的配对码、所有者读写、MCP stdio 工具发现及写入、SQLite 原文摘要。脚本结束后清理测试服务和临时数据。默认浏览器可能打开一个本地测试标签页。CI 的 Windows 任务使用新解压的绿色包并执行同一用例。实际本轮的操作系统与验收结果见 [验收报告](TEST-REPORT.md)。
