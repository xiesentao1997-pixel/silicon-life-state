# 依赖与素材

- 项目自有代码按根目录 Apache License 2.0 分发。NOTICE 保留项目展示署名。许可证的通用附录保持原文。
- 日常运行使用 CPython 标准库、其中的 sqlite3 接口和浏览器内建 Web API。安装包源码中没有 npm 或 pip 运行时依赖。CPython 和 SQLite 的分发条款随相应运行时提供。Windows x64 绿色包附 CPython 3.14.10 官方 embeddable 运行时。原许可在 runtime/LICENSE.txt，归档来源、整包散列、每个原件的 SHA-256 在 runtime/SLS-RUNTIME.json。
- Python 3.11+ 通过标准库 tomllib 校验宿主 TOML。Python 3.10 随包附 Tomli 2.4.1 的纯 Python 回退解析器，保留 MIT 许可证和源文件版权声明，见 [Tomli LICENSE](../apps/local-service/_vendor/tomli/LICENSE)。无需 pip 安装。
- 前端系统字体由设备提供。界面图标和布局由项目生成。apps/dashboard/assets/life.webp 为本项目定制的 AI 生成玻璃晶体生命形象，用于界面插画。浏览器截图由实际应用生成并注明验收环境。
- 可选开发测试使用 Playwright、Chromium 与官方 MCP Python SDK；运行环境中的这些外部工具未重新打包。其版本及使用范围见验收报告。Chrome、ChatGPT、Claude、Gemini 与 Codex 等名称用于识别相应的兼容接口与宿主。
- 模型联调使用的 Qwen 权重与 llama.cpp 推理程序仅用于验收。成品包不含这两项，用户自行连接已获授权的模型端点。
- 参考规范入口：[Agent Skills](https://agentskills.io/specification)、[MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)、[官方 TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)、[Chrome Side Panel](https://developer.chrome.com/docs/extensions/reference/api/sidePanel)、[Chrome 扩展政策](https://developer.chrome.com/docs/webstore/program-policies/policies)。
