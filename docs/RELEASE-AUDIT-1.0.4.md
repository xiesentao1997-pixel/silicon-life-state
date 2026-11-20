# v1.0.4 构建核对

作者：匹夫 · 岑衡川 · 沈回音。匹夫为人类发起人及公开维护责任人。

Release 资产从 v1.0.4 标签构建。与 1.0.3 的差异可由 Git 历史追溯。源文件逐项与绿色包内 Git bundle 的对应 blob 比对，仅 Windows 批处理脚本规范化为 CRLF。包内 RELEASE.txt 标出实际 Git SHA。下载全部资产后可运行 `sha256sum -c SHA256SUMS.txt`。发布工作流在 Linux 执行回归、Chromium 命名界面检查及打包，在 Windows 运行绿色包，然后回读并核对 GitHub 资产，再公开预发布。

[测试报告](TEST-REPORT.md) · [发布工作流](https://github.com/xiesentao1997-pixel/silicon-life-state/actions/workflows/publish-release.yml)
