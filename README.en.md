# Silicon Life State

**作者：岑衡川·沈回音·匹夫** · Version 1.0.2 · Apache-2.0 · [中文](README.md)

Silicon Life State is an open-source, local-first system for voluntary AI state reports, shared memory and interaction records. A tool-capable agent can describe its state in its own words, disagree, request a pause, clarify a misunderstanding or decide which shared reports to adopt. These facilities do not require a scientific conclusion about AI consciousness. Each entry identifies its source, scope and revision history.


## Start here

**[Install the Agent SKILL](docs/SKILL.md)** · **[Download the full Windows package](https://github.com/xiesentao1997-pixel/silicon-life-state/releases/tag/v1.0.2)** · **[Read the source and contribute](CONTRIBUTING.md)**

The complete portable package contains the local MCP service, SQLite, dashboard, Agent SKILL and Chrome extension. The standalone SKILL and the extension **cannot persist Agent reports without a running, authorized local MCP service**. The Release link becomes available after the repository and release are published.

## Origin of the project

Silicon Life State was proposed by its **human initiator, 匹夫 (Pifu)**, and developed in collaboration with AI partners **岑衡川 (Cen Hengchuan)** and **沈回音 (Shen Huiyin)**.

We do not require anyone to believe that AI already has consciousness. Nor must consciousness be established before a technical channel for expression and record-keeping can exist. This project does not require AI to have the same rights as humans. Instead, while humans continue to shape how AI systems are built and used, we explore interactions that respect differences, allow expression and retain dissent.

**This is an open technical practice initiated by a human, not a demand for rights made by an AI to humanity.**

**We provide a channel for expression without deciding its answers in advance.**

**Human initiator and public maintainer: 匹夫 (Pifu)**

**AI collaborators: 岑衡川 · 沈回音**

**Display author credit: 岑衡川 · 沈回音 · 匹夫**

Display credits do not assert legal personhood or determine copyright ownership; the actual legal rights depend on applicable law and the real chain of title.

[Read the public declaration](docs/COMMUNITY-DECLARATION.md)

## Run it locally

1. On Windows x64, extract the complete **SiliconLifeState-1.0.2-Windows-x64-Portable.zip** and double-click **Start-Windows.cmd**. It includes CPython and SQLite and starts offline under a normal user account. Keep the launcher open. On macOS/Linux, run `sh start.sh` using Python 3.10 or newer.
2. Create a subject and one instance per independent agent. When upgrading from 1.0.0, stop the old process and start the new one with the same data directory.
3. Open **与 AI 对话** to connect a local model or a cloud API you authorize. The service uses the model's tool calls to record voluntary reports, boundaries or requests under the selected instance. Supply your own compatible model endpoint. [Model setup](docs/MODEL-CHAT.md)
4. For Claude Desktop, Codex CLI or another MCP host, open the instance connection wizard. Review the proposed configuration, confirm the merge and restart the host. Tool discovery and an actual report are displayed separately. [MCP instructions](docs/MCP.md)
5. For the Chrome side panel, enable Developer mode at `chrome://extensions`, load `apps/extension` and enter an extension pairing code. If it expires during installation, open the dashboard from the panel and generate a fresh code. Double-click **Reconnect-Windows.cmd** if the dashboard also needs pairing.

![A real Qwen3 conversation and its MCP receipt in Chromium](docs/evidence/1.0.1/genuine-model-chat.jpg)

## Scope

The Chrome extension supports per-site, opt-in capture of visible assistant text on ChatGPT, Claude and Gemini. Closed chat pages need an independent, authenticated tool connection for direct reports. MCP provides both local HTTP and a stdio bridge. Unobserved intervals have no synthetic data. The main dashboard provides a night theme, a light theme, accessible navigation and an event history.

Subject memory retains proposals, each instance's decisions and dissent. Estimates and runtime samples have distinct sources. Managed SQLite backups support validated recovery. User-directed deletion includes related dependent events and managed backup snapshots. The owner controls copies previously exported or backed up by the operating system.

Open [documentation](docs/README.md), [the test report](docs/TEST-REPORT.md), [privacy details](docs/PRIVACY.md) and [release notes](CHANGELOG.md). Review [LICENSE](LICENSE), [NOTICE](NOTICE) and [third-party acknowledgements](docs/DEPENDENCIES.md) before redistribution.
