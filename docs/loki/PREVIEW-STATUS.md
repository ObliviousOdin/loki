# Preview delivery status

Recorded October 19, 2026. Loki is preparing its first public preview. No preview tag, published release, or completed protected merge is claimed. Public-release preparation must preserve required licenses and upstream history while excluding private project audit material from every published ref and artifact.

## Publication gates

Release qualification requires the protected CI gate on the final pull-request head. Loki verification uses standard GitHub-hosted runners. Public-release preparation reviews the exact source, reachable history, repository metadata, workflow logs and artifacts before publication.

Required `Loki verification` protection must remain enforced for administrators. No bypass, fabricated approval or local replacement status is permitted. Every active Loki job must actually succeed on the final PR head before normal merge, merged-commit release builds and publication. The workflow includes the full Linux Python suite, workspace checks/builds, complete desktop UI shards, Electron and packaged validation, plus source installations and applicable native-host tests on Linux, macOS and Windows. A skipped native test does not qualify a platform.

## Evidence and its limits

[Verification](VERIFICATION.md) defines parity against the pinned upstream source. Source availability does not establish full functional parity. Raw local logs remain private; only explicitly sanitized summaries, hashes and provenance may be distributed. Each distributed receipt must identify the exact source, environment, outcome and skips. Overlapping focused test counts must not be summed into a unique passing total.

The pristine upstream macOS arm64 Python baseline was non-green: 6,379 files, 62,973 passed, 192 failed and 1,755 skipped, with additional nonzero/collection outcomes separately recorded. The complete first fork diagnostic finished with 6,431 files, 63,747 passed, 158 failed and 1,840 skipped; ten icon-fixture DNS setup errors and one optional Fal SDK collection error were separately recorded. Subsequent focused fixes do not turn that historical run green. A final candidate requires its own receipts and cause-based failure disposition.

The complete desktop UI diagnostic passed 11,259 tests across 1,309 files, with zero failures or skips. Later changes to relevant UI inputs require new verification. The complete Electron diagnostic remained failed: 384 files, 373 passed, two failed and nine skipped; 3,618 tests passed, two failed and 36 skipped. Both failed assertions reproduced at the pinned upstream source on native macOS: a Linux HUD cross-target warning and a remote installer-wrapper assertion after exec. These observations do not excuse a failed required CI job.

Earlier clean source installation checks covered actual macOS arm64 and a Linux x86-64 CI candidate: help/version, configuration, a real terminal tool, cross-process synthetic session persistence and foreign-state isolation. Gateway, Docker, TUI and dashboard checks have separate receipts. None of these results automatically qualifies a later source tree or every external integration.

All earlier native candidates are superseded and must not be distributed. The corrected candidate needs a fresh build, immutable archive hashes, exact source stamp, complete third-party notices, installed deep/strict seal, version/help, owned paths, local tool execution and native quit/restart persistence. Temporary local extraction is not a published-download test. The current native preview target is an unsigned macOS arm64 ZIP.

Classic CLI first-run startup reached setup; declining setup exited with the expected status 1. A model-configured modern TUI started with 20 tools and 57 skills and exited with status 0 without any provider request. Starting the TUI before selecting a model can report `storage_unavailable`; complete setup first. The same blank-model policy reproduced at the pinned upstream source, and no policy validation was relaxed.

Actual provider conversation and resume acceptance require a separately configured provider credential. Existing application credentials are not adopted. Provider, messaging, OAuth, hosted-service, wake-word and computer-use acceptance require their own real evidence. Windows native desktop, Linux native desktop, macOS Intel, Android/Termux and Nix execution remain unqualified where no native receipt exists.

No Developer ID signature, notarization, Windows signing, Store acceptance or quarantined-download acceptance is claimed. Local ad hoc sealing proves integrity only. Packaged automatic updates remain disabled until an owned authenticated feed and trusted signing are qualified.

See [release notes](RELEASE-NOTES.md), [installation](INSTALL.md) and [maintenance](MAINTENANCE.md). Published-download verification and a real preview-release URL are required before claiming publication.
