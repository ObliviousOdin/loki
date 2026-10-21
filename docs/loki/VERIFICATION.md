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

## Unpublished alpha.2 verification

[PR #9](https://github.com/ObliviousOdin/loki/pull/9) contains the following corrections. These are development-candidate results, not additions to alpha.1's measured release scope.

- **Mailbox settlement:** a two-connection real-SQLite regression reproduces settlement between the admission and result reads. Re-reading the terminal admission fixes the incorrect receipt classification while retaining failure, interruption and silence behavior. The historical failed runs did not capture enough receipt state to establish that this race caused each failure.
- **Process and lifecycle fixtures:** Windows handoff tests acknowledge the actual paused help process before creating the updater and capture concurrent claimant output in files. Portable controller tests prove explicit release and cancellation. HTTP drain fixtures bind the actual queued task; DOM teardown waits for unmount callbacks. Earlier behavior has meaningful failing regressions, followed by targeted passing cohorts. Native Windows assertions remain required on Windows; macOS skips do not qualify them.
- **Windows process completion:** an actual Windows diagnostic retained an unsignaled original process handle after the old helper had reported success with zero active job members. The candidate retains lifetime process handles and requires their completion together with final job accounting under the original deadline. Observation uncertainty refuses quiescence. New native probes cover current and already-exited descendants, and run alongside the existing installer workload. Fixture startup failures and earlier unsuccessful runs remain failure evidence; a later isolated pass does not qualify the combined candidate.
- **Unconfigured first session:** a real authority connection and temporary SQLite store reproduce a blank model creating a session and then failing restore. The correction refuses new creation before durable writes and routes the TUI's structured model refusal to setup. The explicit-model path and frozen-session retry remain separate regression contracts. These credential-free checks do not prove provider delivery.
- **Containers and website:** public command/environment binding and generated s6 execution have focused behavior regressions. The owned website traversal fork has upstream-output comparisons plus actual glob-discovery and watcher contracts. The real Linux Docker suite and complete default English website job remain required at the final source; focused checks do not replace them.
- **Image dependencies:** a fresh PM environment selected Pillow 13.0.0 and the local browser-harness metadata rebuild. All supplier implementation and asset bytes matched the admitted source; 204 tests passed with zero reported skips, failures or retries. Native image codecs and 99 generated icon outputs passed their checks. The PM snapshot now carries declared local dependency archives, with 17 passing snapshot contracts. This is macOS source/runtime evidence; actual browser automation, Docker installation and other hosts require their own checks. The unchanged certifi version still has an unresolved advisory.
- **Sealed dependency metadata:** an actual offline PM install reproduced a local source URL disclosing the build-machine path. Fresh sealed builds now remove that local URL and its RECORD row while retaining runtime bytes, licenses and remote provenance. The real-install contracts and adjacent PM cohort passed; unsealed installations retain their provenance. This does not establish native packaged privacy until the final artifact is built and inspected.
- **Delivery tooling:** source/native staging and published-download verifier fixtures pass exact-source, checksum, notice and refusal contracts. Native upload defaults off, targets only an explicitly selected owned draft, and never publishes or overwrites assets. Published native acceptance uses anonymous downloads and an independently accepted staging-proof hash. These checks have not executed an alpha.2 native build, upload, downloaded installation or real provider conversation.

The latest completed [combined diagnostic run](https://github.com/ObliviousOdin/loki/actions/runs/39515354374) passed 16 of 18 jobs, including all four Linux Python slices (65,216 passed, 963 skipped), the website and actual Linux container checks. Windows failed two new probe readiness preconditions, so its required verification gate failed. That run does not qualify the later fixture or first-session corrections: a fresh final-head run with zero automatic file retries remains required. Alpha.2 remains unpublished; security dispositions, ordinary published installation on every claimed host, real integrations, native trust/update behavior and signing still require their own evidence.

## Pristine baseline findings

On macOS arm64, upstream environment setup and all 12 `scripts/check` checks passed before customization. The pristine canonical Python run finished with 6,379 files: 62,973 tests passed, 192 failed and 1,755 were skipped. Another 13 files exited nonzero after passing assertions, and 16 reported collection/no-tests errors. This was not a green upstream baseline.

Every one of the 81 non-green files was replayed with the prepared pinned tool PATH and a distinct empty home. Those targeted replays passed 1,332 tests, with 33 persistent inherited failures, 53 skips and one collection error for the locally absent optional Fal SDK. This is targeted replay evidence, not a second full suite. `BASELINE-PYTHON-FINAL.json` records exact case IDs, categories and environment constraints in the release evidence.

Inherited cases include canonical `/var/tmp` versus `/private/var/tmp` snapshot paths, native macOS process-command inspection, and host/tool portability assumptions. Loki's real SQLite browse deadline regression also reproduced against the pinned source; Loki fixes the unguarded transaction-start error while retaining the original deadline and rollback assertions. Baseline failures do not excuse Loki CI failures or qualify an untested platform. Initial JS checks required the pinned Python/tool PATH and a canonical temp directory; corrected reruns retain their original logs.

## Historical fork diagnostics

Before the final release candidate, the first complete fork Python diagnostic recorded 6,431 files, 63,747 passed, 158 failed and 1,840 skipped, with ten icon-fixture DNS setup errors and one optional Fal SDK collection error separately recorded. Focused fixes do not turn that historical run green.

An earlier macOS Electron diagnostic recorded 384 files, 373 passed, two failed and nine skipped; 3,618 tests passed, two failed and 36 skipped. Both failed assertions also reproduced at the pinned upstream source: a Linux HUD cross-target warning and a remote installer-wrapper assertion after exec. These historical observations are superseded as current release status by the exact-source CI linked in [preview delivery status](PREVIEW-STATUS.md); they are retained as diagnostics, not a successful baseline or evidence for later changes.

Do not infer provider availability, cross-platform acceptance, signing, or publication from this document. The release notes and attached receipts record the final measured result.
