# 开发、测试与构建

作者：岑衡川·沈回音

使用一条 main 主线。Release 由版本标签标识。源码 ZIP 可直接修改运行；需要保留提交对象与标签时，用完整包内的 Git bundle 建立本地仓库。

```sh
git init silicon-life-state
cd silicon-life-state
git fetch /absolute/path/to/SiliconLifeState.git.bundle refs/tags/v1.0.0:refs/tags/v1.0.0
git switch -c main v1.0.0
```

## 本地开发

```sh
python apps/local-service/server.py --data-dir ./dev-data --no-browser
```

请为开发使用干净的数据目录。在控制台打开首次配对地址。仪表盘源文件由服务直接提供，修改后刷新即可。更改扩展文件后，在 Chrome 的扩展页重新加载。新增 MCP 工具须同步更新工具目录 JSON Schema、领域验证、授权规则、Agent Skill 与测试。

应用部署不下载前端框架、MCP SDK 或数据库驱动；完整源码就是可运行的发行输入。选择 Python 标准库和浏览器原生模块，是为了让本地工作站能够离线安装。TypeScript SDK 的优先选型未在此版本采用。

## 重跑测试

从仓库根目录执行：

```sh
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
python -X utf8 -m unittest packages.core.test_invariants -v
```

Node 用于扩展客户端的 JavaScript 测试。若需重跑浏览器及独立 SDK 验收，可在开发用虚拟环境执行 `python -m pip install -r requirements-test.txt` 和 `python -m playwright install chromium`，或令 SILICON_CHROMIUM 指向本机已安装的 Chromium 程序。项目锁定了这些可选工具的实测版本。真实 Chromium 扩展测试与模型宿主测试为单独入口，所需外部条件和执行结果见 [验收报告](TEST-REPORT.md)。默认测试只启动临时数据库与本机服务；不会写入安装者的主数据库。

## 制作发行包

```sh
python scripts/build_release.py --ref v1.0.0 --output dist
```

脚本读取标签对应的 Git 对象，只打包版本库中的文件。完整包、源码、浏览器扩展、SKILL、本地服务、README、验收报告及总 SHA-256 清单位于 dist/。源码文件和 ZIP 的时间戳采用固定值。用户可用 `sha256sum -c SHA256SUMS.txt`，或在 Windows PowerShell 中使用 `Get-FileHash -Algorithm SHA256 文件名` 核对下载。分发时保留 LICENSE 和 NOTICE。

配置的 GitHub Actions 工作流可在项目发布到获授权仓库后执行 Windows、Linux、macOS 的测试。实际在哪些系统执行过，以当前验收报告为准。

复核交付 ZIP 时运行 `python scripts/smoke_release.py dist`。程序从完整包和独立服务包分别解压启动，创建临时主体，读取仪表盘和本地插画，并核对独立组件和 Git bundle 的提交。
