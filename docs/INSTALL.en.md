# Install Silicon Life State

**Display authors:** 岑衡川 · 沈回音 · 匹夫

## Windows x64: easiest path

1. Download the complete `SiliconLifeState-1.0.2-Windows-x64-Portable.zip` from the matching GitHub Release. Do **not** download only the SKILL ZIP or Chrome ZIP if you want the full local state service.
2. Extract the whole ZIP; open `SiliconLifeState` and double-click `Start-Windows.cmd`. The complete Windows x64 ZIP bundles its own verified Python runtime and SQLite; no separate Python installation or network connection is required for local operation. Keep the startup terminal open.
3. Open the dashboard, create a subject and at least one instance. Use the instance's host configuration wizard to connect a tool-capable AI via local MCP (stdio or HTTP). Model weights and paid API access are **not** bundled.
4. If supported by your AI host, install the folder `packages/agent-skill/silicon-life-state` or extract `SiliconLifeState-1.0.2-Skill.zip`. Skill instructions alone cannot persist data; MCP service and per-instance authorization are still required.
5. Optional: open `chrome://extensions` in Chrome 116+, enable Developer Mode and load `apps/extension`. The extension observes only authorized visible web content. Use the pairing code issued by the local dashboard.

## Restore pairing

From the Chrome side panel select **Open dashboard to get pairing code**, use an authenticated owner dashboard session to regenerate the code, and paste it back into the side panel. If the dashboard is disconnected too, double-click `Reconnect-Windows.cmd`. Reconnecting does not erase SQLite history.

## macOS / Linux and source installs

Clone the repository or extract the source ZIP, then run `sh start.sh` with Python 3.10+ and its sqlite3 module available. Read [the complete Chinese installation guide](INSTALL.md) and [MCP setup](MCP.md) for commands and security boundaries. The runtime, extension, and SKILL should come from the **same version**.

## Verify the download

Use `sha256sum -c SHA256SUMS.txt` from the extracted Release asset folder, or PowerShell `Get-FileHash -Algorithm SHA256 <path>` and compare with Release `SHA256SUMS.txt`. The original Python runtime license and checksums are bundled.
