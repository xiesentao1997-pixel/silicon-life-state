# 开发、测试与构建

作者：匹夫 · 岑衡川 · 沈回音

克隆权威源码仓库可运行 `git clone https://github.com/xiesentao1997-pixel/silicon-life-state.git`。使用一条 main 主线。Release 由版本标签标识。源码 ZIP 可直接修改运行；需要保留提交对象与标签时，用完整包内的 Git bundle 建立本地仓库。

```sh
git clone /absolute/path/to/SiliconLifeState.git.bundle silicon-life-state
cd silicon-life-state
git status -sb
git tag --list
```

## 本地开发

```sh
sh start.sh --data-dir ./dev-data --no-browser
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

## 真实本地模型验收

先在回环地址启动已装载模型、启用函数调用的兼容推理服务，再运行独立验收。以下命令会创建临时主体和数据库，通过实际对话工具执行两轮交互，校对模型回执、SQLite 和哈希链。模型可以不提交记录，该次验收会报告未观察到写入。把 `--model` 替换为该服务实际公布的模型名。

```sh
python tests/live_model_chat.py --endpoint http://127.0.0.1:8080/v1 --model qwen3-1.7b-local --output live-model.json
```

## 制作发行包

```sh
python scripts/build_release.py --pet-exe /path/to/SiliconLifePet.exe --ref v1.0.5 --fetch-runtime --output dist/1.0.5
```

桌宠可执行文件来自同一标签的 Windows 构建。在该标签源码的 Windows x64 检出目录运行 `apps\desktop-pet\Install-Windows.cmd --no-start`，将当前用户目录 `%LOCALAPPDATA%\SiliconLifeState\DesktopPet\SiliconLifePet.exe` 传入构建命令。公开构建自动传递该文件。

默认模式读取标签对应的 Git 对象，并校验所附 CPython 官方 ZIP 的大小和 SHA-256。离线构建可以用 `--windows-runtime /path/to/python-3.14.10-embed-amd64.zip` 指定预先下载的原件。对无法访问 Python.org 的独立构建环境，可以使用 `--runtime-from-baseline /path/to/SiliconLifeState-1.0.1-Windows-x64-Portable.zip` 复用 1.0.1 内已经逐文件验证的官方运行时（强制校验历史整包 SHA-256 与上游原始文件摘要）。完整包、源码、浏览器扩展、SKILL、本地服务、README、验收报告及总 SHA-256 清单位于 dist/1.0.5/。源码文件和 ZIP 的时间戳采用固定值。用户可用 `sha256sum -c SHA256SUMS.txt`，或在 Windows PowerShell 中使用 `Get-FileHash -Algorithm SHA256 文件名` 核对下载。分发时保留 LICENSE 和 NOTICE。

GitHub Actions 工作流提供 Windows、Linux、macOS 的测试。实际在哪些系统执行过，以当前验收报告为准。

复核交付 ZIP 时运行 `python scripts/smoke_release.py dist/1.0.5`。程序从完整包和独立服务包分别解压启动，创建临时主体，读取仪表盘和本地插画，并核对独立组件和 Git bundle 的提交。

有仓库发布权限的维护者可将主线与标签推送至权威仓库，由标签触发发布，或手工运行 Actions 的 **Publish verified release**，选择已有标签。工作流校验发布资产、在 Windows runner 上运行解压后的绿色包，再把同一批资产附到该仓库的 GitHub Release。
