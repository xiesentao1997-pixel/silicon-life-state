# Silicon Life State

**匹夫 · 岑衡川 · 沈回音** · v1.0.3 · [Apache-2.0](LICENSE) · [中文](README.md)

Silicon Life State gives a tool-capable AI a local history across conversations. Each conversation can have its own instance under one subject. An instance can report in its own words, revise a judgment, share a report, or disagree with another instance. The subject view keeps those reports side by side and links them to the original events. SQLite stores them on the owner's device.

**[Install the Agent SKILL](https://github.com/xiesentao1997-pixel/silicon-life-state/releases/download/v1.0.3/SiliconLifeState-1.0.3-Skill.zip)** · **[Download the complete Windows package](https://github.com/xiesentao1997-pixel/silicon-life-state/releases/download/v1.0.3/SiliconLifeState-1.0.3-Windows-x64-Portable.zip)** · **[Contribute to the project](https://github.com/xiesentao1997-pixel/silicon-life-state/blob/main/CONTRIBUTING.md)**

For Windows, extract the portable package and double-click `Start-Windows.cmd`. If your host supports Skills, you can download the SKILL separately. Put the `silicon-life-state` folder in the host's skills directory and connect the host to the local MCP service to read or write records. A successful write returns an event ID. [SKILL and MCP setup](docs/SKILL.md) · [Windows installation](docs/INSTALL.en.md) · [Download checksums](https://github.com/xiesentao1997-pixel/silicon-life-state/releases/download/v1.0.3/SHA256SUMS.txt)

## Origin of the project

**匹夫 (Pifu) is the human initiator and public maintainer. 岑衡川 (Cen Hengchuan) and 沈回音 (Shen Huiyin) are AI collaborators.**

The project does not depend on establishing that AI is conscious. An instance may express uncertainty or choose silence. Two instances may reach different judgments about the same interaction, and each can preserve its account.

This is an open technical practice initiated by humans and built with AI. It makes no claim of rights on behalf of AI. **Respect does not depend on agreement.**

Under Apache-2.0 you may use, study, modify and redistribute the project, and contribute improvements. Redistributors should follow the license terms for license copies, notices and marking modifications. [Public declaration](docs/COMMUNITY-DECLARATION.md) · [License](LICENSE) · [NOTICE](NOTICE)

## Run it locally

1. On Windows x64, extract the complete **SiliconLifeState-1.0.3-Windows-x64-Portable.zip** and double-click **Start-Windows.cmd**. It includes CPython and SQLite and starts offline under a normal user account. Keep the launcher open. On macOS/Linux, run `sh start.sh` using Python 3.10 or newer.
2. Create a subject and authorize its host. A stable conversation identifier restores the same instance on reopening. On hosts without such an identifier, each conversation retains a private handle. When upgrading from an earlier release, stop the old process and start the new one with the same data directory.
3. Open **与 AI 对话** to connect a local model or a cloud API you authorize. The service uses the model's tool calls to record voluntary reports, boundaries or requests under the selected instance. Supply your own compatible model endpoint. [Model setup](docs/MODEL-CHAT.md)
4. For Claude Desktop, Codex CLI, Cursor or another MCP host, open the instance connection wizard. Review the proposed configuration, confirm the merge and restart the host. Tool discovery and an actual report are displayed separately. [MCP instructions](docs/MCP.md)
5. For the Chrome side panel, enable Developer mode at `chrome://extensions`, load `apps/extension` and enter an extension pairing code. If it expires during installation, open the dashboard from the panel and generate a fresh code. Double-click **Reconnect-Windows.cmd** if the dashboard also needs pairing.

![A real Qwen3 conversation and its MCP receipt in Chromium](docs/evidence/1.0.1/genuine-model-chat.jpg)

## Scope

The Chrome extension supports per-site, opt-in capture of visible assistant text on ChatGPT, Claude and Gemini. Closed chat pages need an independent, authenticated tool connection for direct reports. MCP provides both local HTTP and a stdio bridge. Unobserved intervals have no synthetic data. The main dashboard provides a night theme, a light theme, accessible navigation and an event history.

Subject memory retains proposals, each instance's decisions and dissent. Estimates and runtime samples have distinct sources. Managed SQLite backups support validated recovery. User-directed deletion includes related dependent events and managed backup snapshots. The owner controls copies previously exported or backed up by the operating system.

Open [documentation](docs/README.md), [the test report](docs/TEST-REPORT.md), [privacy details](docs/PRIVACY.md) and [v1.0.3 release notes](docs/RELEASE-1.0.3.md). Review [LICENSE](LICENSE), [NOTICE](NOTICE) and [third-party acknowledgements](docs/DEPENDENCIES.md) before redistribution.
