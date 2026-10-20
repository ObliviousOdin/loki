# Loki

Loki is a personal AI agent with tools, memory, skills, delegation, scheduling, messaging, a terminal UI, a dashboard and a desktop application.

Loki uses the **0.1.0-alpha.1 preview** sequence. The [release page](https://github.com/ObliviousOdin/loki/releases) lists available artifacts and their measured scope; [delivery status](docs/loki/PREVIEW-STATUS.md) explains the qualification gates. [Upstream provenance](docs/loki/UPSTREAM.json) pins Hermes commit `18c525b669b6ea4ba62e6967d228af21d89aa9d3` from October 17, 2026: 1,376 commits after `v0.22.2`.

## Install the preview

The source is public at [ObliviousOdin/loki](https://github.com/ObliviousOdin/loki). Cloning it does not require a GitHub account.

The tagged installation below applies when `v0.1.0-alpha.1` appears on the release page. Before publication, developers can select `codex/loki-preview` in the clone and record `git rev-parse HEAD`; that branch is a development candidate.

```bash
git clone https://github.com/ObliviousOdin/loki.git
cd loki
git checkout v0.1.0-alpha.1
bash scripts/install.sh --commit "$(git rev-parse HEAD)" --non-interactive
```

On Windows, run `scripts\install.ps1 -Commit (git rev-parse HEAD) -NonInteractive` from that checkout. The [installation guide](docs/loki/INSTALL.md) covers authentication, data paths, unsigned artifacts, and configuration.

Start a new terminal, then:

```bash
loki --help
loki --version
loki setup
loki
```

Loki stores its own configuration, sessions, logs, memory, skills, caches and managed tools under `~/.loki` on macOS/Linux or `%LOCALAPPDATA%\loki` on Windows. `LOKI_HOME` and `LOKI_RUNTIME_DIR` provide explicit overrides. The retained engine checkout leaf is `hermes-agent`; it lives inside Loki's directory and is not an existing Hermes installation.

Existing agent state and Codex/Claude logins are not adopted automatically. API-key and local providers remain available. OAuth and hosted services require separately configured applications and credentials; upstream subscriptions, trials and signing accounts do not transfer to Loki.

## Preview scope

The fork retains source capabilities, but that does not prove all integrations work. [Verification and parity](docs/loki/VERIFICATION.md) distinguishes measured behavior, inherited source, externally configured services and untested platforms. [Release notes](docs/loki/RELEASE-NOTES.md) identify limitations and stable-release requirements.

Loki updates from its own repository. Source previews follow `main` unless an explicit pin/channel is selected. Packaged preview automatic updates and upstream publication are disabled. A preview never installs an upstream Hermes release.

## Development and upstream updates

Use `source ./activate` (Windows: `. .\activate.ps1`) with an isolated `LOKI_HOME`. The public command is `loki`; internal Python modules such as `hermes_cli`, gateway protocols and plugin APIs retain their upstream names. Use `scripts/run_tests.sh` for Python tests and `python scripts/check` for the upstream lint gate. See [maintenance](docs/loki/MAINTENANCE.md) and the retained [developer guide](AGENTS.md).

[Prioritized follow-ups](docs/loki/FOLLOWUPS.md) records the small candidate list.

## License and attribution

Loki is an independent fork of [Hermes Agent by Nous Research](https://github.com/NousResearch/hermes-agent). It retains the upstream [MIT license](LICENSE), copyright notices and third-party notices. See [NOTICE](NOTICE). This independent fork is not published or endorsed by Nous Research. Historical upstream documentation and internal names remain reference material; Loki's installation and release instructions above take precedence.
