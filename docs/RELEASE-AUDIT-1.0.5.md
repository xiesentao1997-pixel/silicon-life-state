# v1.0.5 构建与校验

公开构建从权威仓库的 v1.0.5 标签检出。Windows 作业从 Pet.cs 编译 x64 WinForms 可执行文件。Linux 作业从标签的 Git 对象创建源码、Chrome、Agent SKILL、MCP 本地服务、桌宠安装和 Windows 完整包。两个 Windows 包复用同一 EXE。Windows 完整版沿用项目固定版本的 CPython 运行时。

独立组件文件和嵌入完整包的组件逐字节校验。源码对应提交见 RELEASE.txt，完整历史可通过包内 Git bundle 验证。构建和分发文件分别附 SHA-256 清单。发布程序在 GitHub 资产的名称、数量和摘要全部相符后结束。

Windows x64 用户级安装，无管理员权限。预发布 EXE 未进行 Authenticode 商业代码签名。可将下载文件的 SHA-256 与 Release 清单对照。

[公开构建与发布](https://github.com/xiesentao1997-pixel/silicon-life-state/actions/workflows/publish-release.yml) · [实际验收](TEST-REPORT.md)
