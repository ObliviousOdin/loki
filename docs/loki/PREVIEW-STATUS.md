# Preview delivery status

Recorded October 20, 2026 (UTC). [Loki 0.1.0-alpha.1](https://github.com/ObliviousOdin/loki/releases/tag/v0.1.0-alpha.1) is a published **unsigned source preview**, built from commit `12690b426de4610916f91fb42f008391df550f27`. It contains source, installers and required notice companions. No packaged native application is published.

The [published verification report](https://github.com/ObliviousOdin/loki/releases/download/v0.1.0-alpha.1/LOKI-VERIFICATION.json) has SHA-256 `6150c978f37c05f07362cc4e2277bbf84e0d401478e196caf949eccb45ba6434`. It identifies the exact source, test scopes, skips and artifact hashes. All nine original release assets and this additional report were downloaded anonymously and hash-verified. The report is additional to the immutable software `SHA256SUMS` manifest.

## Measured scope

The [protected PR-head run](https://github.com/ObliviousOdin/loki/actions/runs/39350417603) and [merged-commit run](https://github.com/ObliviousOdin/loki/actions/runs/39355462656) each completed all 16 jobs successfully. These results qualify their recorded commits; later repository changes require fresh checks.

| Check at the published source | Result and boundary |
|---|---|
| Full Linux Python suite | 6,455 files; 65,161 passed, 959 skipped; no final failures, setup errors, crashes or reported file retries on the merged-source run |
| Desktop UI / Electron | 11,259 UI passes; 3,640 Electron passes with 24 skips; builds and lint/type checks passed |
| Actual macOS / Windows hosts | Applicable source subsets and 15 Windows runtime contracts passed; native-host tests do not qualify packaged applications |
| Controlled lean source installs | Eight scenarios on each of Linux, macOS and Windows: help/version, configuration, gateway help, synthetic cross-process persistence, a real local terminal tool and foreign-state isolation |
| Source distribution | Exact source/archive/installer/metadata/notice/checksum validation and published-asset downloads passed |

The controlled installers used local source and explicit temporary paths, with browser and computer-use installation excluded. The additional ordinary public-network installation into default macOS paths and installed CLI/TUI startup remain unqualified because local disk capacity is unavailable. An update-source resolution check is not an executed update. Synthetic session persistence is not a provider conversation or resume.

## Open acceptance requirements

The PR-head run reported an intermittent paused-mailbox receipt test failure; the merged-source Windows run reported an intermittent update-marker test failure. Both passed the runner's existing retry. Neither has an established cause or fix; both remain stable-release requirements. Successful retries must remain visible in release evidence.

A real provider conversation/resume and messaging delivery require dedicated credentials and acceptance. OAuth, hosted services, browser/computer-use and wake-word behavior retain their own external configuration and verification requirements. Existing agent state or external logins are not adopted automatically.

Packaged native applications, signing/notarization, quarantined-download acceptance and native installation/update flows remain unqualified. No Developer ID, Windows signing, Store acceptance or authenticated packaged update feed is claimed. Packaged automatic updates remain disabled. Select a provider and model with `loki setup` before starting the TUI; a blank model can report `storage_unavailable`.

The [verification guide](VERIFICATION.md) retains historical baseline diagnostics. [Production readiness](PRODUCTION-READINESS.md) defines stable promotion; [installation](INSTALL.md), [release notes](RELEASE-NOTES.md) and [maintenance](MAINTENANCE.md) explain the supported preview path. Source availability and passing scoped checks do not establish full functional parity.
