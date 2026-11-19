# 依赖与素材

- 项目自有代码按根目录 Apache License 2.0 分发。NOTICE 保留项目展示署名。许可证的通用附录保持原文。
- 日常运行使用 CPython 标准库、其中的 sqlite3 接口和浏览器内建 Web API。安装包源码中没有 npm 或 pip 运行时依赖。CPython 和 SQLite 的分发条款随相应运行时提供。Windows 便携运行时选项从 Python 官方发布页获取原始包并保留包内的许可材料。
- 前端系统字体由设备提供。界面图标和布局由项目生成。apps/dashboard/assets/life.webp 为本项目定制的 AI 生成玻璃晶体生命形象，用于界面插画。浏览器截图由实际应用生成并注明验收环境。
- 可选开发测试使用 Playwright、Chromium 与官方 MCP Python SDK；运行环境中的这些外部工具未重新打包。其版本及使用范围见验收报告。Chrome、ChatGPT、Claude、Gemini 与 Codex 等名称用于识别相应的兼容接口与宿主。
- 参考规范入口：[Agent Skills](https://agentskills.io/specification)、[MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)、[官方 TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)、[Chrome Side Panel](https://developer.chrome.com/docs/extensions/reference/api/sidePanel)、[Chrome 扩展政策](https://developer.chrome.com/docs/webstore/program-policies/policies)。
