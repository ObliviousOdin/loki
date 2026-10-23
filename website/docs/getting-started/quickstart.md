---
sidebar_position: 1
title: "Loki Quickstart"
description: "Install a pinned Loki source preview, configure a dedicated provider, and check conversation persistence."
---

# Loki Quickstart

Start with the [Installation guide](./installation.md). The known published [0.1.0-alpha.1](https://github.com/ObliviousOdin/loki/releases/tag/v0.1.0-alpha.1) is an unsigned source preview, with no published native desktop app. Choose later releases from [Loki releases](https://github.com/ObliviousOdin/loki/releases) and follow their own notes and exact source commit. [Delivery status](https://github.com/ObliviousOdin/loki/blob/main/docs/loki/PREVIEW-STATUS.md) distinguishes source tests from installed-product and service acceptance.

## 1. Check your installation

Open a new terminal if the installer changed PATH, then run:

```bash
loki --version
loki --help
```

Confirm the version and installation path match the release you selected. For the alpha.1 example, the source commit is `12690b426de4610916f91fb42f008391df550f27`. Do not use an upstream Hermes installer or a previously configured agent home.

## 2. Configure a dedicated provider

```bash
loki setup
loki config show
```

Choose a provider and model that you are authorized to use. Supply a dedicated API key locally, or configure a local model endpoint. OAuth additionally requires an application authorized for Loki; existing external logins are not adopted by default. Loki supplies no subscription, hosted tool service or trial credits. Do not assume upstream Nous Portal access or another provider's account grants transfer to this fork.

The default profile lives in `~/.loki` on macOS/Linux, or `%LOCALAPPDATA%\loki` on Windows. Secrets belong in its `.env`; ordinary settings belong in `config.yaml`. `LOKI_HOME` selects a separate Loki home and `LOKI_RUNTIME_DIR` its tools store. Do not copy another agent's profiles, credentials or runtime state.

Select a model before starting the TUI. The alpha.1 macOS source preview can report `storage_unavailable` when a blank profile creates its first TUI session without a selected model. See the [owned installation guide](https://github.com/ObliviousOdin/loki/blob/main/docs/loki/INSTALL.md) for the observed scope.

## 3. Run a conversation

```bash
loki
```

Or use the terminal UI after completing setup:

```bash
loki --tui
```

Ask a small question, then a follow-up that refers to the first answer. A successful check means your chosen provider responds across both turns. Provider requests may incur charges under your account. Do not treat a welcome banner or a synthetic session test as a successful model conversation.

## 4. Verify persistence and resume

Exit normally, then start:

```bash
loki --continue
```

Confirm the earlier conversation is present in the same Loki profile and ask a question about it. If it is absent, inspect `loki sessions --help` and verify the selected home/profile before continuing. A real conversation and resume remain credential-dependent acceptance requirements; these instructions do not claim they have passed for your provider.

## 5. Configure optional capabilities

Once conversation and resume work, enable only the integrations you need:

```bash
loki tools
loki skills --help
loki gateway setup
loki gateway --help
```

Messaging requires your own platform tokens and allowlists. Browser/computer-use, voice, remote execution, cloud services and optional memory integrations have separate dependencies, credentials and acceptance requirements. Automatic Telegram QR provisioning needs an explicitly authorized service; manual bot-token setup remains available.

The [provider catalog](../integrations/providers.md), [tools](../user-guide/features/tools.md), [skills](../user-guide/features/skills.md), [messaging](../user-guide/messaging/index.md) and [TUI](../user-guide/tui.md) pages retain the advanced engine reference. Internal `hermes` names remain compatible; public steps use `loki`. Upstream installers, update feeds, package signatures and shared homes in reference examples are not Loki instructions.

## Troubleshooting

```bash
loki doctor
loki model
loki sessions --help
loki gateway status
```

Keep the base provider working before adding routing or services. Preserve your profile and installation logs when investigating a failure. Never post credential files or tokens in an issue. See [updating](./updating.md), [platform scope](./platform-support.md) and the [verification guide](https://github.com/ObliviousOdin/loki/blob/main/docs/loki/VERIFICATION.md) before relying on a deployment.

## Pinned inherited reference

The [original engine quickstart guide](https://github.com/ObliviousOdin/loki/blob/18c525b669b6ea4ba62e6967d228af21d89aa9d3/website/docs/getting-started/quickstart.md) preserves the advanced upstream guidance at the pinned baseline. Its internal commands, package/update destinations and hosted-service examples are reference material, not Loki installation instructions or service/native qualification. Use the Loki steps above and your selected release's evidence.
