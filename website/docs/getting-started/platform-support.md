---
sidebar_position: 2.5
title: "Loki Platform Scope"
description: "What the Loki source preview has actually tested, and which platforms and distribution paths remain unqualified."
---

# Loki Platform Scope

Inherited source support, CI execution, public installation and native application qualification are separate. Choose a version from [Loki releases](https://github.com/ObliviousOdin/loki/releases) and inspect that release's evidence. The known published [0.1.0-alpha.1](https://github.com/ObliviousOdin/loki/releases/tag/v0.1.0-alpha.1) is an unsigned source preview, with **no published native app**. The table below describes only that exact source, `12690b426de4610916f91fb42f008391df550f27`.

## Tier 1

These are the primary source-validation targets, not a stable-support or native-package guarantee:

| Platform | Alpha.1 evidence | Remaining boundary |
| --- | --- | --- |
| Linux | Full Python suite and controlled lean source-install scenarios in CI | Ordinary public-default installation, browser/computer-use and downloaded native app acceptance remain unqualified |
| macOS | Applicable source tests; controlled lean installs; additional public-network lean install and CLI/TUI startup on arm64 | No signed/notarized native app or downloaded-app acceptance; Intel source/native scope is not established by arm64 results |
| Windows | Applicable native-host source tests and controlled lean source-install scenarios | Ordinary public-default installation and native package/Store/signing acceptance remain unqualified |
| WSL2 | Retained Linux source path | No separate WSL2 user-install qualification claimed |

See the [published verification report](https://github.com/ObliviousOdin/loki/releases/download/v0.1.0-alpha.1/LOKI-VERIFICATION.json), [additional macOS source report](https://github.com/ObliviousOdin/loki/releases/download/v0.1.0-alpha.1/LOKI-MACOS-SOURCE-VERIFICATION.json) and [delivery status](https://github.com/ObliviousOdin/loki/blob/main/docs/loki/PREVIEW-STATUS.md) for counts, skips, retries and exact scope. A later development CI pass does not retroactively qualify alpha.1 or a future artifact.

Use the [owned source installation instructions](./installation.md#linux--macos--wsl2) for Linux/macOS/WSL2 or [Windows](./installation.md#windows-native). Lean installs explicitly exclude browser and computer-use setup. Real conversations, messaging delivery, OAuth and hosted services require their own credentials and acceptance.

## Tier 2

The inherited Nix, Termux, Docker and other architecture-specific source paths remain available for development and separate qualification. Their reference pages may name upstream packages, registries, signed repositories or application feeds. Those destinations are not owned Loki distribution channels. Do not install an upstream package or reuse its update feed to obtain Loki.

No Loki Termux APT repository, Homebrew package, PyPI wheel, Store listing, public container image or authenticated packaged update feed is established by the alpha.1 source release. Local builds and fixture tests do not publish or qualify those destinations. Nix and Android require separate platform evidence; source compatibility alone is insufficient.

### Build targets and support priority

The repository retains desktop and other build machinery. A target appearing in source or CI is not an available download. Only assets actually listed on a Loki release are published. Native build, signing/notarization, installation after download and update acceptance are separate gates, described in [production readiness](https://github.com/ObliviousOdin/loki/blob/main/docs/loki/PRODUCTION-READINESS.md).

## Unsupported

Generic `pip install`, `uv tool install` and unowned package repositories are not Loki installation instructions. The retained distribution guard prevents an incomplete generic Python wheel from omitting runtime resources. Follow the pinned [source installer](./installation.md) instead.

No additional OS, architecture, distribution or external service is qualified by an upstream support tier. Internal `hermes` module and schema names remain compatible; the public command is `loki`, with its own home and update source.
