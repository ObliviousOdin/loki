---
sidebar_position: 2
title: "Loki Installation"
description: "Install the pinned Loki source preview from its own public repository and verify its scope."
---

# Loki Installation

Choose a release from [Loki releases](https://github.com/ObliviousOdin/loki/releases), read its release notes, and use its recorded source commit. The commands below are a reproducible example for the known published [0.1.0-alpha.1](https://github.com/ObliviousOdin/loki/releases/tag/v0.1.0-alpha.1), an **unsigned source preview** at `12690b426de4610916f91fb42f008391df550f27`. It contains source, installers and notice companions; **no native desktop app is published in alpha.1**. Later candidates require their own qualification and are not implied by these instructions.

The [owned installation guide](https://github.com/ObliviousOdin/loki/blob/main/docs/loki/INSTALL.md), [delivery status](https://github.com/ObliviousOdin/loki/blob/main/docs/loki/PREVIEW-STATUS.md) and [platform evidence](./platform-support.md) define the preview's scope. Upstream Hermes installers, desktop downloads, signed packages, hosted repositories and automatic update feeds do not distribute Loki.

## Quick Install

### Linux / macOS / WSL2

Provide Git, curl, tar and SHA-256 utilities, inspect the selected source and installer, then run:

```bash
git clone https://github.com/ObliviousOdin/loki.git
cd loki
git checkout v0.1.0-alpha.1
test "$(git rev-parse HEAD)" = "12690b426de4610916f91fb42f008391df550f27" &&
  bash scripts/install.sh --commit 12690b426de4610916f91fb42f008391df550f27 --non-interactive --skip-browser --skip-computer-use
```

Open a new terminal if PATH was changed. This example deliberately selects the lean install used in the recorded source-install checks, excluding browser and computer-use setup. The installer uses the pinned public tools and dependency lock, prepares the terminal UI and dashboard, and installs the source at `~/.loki/hermes-agent`. The public command is `loki`; the internal checkout name remains compatible.

### Windows (native)

From PowerShell, with Git available:

```powershell
git clone https://github.com/ObliviousOdin/loki.git
Set-Location loki
git checkout v0.1.0-alpha.1
if ((git rev-parse HEAD) -ne "12690b426de4610916f91fb42f008391df550f27") { throw "Unexpected Loki source commit" }
.\scripts\install.ps1 -Commit 12690b426de4610916f91fb42f008391df550f27 -NonInteractive -SkipBrowser -SkipComputerUse
```

The default home is `%LOCALAPPDATA%\loki`, with commands in its `bin` directory. Keep PowerShell execution policy under your control; inspect the downloaded script. This source preview does not register a Microsoft Store identity or reuse an upstream certificate.

### What the source installer does

The installer provisions pinned tools through the retained PM architecture rather than a generic wheel or `pip install`. It downloads dependencies and builds interfaces. Browser and computer-use tools are included by default; `--skip-browser` and `--skip-computer-use` (PowerShell: `-SkipBrowser`, `-SkipComputerUse`) deliberately select a leaner install. Lean-install evidence does not qualify the default browser/computer-use path. Native dependencies and Linux browser system libraries can require platform prerequisites.

`--include-desktop` / `-IncludeDesktop` builds the desktop from source. A source build is not a signed package, a published native artifact or evidence of normal downloaded-app installation. The alpha.1 release has no native app to download; do not use an upstream DMG, MSIX, App Installer feed or Store package as a substitute.

### Install layout

| Platform | Source and command | User data |
| --- | --- | --- |
| macOS / Linux | `~/.loki/hermes-agent`, user command `loki` | `~/.loki` |
| Windows | `%LOCALAPPDATA%\loki\hermes-agent`, commands under its `bin` directory | `%LOCALAPPDATA%\loki` |

`LOKI_HOME` and `LOKI_RUNTIME_DIR` select explicit Loki state and tool-store paths. Keep them separate from existing agents. Fresh entry points do not adopt inherited `HERMES_*` state selectors or external logins automatically. Do not copy another agent's secrets, home or caches.

## After Installation

```bash
loki --version
loki --help
loki setup
loki config show
```

Configure a dedicated provider and model, then follow the [Quickstart](./quickstart.md) for conversation and resume checks. No provider subscription, OAuth application, Tool Gateway, telemetry collector or provisioning service is included. Hosted integrations require explicit configuration and authorization; setup alone is not service acceptance.

## Release artifacts and verification

Download only assets listed on your selected Loki release. For the alpha.1 example:

```bash
gh release download v0.1.0-alpha.1 --repo ObliviousOdin/loki
shasum -a 256 -c SHA256SUMS
```

The source archive contains the exact tree, installers and license/notice companions. Its installer still obtains the pinned public source through Git. Consult [source companions](https://github.com/ObliviousOdin/loki/blob/main/docs/loki/SOURCE-ASSETS.md) and the release's verification report; a checksum confirms bytes, not native signing or functional parity. Git cloning is public and requires no GitHub token; `gh` is optional for downloading release assets.

## Manual / Developer Installation

The [PM developer workflow](../reference/package-management.md#developer-workflow) and [development setup](../developer-guide/contributing.md#development-setup) describe the inherited architecture and test environment. Use a separate Loki home. Engine-internal names remain compatible; public installation and update destinations must belong to Loki.

Docker, Nix, Termux and desktop pages are advanced source references. Their inherited package/image/service examples do not establish owned Loki distribution or platform qualification. See [Platform Support](./platform-support.md) before choosing one and [Updating & Uninstalling](./updating.md) before changing or removing an install.

## Pinned inherited reference

The [original engine installation guide](https://github.com/ObliviousOdin/loki/blob/18c525b669b6ea4ba62e6967d228af21d89aa9d3/website/docs/getting-started/installation.md) is preserved at the pinned upstream baseline for advanced architecture and troubleshooting context. Its package names, installers, hosted services and platform claims are inherited reference, not Loki installation destinations or qualification.
