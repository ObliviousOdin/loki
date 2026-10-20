# Loki parity and verification

Parity target: Hermes `18c525b669b6ea4ba62e6967d228af21d89aa9d3`, not a moving branch. The Git merge ancestry and preserved source tree provide source provenance, not full functional parity.

The preview retains the runtime, tools, providers, memory, skills, scheduling, delegation, messaging adapters, terminal UI, dashboard, desktop, Docker and Nix sources. No feature was removed and no earlier product branch was imported. Credentials, service registrations, OAuth apps, trial entitlements and signing identities are external requirements.

Container desktop backends retain the upstream default image identifier, `nousresearch/hermes-sandbox:desktop`, as an external dependency. Anonymous registry manifest access was checked; the image's desktop/browser behavior was not qualified. The recorded Docker terminal smoke used a separate public Python image with networking disabled. Loki has not published a sandbox image, and no upstream registry publishing credentials are used. Configure an independently built image when an owned sandbox image is required.

Wake-word support retains the upstream `hey_hermes` model and its matching phrase; these are model identities, not a qualified "Hey Loki" activation model. Voice activation remains off by default. Custom wake-word models and the configurable Sherpa phrase remain available, but microphone detection and a Loki-specific wake word have not been qualified.

## Evidence gates

| Surface | Required evidence | Claim boundary |
|---|---|---|
| Python runtime | canonical upstream runner plus Loki regressions | A unit suite does not prove all real providers |
| CLI/source install | clean profile, help/version/config, startup, own paths | A native Python host is not a native packaged app |
| Sessions | cross-process write/reopen and resume tests | Synthetic persistence is not a real model conversation |
| Tools/gateway | real local tool and relevant adapter tests | Help/mocked adapters do not prove message delivery |
| Memory/skills/cron/delegation | unchanged upstream tests plus isolation | Configured cloud backends still need credentials |
| TUI/dashboard/desktop | workspace checks and production builds | A build is not installed-app UAT |
| Operating systems | host-native CI and actual install receipts | Skips and cross-builds are not qualification |
| Distribution | exact commit, checksums, download and install | Unsigned bytes are not signed stable artifacts |

The full machine-readable and human-readable receipts are retained in the preview's evidence assets when produced. Results must be updated from actual commands before release. CI's final `Loki verification` requires every active Loki job to succeed; skipped inherited workflows are never counted as evidence.

## Pristine baseline findings

On macOS arm64, upstream environment setup and all 12 `scripts/check` checks passed before customization. The pristine canonical Python run finished with 6,379 files: 62,973 tests passed, 192 failed and 1,755 were skipped. Another 13 files exited nonzero after passing assertions, and 16 reported collection/no-tests errors. This was not a green upstream baseline.

Every one of the 81 non-green files was replayed with the prepared pinned tool PATH and a distinct empty home. Those targeted replays passed 1,332 tests, with 33 persistent inherited failures, 53 skips and one collection error for the locally absent optional Fal SDK. This is targeted replay evidence, not a second full suite. `BASELINE-PYTHON-FINAL.json` records exact case IDs, categories and environment constraints in the release evidence.

Inherited cases include canonical `/var/tmp` versus `/private/var/tmp` snapshot paths, native macOS process-command inspection, and host/tool portability assumptions. Loki's real SQLite browse deadline regression also reproduced against the pinned source; Loki fixes the unguarded transaction-start error while retaining the original deadline and rollback assertions. Baseline failures do not excuse Loki CI failures or qualify an untested platform. Initial JS checks required the pinned Python/tool PATH and a canonical temp directory; corrected reruns retain their original logs.

## Historical fork diagnostics

Before the final release candidate, the first complete fork Python diagnostic recorded 6,431 files, 63,747 passed, 158 failed and 1,840 skipped, with ten icon-fixture DNS setup errors and one optional Fal SDK collection error separately recorded. Focused fixes do not turn that historical run green.

An earlier macOS Electron diagnostic recorded 384 files, 373 passed, two failed and nine skipped; 3,618 tests passed, two failed and 36 skipped. Both failed assertions also reproduced at the pinned upstream source: a Linux HUD cross-target warning and a remote installer-wrapper assertion after exec. These historical observations are superseded as current release status by the exact-source CI linked in [preview delivery status](PREVIEW-STATUS.md); they are retained as diagnostics, not a successful baseline or evidence for later changes.

Do not infer provider availability, cross-platform acceptance, signing, or publication from this document. The release notes and attached receipts record the final measured result.
