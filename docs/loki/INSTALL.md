# Loki preview installation

Publication is pending the protected CI gate. The tag and release-download commands below apply after the preview is published; see [delivery status](PREVIEW-STATUS.md) for the current candidate and blockers.

Until repository access is public, sign in using `gh auth login` with an account granted access to `ObliviousOdin/loki`. Credentials remain in your normal GitHub credential manager; the installer does not embed tokens. Public source downloads do not require an account. A private repository's source and assets require authorization.

## Source preview (macOS and Linux)

```bash
gh repo clone ObliviousOdin/loki
cd loki
git checkout v0.1.0-alpha.1
# If Git uses HTTPS, configure its credential helper through GitHub CLI:
gh auth setup-git
bash scripts/install.sh --commit "$(git rev-parse HEAD)" --non-interactive
```

The installer downloads hash-pinned public tools and installs the committed dependency lock through the upstream PM architecture. It builds the terminal UI and dashboard. `--include-desktop` also builds the desktop application. `--skip-browser` and `--skip-computer-use` are explicit lean-install options, not the default feature set.

The source checkout installs at `~/.loki/hermes-agent`; the public command is linked into your user command directory. Open a new terminal if the installer changed PATH. Run `loki --version` and confirm both the Loki version and installation path.

## Windows source preview

From PowerShell (authenticate GitHub CLI first if repository access is private):

```powershell
gh repo clone ObliviousOdin/loki
Set-Location loki
git checkout v0.1.0-alpha.1
gh auth setup-git
.\scripts\install.ps1 -Commit (git rev-parse HEAD) -NonInteractive
```

The product home is `%LOCALAPPDATA%\loki`, with commands in its `bin` directory. PowerShell execution policy remains under your control; download and inspect the script before running it. This preview does not register a Microsoft Store identity or reuse a Hermes certificate.

## Optional Honcho memory

`loki plugins install honcho` installs Loki's pinned compatibility copy from this repository. Git needs read access to `ObliviousOdin/loki`; private access requires authentication. The normal plugin scan, dependency consent and PM installation remain in effect. Configure it with `loki memory setup honcho` using your own API key or self-hosted server. OAuth additionally requires an application authorized for Loki. The provider uses Loki's `honcho.json` and profile host names; it does not import `~/.honcho` or existing agent memory. Explicit backend, workspace and peer settings remain under your control. This optional integration has local configuration/constructor tests; real Honcho service and OAuth qualification require external configuration.

## Release artifacts

```bash
gh release download v0.1.0-alpha.1 --repo ObliviousOdin/loki
shasum -a 256 -c SHA256SUMS
```

The source archive contains the exact release tree, its license/notices, and installers. Extract it and run its installer with the commit from `LOKI-PREVIEW.json`; installation still clones the pinned project source through Git. Private source access requires authentication. The archive is not a Python wheel: upstream deliberately blocks generic wheel/sdist distribution because it would omit runtime resources. Loki preserves that guard.

Native downloads also require the [source and notice companions](SOURCE-ASSETS.md) listed in `LOKI-PREVIEW.json`, including the exact lock-pinned Pilk source archive. Keep those files with the native artifact and verify every companion against `SHA256SUMS`.

Only native artifacts actually listed in the release are available. An unsigned/unnotarized macOS preview needs an explicit macOS trust decision; it is not Developer ID signed or notarized. Do not disable system security globally. An unsigned Windows package is not proof of normal Windows installation or signing qualification. Do not claim Linux/macOS/Windows native app qualification from a source archive or a cross-build.

### macOS arm64 native candidate

Choose the macOS arm64 asset explicitly labeled `UNSIGNED`, verify its SHA-256 against the supplied manifest, then extract the ZIP and copy `Loki.app` into an Applications directory. The preview currently targets a ZIP artifact; no final DMG installation is qualified. The first launch may require your explicit approval in macOS for this unnotarized application; verify its origin and checksum before granting that trust.

The app creates its own `loki` launcher in `~/.local/bin`. Add that directory to your shell PATH if necessary, then run `loki --version` and `loki --help`. A native preview reports `0.1.0-alpha.1` and its embedded source commit; the Python source installation reports the equivalent `0.1.0a1`. Check the commit against the artifact's metadata. Configure a dedicated provider in Loki before starting a real conversation.

Earlier native evidence covers an actual ZIP installation and app startup on macOS arm64. Those candidates are superseded; a corrected candidate requires fresh exact-commit build and installation receipts. Published-download installation, native Windows/Linux packages, signing and notarization remain pending; the [delivery status](PREVIEW-STATUS.md) records the exact candidate and measured scope.

## Configuration and isolation

```bash
loki setup
loki config show
loki sessions --help
loki gateway --help
```

Configure a dedicated provider key through Loki setup or its own `.env`. Do not copy an existing agent home. A real model conversation requires a usable provider key, a local provider, or a separately configured OAuth application. Do not assume upstream trial credits or subscription grants apply.

Complete provider and model selection with `loki setup` or the desktop setup screen before opening `loki --tui`. A clean profile with no selected model can currently show `storage_unavailable` when the TUI creates its first session. This preview limitation was observed on macOS arm64; the database integrity check passed, and selecting a model allowed session startup. That check did not make a provider request or qualify a real conversation.

`LOKI_HOME` selects an explicit Loki home; `LOKI_RUNTIME_DIR` selects its tools store. The default is `~/.loki` (macOS/Linux) or `%LOCALAPPDATA%\loki` (Windows). Fresh Loki entry points ignore inherited `HERMES_*` activation/state selectors; the engine translates explicit `LOKI_*` values into its retained internal variables. Profiles remain separate inside the Loki home. Product-specific project instructions use `LOKI.md` or `.loki.md`. Project-local plugins, skills, attachment staging and verification manifests use `./.loki`; `./.hermes` is not adopted. Existing shared `./.agents/skills` discovery retains its explicit project-trust gate.

External Codex/Claude login adoption defaults to false. Enabling `auth.adopt_external_logins` is an explicit credential-sharing choice. OAuth client IDs are configured under `auth.oauth_clients.<provider>.client_id`; choose a client application you are authorized to use. `auth.hosted_services` defaults to false. Telemetry is off by default, and no upstream collector endpoint is supplied.

Telegram bot setup supports manual tokens from @BotFather. Automatic QR setup additionally requires `TELEGRAM_ONBOARDING_URL` pointing to an authorized service; Loki has no inherited provisioning endpoint. Its Codex tool callback server uses the separate `loki-tools` entry. Migration preserves foreign managed configuration blocks and their server/plugin settings.

Optional telemetry uploads require separate consent and `telemetry.shared_metrics.endpoint` set to an HTTPS collector you control. Loki supplies no collector service. Choosing collection or saving upload consent does not configure a destination or prove an upload occurred.

## Updates and uninstall

`loki update` uses `ObliviousOdin/loki`; the preview source default is `main`. The selected source must declare the stable Loki product, command, distribution, repository and executable entry point before update custody can begin or a source tree can land. An infrastructure-only bootstrap is intentionally refused until the Loki implementation merges. Keep the preview pinned to its admitted commit and review changes before moving it. Packaged preview automatic updates are disabled until Loki has an owned authenticated feed and signed artifacts. Never use upstream Hermes installers to update Loki.

Use `loki uninstall --help` for the product's removal options. Loki cleanup targets its own directories, application and service identities. Preserve user data deliberately; do not remove unrelated application directories.
