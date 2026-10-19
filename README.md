<p align="center">
  <img src="assets/loki-banner.svg" alt="Loki: One agent. Every shape." width="100%">
</p>

<p align="center">
  <b>A personal AI agent that remembers you, learns new tricks, and works wherever you do.</b>
</p>

<p align="center">
  <a href="#status"><img src="https://img.shields.io/badge/status-0.1.0--alpha_preview-8A6428?style=for-the-badge&labelColor=304B42" alt="Status: 0.1.0-alpha preview"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-536D4F?style=for-the-badge&labelColor=304B42" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11_%E2%80%93_3.14-3F7562?style=for-the-badge&labelColor=304B42&logo=python&logoColor=FFFFFF" alt="Python 3.11 to 3.14">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://img.shields.io/badge/fork_of-Hermes_Agent-526D80?style=for-the-badge&labelColor=304B42" alt="Fork of Hermes Agent"></a>
</p>

<p align="center">
  <a href="#meet-loki">Meet Loki</a> ·
  <a href="#what-loki-does">What Loki does</a> ·
  <a href="#get-started">Get started</a> ·
  <a href="#status">Status</a> ·
  <a href="#built-on-hermes-agent">Built on Hermes</a>
</p>

---

## Meet Loki

Loki is one agent that takes whatever shape the job needs. Work with it in a terminal, open it as a desktop app, check on it from a web dashboard, or message it from your phone while it runs on a server. Point it at the model you prefer, and switch whenever you like.

It doesn't start from zero each time. Loki keeps a memory of you and your projects, turns finished work into reusable skills, hands side tasks to subagents, and runs scheduled jobs while you're away.

## What Loki does

<table>
<tr>
<td width="50%" valign="top">

**Remembers you**<br>
Persistent memory and searchable session history, so context carries from one conversation to the next.

</td>
<td width="50%" valign="top">

**Learns new tricks**<br>
Turns solved problems into skills it can reuse, and sharpens them each time it runs them.

</td>
</tr>
<tr>
<td width="50%" valign="top">

**Lives where you work**<br>
A terminal UI, desktop app, web dashboard, and a messaging gateway for Telegram, Discord, Slack and more.

</td>
<td width="50%" valign="top">

**Any model, no lock-in**<br>
Bring an API key or run a local model. Change providers without changing code.

</td>
</tr>
<tr>
<td width="50%" valign="top">

**Delegates and schedules**<br>
Splits big jobs across parallel subagents and runs recurring tasks on its own schedule.

</td>
<td width="50%" valign="top">

**Runs anywhere, extends at the edges**<br>
Local, Docker, SSH or cloud sandboxes. Add plugins, skills and MCP servers.

</td>
</tr>
</table>

## Get started

> [!IMPORTANT]
> **Loki 0.1.0-alpha.1 is in review and not yet released.** The `loki` command, its installers and Loki's own data folder arrive with [pull request 6](https://github.com/ObliviousOdin/loki/pull/6). Until it merges, `main` holds the inherited engine unchanged, and its command is still `hermes`.

To try the preview from source on macOS or Linux:

```bash
git clone --branch codex/loki-preview https://github.com/ObliviousOdin/loki.git
cd loki
bash scripts/install.sh --commit "$(git rev-parse HEAD)" --non-interactive
```

On Windows, check out the same branch in PowerShell, then run:

```powershell
.\scripts\install.ps1 -Commit (git rev-parse HEAD) -NonInteractive
```

Open a new terminal and say hello:

```bash
loki setup    # choose a provider and model first
loki          # start talking
```

**Your data stays separate.** Loki keeps its config, memory, skills and logs in `~/.loki` on macOS and Linux, or `%LOCALAPPDATA%\loki` on Windows. It doesn't adopt an existing Hermes setup or other apps' logins unless you opt in.

## Status

Loki is an **alpha**. Here is what that means today:

- **Full engine, partial proof.** Loki keeps every capability of the engine it's built on, but having the code isn't the same as having tested it. Each integration is verified on its own before it's called ready.
- **Bring your own credentials.** Model providers, messaging platforms and OAuth apps need your own keys or apps. Upstream subscriptions and trials don't carry over.
- **Unsigned builds, manual updates.** Native builds aren't signed or notarized yet, and automatic updates stay off until they are.

Follow progress in [pull request 6](https://github.com/ObliviousOdin/loki/pull/6).

## Built on Hermes Agent

Loki is an independent fork of [Hermes Agent](https://github.com/NousResearch/hermes-agent) by [Nous Research](https://nousresearch.com). It is not published or endorsed by Nous Research. Internal names such as `hermes_cli` keep their upstream spelling so the engine stays easy to update.

The original Hermes README, with its install guide, command reference, documentation links and translations, now lives in **[docs/hermes](docs/hermes/README.md)**.

## Contributing

Read the [development guide](AGENTS.md) first, then [CONTRIBUTING.md](CONTRIBUTING.md) for the test environment.

```bash
source ./activate        # provision and enter the development environment
python scripts/check     # every blocking lint check CI runs
scripts/run_tests.sh     # the test suite (never bare pytest)
```

## License

MIT. See [LICENSE](LICENSE). Hermes Agent is © 2025 Nous Research.

<br>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/loki-mark-white.svg">
    <img src="assets/loki-mark-black.svg" alt="Loki mark" width="56">
  </picture>
  <br>
  <sub>One agent. Every shape.</sub>
</p>
