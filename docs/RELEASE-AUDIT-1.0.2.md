# 1.0.2 构建来源与验收范围

原工程的 Windows 完整包包含 Git bundle。本轮沿用其中 `v1.0.0`、`v1.0.1`、`v1.0.2` 的 Git 对象与 main 提交历史。历史 `v1.0.2` 对应 `7dfebe55898ae0296b08c0ea19604db88185bb64`。

| 核对项 | 依据 |
| --- | --- |
| 本包的源码 | `RELEASE.txt` 的 Git commit 与绿色包内 `release/SiliconLifeState.git.bundle` 的 main HEAD 可交叉核对 |
| 候选构建 | `--candidate` 验证原标签是当前提交的祖先，记录历史标签提交和本次提交 |
| 标签构建 | 默认要求所选提交与同版本标签完全相符 |
| Windows 运行时 | 固定 CPython 3.14.10 AMD64。离线路径先校验整个历史 1.0.1 绿色包的 SHA-256，再核对每个上游运行时文件 |
| 交付校验 | 顶层 `SHA256SUMS.txt` 用于验收所有成品。绿色包内另含源文件、运行时和独立组件清单 |

本次执行的应用测试、三客户端试验、宿主与系统实测结果以 [TEST-REPORT.md](TEST-REPORT.md) 为准。旧版图片、回执与历史测试结果在各自原始版本下保留。GitHub Release 的发布状态以权威仓库实际可见页面为准。
