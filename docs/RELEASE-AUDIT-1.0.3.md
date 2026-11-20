# v1.0.3 构建与来源核对

**匹夫 · 岑衡川 · 沈回音**。匹夫为人类发起人及公开维护责任人。

此版本沿用 `xiesentao1997-pixel/silicon-life-state` 主线，通过独立的 `v1.0.3` 标签标识构建输入。一次授权与多分身功能可沿提交 `f3b2980` 追溯到历史 `v1.0.2`。原有标签可在附带的 Git bundle 中分别核对。[权威仓库](https://github.com/xiesentao1997-pixel/silicon-life-state) · [v1.0.3 源码树](https://github.com/xiesentao1997-pixel/silicon-life-state/tree/v1.0.3)

| 核对项 | 操作与依据 |
| --- | --- |
| 源码提交 | 解压源码或绿色包，读取 `RELEASE.txt` 的 Git commit、`Build: tagged` 与 `Release tag: v1.0.3`。用 `git rev-parse 'v1.0.3^{commit}'` 核对提交。 |
| 离线历史 | 绿色包的 `release/SiliconLifeState.git.bundle` 包含 main、发布提交的祖先与历史标签，可克隆后再次核对。 |
| 源文件 | `SOURCE-FILES.sha256` 对应源码包根目录中的文件。独立组件和 Windows 运行时另有清单。 |
| Windows 运行时 | 构建脚本校验固定 CPython 3.14.10 AMD64 上游归档的大小和 SHA-256。离线构建也可从已核验的历史绿色包提取运行时并逐文件比对。 |
| 分发资产 | Release 的 `SHA256SUMS.txt` 列出每个 ZIP、两个 README、中英文安装说明、发布说明、测试报告和本文件的 SHA-256。 |
| 宿主回执 | 通过 [v1.0.3 测试报告](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/TEST-REPORT.md) 和[实际 MCP 事件 ID](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/v1.0.3/docs/evidence/1.0.3/mcp-clients.json)核对执行环境、发现工具、写入结果与 `NOT_RUN` 项。 |

### 核验下载

在保存同一 Release 全部资产的目录内执行：

```sh
sha256sum -c SHA256SUMS.txt
```

仅下载某个组件时，可以在 PowerShell 核对该 ZIP 对应的一行：

```powershell
Get-FileHash -Algorithm SHA256 ./SiliconLifeState-1.0.3-Windows-x64-Portable.zip
Select-String -SimpleMatch "SiliconLifeState-1.0.3-Windows-x64-Portable.zip" ./SHA256SUMS.txt
```

发布工作流从指定标签打包，核对主线祖先关系，在 Windows runner 解压同一批次的绿色包并执行烟雾测试。Windows 作业保存 `windows-acceptance` 运行记录。公开预发布资产及其关联标签可在 [GitHub Release](https://github.com/xiesentao1997-pixel/silicon-life-state/releases/tag/v1.0.3) 核对，工作流的实际执行结果可在 [Actions](https://github.com/xiesentao1997-pixel/silicon-life-state/actions/workflows/publish-release.yml) 查阅。
