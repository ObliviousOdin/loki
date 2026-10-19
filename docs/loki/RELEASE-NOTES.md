# Loki 0.1.0-alpha.1

Unreleased candidate. Protected merge and preview publication remain pending; see [delivery status](PREVIEW-STATUS.md) for measured results and blockers.

Independent preview sequence: Python `0.1.0a1`; JavaScript/release tag `v0.1.0-alpha.1`.

Based on Hermes `18c525b669b6ea4ba62e6967d228af21d89aa9d3` (October 17, 2026), 1,376 commits after upstream `v0.22.2`, released October 15. The complete upstream Git history and MIT attribution are retained.

Changes: Loki command/package/application identities; owned data, cache, runtime, log and service paths; branded CLI/TUI/dashboard/desktop catalogs and icons; separate repository/update source; explicit credential adoption, OAuth and hosted-service configuration; disabled inherited publishing/signing/update infrastructure; Loki CI and preview installation receipts. Source updates must admit Loki-owned target identity before Git custody or archive overlay. Dashboard uninstall must preserve foreign service declarations and files. Scheduled recovery, SQLite recovery and provider setup guidance use Loki commands while preserving user-supplied names and paths. Internal engine modules and protocols remain compatible where practical. No earlier product branch was imported.

Preview requirements: read access to the project repository (authentication while private), supported native toolchains, and separately configured provider/messaging credentials. Packaged automatic updates are disabled. Generic PyPI wheel installation remains unsupported as upstream requires full runtime resources.

Native release assets must include the exact Loki source/lock/build recipes, the unmodified lock-pinned Pilk 0.2.4 source archive, its package license and the SILK codec redistribution notice. The app retains both codec notices alongside existing upstream and third-party attribution. See [source assets](SOURCE-ASSETS.md). Source/notice staging and build-path normalization need fresh native artifact verification; no final binary, reproducibility or licensing conclusion is claimed here.

Additional isolation fixes give Codex callbacks their own `loki-tools` registration, preserve foreign migration blocks, and require an explicit endpoint for automatic Telegram setup. Trusted bundled translation templates are branded before custom overlays and runtime values are applied. A WebSocket close race is corrected without changing timeout, abort or replay policy. These changes have regression tests; external-service and native-platform acceptance remain separate evidence.

Known first-run limitation: launching the terminal UI before choosing a model can report `storage_unavailable`. Complete `loki setup` or desktop setup first. Model-bound session startup was checked without a provider request; real provider conversation and resume acceptance remain separate release requirements.

Stable release requires exact-commit native installation/update acceptance on every claimed OS/architecture, real provider and messaging acceptance, owned OAuth registrations and any hosted-service credentials, owned signing/notarization certificates, a tested authenticated update feed, and a reviewed upstream-update procedure. Only platform artifacts actually attached to a release are available; unsigned previews do not satisfy signing requirements.

See `VERIFICATION.md` and the published evidence for measured tests and known baseline failures. This file must not be used as a claim that unexecuted tests passed.
