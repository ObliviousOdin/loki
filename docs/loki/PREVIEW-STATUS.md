# Preview delivery status

Updated October 21, 2026 (UTC). [Loki 0.1.0-alpha.1](https://github.com/ObliviousOdin/loki/releases/tag/v0.1.0-alpha.1) is a published **unsigned source preview**, built from commit `12690b426de4610916f91fb42f008391df550f27`. It contains source, installers and required notice companions. No packaged native application is published.

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
| Additional macOS arm64 source acceptance | Public-network installation at default paths in a fresh HOME with spaces; configuration, synthetic persistence, local terminal, isolation, CLI setup recovery and TUI startup/normal quit passed |

The controlled installers used local source and explicit temporary paths, with browser and computer-use installation excluded. On October 20, the additional lean public-network installation and installed CLI/TUI startup passed on macOS arm64 at the exact published commit. Its [measured report](https://github.com/ObliviousOdin/loki/releases/download/v0.1.0-alpha.1/LOKI-MACOS-SOURCE-VERIFICATION.json) records hashes, scope and earlier unsuccessful acceptance-script attempts. Telemetry was declined; existing sessions were preserved and no new API calls or messages were recorded. Browser and computer-use installation remained explicitly excluded. Ordinary public-default installation on Linux and Windows remains unqualified. An update-source resolution check is not an executed update. Synthetic persistence is not a provider conversation or resume.

## Open acceptance requirements

At alpha.1, the PR-head run reported an intermittent paused-mailbox receipt test failure; the merged-source Windows run reported an intermittent update-marker test failure. Both passed the runner's existing retry. Those historical receipts remain unchanged. Later deterministic mailbox and Windows fixture corrections do not establish the exact cause of every earlier failure; successful retries must remain visible in release evidence.

A real provider conversation/resume and messaging delivery require dedicated credentials and acceptance. OAuth, hosted services, browser/computer-use and wake-word behavior retain their own external configuration and verification requirements. Existing agent state or external logins are not adopted automatically.

Packaged native applications, signing/notarization, quarantined-download acceptance and native installation/update flows remain unqualified. No Developer ID, Windows signing, Store acceptance or authenticated packaged update feed is claimed. Packaged automatic updates remain disabled. Select a provider and model with `loki setup` before starting the TUI; a blank model can report `storage_unavailable`.

## Unpublished alpha.2 candidate

[PR #9](https://github.com/ObliviousOdin/loki/pull/9) adds dependency and mailbox corrections, Windows process-completion checks, first-session setup recovery, real Docker and website CI gates, and manual source/native delivery checks. The latest completed [combined diagnostic CI run](https://github.com/ObliviousOdin/loki/actions/runs/39529473862), at `8f86c784b08c01f099d86d0240a3d86faa21d8e8`, passed 16 of 20 jobs. Windows contracts and controlled installs passed; two dependency audits, a Python test-directory layout check and the verification gate failed. The layout correction has targeted local evidence, and the Nix dependency graph and browser component passed separate hosted checks. A complete required run at the final source remains pending; earlier passing scopes do not qualify later changes.

Alpha.2 is not published. The native staging and anonymous-download workflows have source/fixture evidence only; no alpha.2 native build, upload, downloaded installation or provider conversation is claimed. Alpha.1's measured results do not transfer to this candidate. See [verification](VERIFICATION.md#unpublished-alpha2-verification) for the implemented corrections and remaining gates.

The [verification guide](VERIFICATION.md) retains historical baseline diagnostics. [Production readiness](PRODUCTION-READINESS.md) defines stable promotion; [installation](INSTALL.md), [release notes](RELEASE-NOTES.md) and [maintenance](MAINTENANCE.md) explain the supported preview path. Source availability and passing scoped checks do not establish full functional parity.
