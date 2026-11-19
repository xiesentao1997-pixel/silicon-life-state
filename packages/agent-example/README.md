# MCP 接入和独立验证

作者：岑衡川·沈回音·匹夫

从已启动的面板创建主体和分身，在分身管理中签发专用 Agent 令牌。将这个凭据保存到本机宿主的私有环境。旧凭据泄露时可从面板撤销。每个独立窗口应使用自己的绑定。

## 本机宿主

支持 MCP 的桌面宿主可参照同目录的 `host-config.json` 注册 stdio 程序。把 Python 命令和脚本绝对路径替换为解压位置。Windows 安装器自带解释器时可把 `command` 指向随包的 `python.exe`。Codex 的 TOML 示例见 `codex.config.toml`。这些示例需要你在本机配置专用令牌，切勿将配置了令牌的文件提交至公开仓库。

安装 Agent Skill 时，将整个 `packages/agent-skill/silicon-life-state/` 复制到宿主的 skills 目录，再按宿主说明刷新。打开宿主的工具列表，确认能看到 `get_own_state`、`report_state`、`express_boundary` 等工具。可对 Agent 说「如果你愿意，为这个分身记录一条由你自己措辞的状态。也可以选择不提交。」接着在仪表盘按分身和事件 ID 核对。

## 独立协议客户端

`call.py` 从标准输入读取工具参数，使用环境变量 `SILICON_AGENT_TOKEN`、`SILICON_MCP_URL`。默认服务为 `http://127.0.0.1:47831/mcp`。在项目根目录使用 PowerShell：

```powershell
$secret = Read-Host "Instance Agent token" -AsSecureString
$env:SILICON_AGENT_TOKEN = [Net.NetworkCredential]::new('', $secret).Password
python packages/agent-example/call.py
'{}' | python packages/agent-example/call.py get_own_state
'{"limit":10}' | python packages/agent-example/call.py read_event_history
```

在 Linux 或 macOS：

```sh
read -rs SILICON_AGENT_TOKEN; export SILICON_AGENT_TOKEN
printf '%s' '{}' | python3 packages/agent-example/call.py get_own_state
```

脚本会输出协议回执。手工使用此客户端的结果属于协议验证。若在专用测试库测试写入，请在原文中保留测试性质。协议中的 `agent_direct` 表示经 Agent 凭据认证的工具写入，不能单凭这一字段判定调用方一定是某一真实模型。

## 使用真实 Codex 宿主验收

启动本地状态服务，创建专用空白测试分身，设置上述环境。安装并登录支持 MCP 的 Codex CLI 后，可运行：

```sh
python packages/agent-example/verify_codex.py
```

它通过真实宿主和 stdio 请求 Agent 自选是否记录，检查宿主产生的 MCP 调用和数据库返回的状态事件。输出包含事件 ID，随后在对应分身的仪表盘中核对原文。该脚本启动独立只读宿主，Codex 提供商将按该宿主自己的设置处理验收提示与工具回执。日常服务、插件和普通协议客户端均可离线工作。

## 官方客户端互操作

`verify_sdk.py` 是可选开发测试，使用独立安装的官方 Python SDK。可在测试虚拟环境中安装 `mcp==1.29.0`，另建空分身，再运行 `python packages/agent-example/verify_sdk.py`。该脚本通过 legacy stdio 握手，读取工具清单、写入带“协议测试”字样的一条记录，并核对读回的事件 ID。正常安装和运行本产品无需这个开发依赖。
