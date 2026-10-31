# Loki 0.1.0-alpha.2 — release candidate

This candidate adds the optional `smart-home` Home Assistant capability. It is disabled
until installed and configured for an individual profile. The existing plugin settings
form provides a masked token field, exact light/switch allowlist and read-only default.
Connection checks and device reads happen only on explicit tool calls. On/off changes
require a fresh approve-once response from a human, including when ordinary approvals
are off. Unavailable viewers or devices block changes; uncertain writes are not retried.
Camera streams, locks, arbitrary services and unattended device changes are excluded.
See the [setup guide](../../optional-plugins/smart-home/README.md).

Python reports `0.1.0a2`; the desktop and other workspace packages report the equivalent
`0.1.0-alpha.2`. Source preview packaging now derives its version from the exact admitted
commit, so a new release cannot silently retain the earlier artifact version.

This candidate has no real Home Assistant or camera acceptance yet. No device endpoint
or credential is supplied. Unsigned preview packaging and signed desktop update delivery
are separate: no signed/notarized build or authenticated automatic-update feed is claimed.
Publication, CI and artifact receipts must identify the final admitted commit before
this candidate is described as released.

# Loki 0.1.0-alpha.1

[Published unsigned source preview](https://github.com/ObliviousOdin/loki/releases/tag/v0.1.0-alpha.1), built from `12690b426de4610916f91fb42f008391df550f27`. Python reports the equivalent `0.1.0a1`; JavaScript and the release tag use `0.1.0-alpha.1`. Packaged native applications are not included.

Based on Hermes `18c525b669b6ea4ba62e6967d228af21d89aa9d3` (October 17, 2026), 1,376 commits after upstream `v0.22.2`, released October 15. The upstream Git history, MIT attribution and third-party notices are retained.

## Changes

Loki has its own command, package/application identities, icons, interface text, repository/update source, and configuration, cache, runtime, log and service paths. Default user data is `~/.loki` on macOS/Linux or `%LOCALAPPDATA%\loki` on Windows. Credential adoption is explicit; upstream OAuth applications, hosted subscriptions, signing accounts and existing agent state do not transfer.

The fork retains engine modules, protocols and architecture where practical. Source updates admit Loki-owned identity before Git custody or archive overlay; uninstall preserves foreign declarations and files. Regression fixes cover command guidance, translation templates, a WebSocket close race, SQLite browse deadlines, Windows runtime discovery/PowerShell transport and container identity binding. Inherited publication/signing/update infrastructure stays disabled. No earlier product parity branch was imported.

## Verification

All 16 jobs passed for both the protected PR head and the published merged commit. Merged-source Linux Python recorded 6,455 files, 65,161 passed and 959 skipped, with no final failures or reported file retries. UI/Electron, lint/type/build checks, Linux directory packaging, actual macOS/Windows source subsets, 15 Windows runtime contracts and eight controlled lean source-install scenarios on each of Linux/macOS/Windows passed. Controlled installs verify local tools and synthetic persistence; they do not prove live provider delivery or packaged-native acceptance.

The [published report](https://github.com/ObliviousOdin/loki/releases/download/v0.1.0-alpha.1/LOKI-VERIFICATION.json), SHA-256 `6150c978f37c05f07362cc4e2277bbf84e0d401478e196caf949eccb45ba6434`, records exact scopes and skips. All nine original software/source/notice/checksum assets and the report were anonymously downloaded and hash-verified. Software assets and `SHA256SUMS` remain immutable. See [delivery status](PREVIEW-STATUS.md) for linked CI and [source companions](SOURCE-ASSETS.md) for the lock-pinned Pilk 0.2.4 source, license and SILK notices. Generic wheel-only installation remains unsupported because the engine requires its full runtime resources.

## Known limitations

An intermittent paused-mailbox test on the PR head and an intermittent Windows update-marker test on the merged source passed existing retries. Neither has an established cause or fix. The additional default-path macOS public-network install and installed CLI/TUI startup are pending disk capacity. Real provider conversation/resume and messaging remain untested with dedicated credentials.

Choose a provider and model with `loki setup` before starting the TUI; a blank model can report `storage_unavailable`. Browser/computer-use, OAuth, hosted-service and wake-word behavior require their own configuration and acceptance. Native packages, signing/notarization, quarantined-download trust and native installation/update flows remain unqualified. Packaged automatic updates are disabled. Full functional parity is not established.

Stable promotion requires the evidence in [production readiness](PRODUCTION-READINESS.md), including resolution of the two intermittent failures, real integration acceptance and qualified signing/update infrastructure for each claimed native platform. Future changes use protected `main`, new release versions and [history-preserving upstream integration](MAINTENANCE.md).
