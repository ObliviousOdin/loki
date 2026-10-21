# Loki 0.1.0-alpha.2 development candidate

This candidate uses Python `0.1.0a2` and JavaScript/tag `0.1.0-alpha.2`. It is not a published release or stable qualification. The published alpha.1 and its immutable software assets remain available below. The upstream baseline remains `18c525b669b6ea4ba62e6967d228af21d89aa9d3`; history, attribution and source companions are preserved.

The candidate patches Python HTTP/OAuth dependencies, Electron and renderer dependencies, and the independent documentation website graph. The website carries a private, source-preserving braces fork with iterative traversal and reproducible archive checks because the pinned upstream release lacks the traversal correction. Its maintained source, MIT license, provenance and behavior tests are in `vendor/braces`; an owned mitigation does not itself close advisory metadata.

The candidate also carries a narrow, source-preserving private `vendor/htmlparser2` fork. Its source, installed bytes, deterministic archive, license/provenance and existing public parser options have targeted verification and independent review. Full workspace checks remain required at the final candidate.

The mailbox correction re-reads committed settlement state before classifying a receipt; a real-SQLite regression reproduces the earlier race. Container fixes cover public command/environment handoff, privilege-drop compatibility and generated s6 gateway execution. The shell installer identifies Loki as an independent product. Test fixes address the actual HTTP task mock, Radix teardown, Windows output pressure and an acknowledged blocking pre-updater gate without weakening product assertions. These fixes do not prove the cause of every historical mailbox or Windows failure.

Windows update cancellation now retains native process handles and checks process completion as well as job accounting before reporting quiescence. An uncertain observation fails closed into the documented recovery path. The native regression keeps the original cancellation deadline and exercises both current descendants and a descendant that exited before cancellation; portable skips do not qualify that behavior.

For a new session with no resolved model, the gateway refuses creation before writing a session, route or frozen policy. The TUI preserves this structured refusal and offers its existing setup handoff. Explicit model selection and valid frozen-session retry remain supported. Existing invalid stored policies still fail the recovery guard; this correction does not migrate them or establish a real provider conversation.

Required CI adds the real Linux container suite and the complete default English website build, with automatic Python file retries disabled in every lane. Website regressions exercise the installed traversal fork, glob discovery and watcher behavior. Earlier failed and retried runs remain historical evidence; targeted tests and source reviews, including the full desktop UI run, do not qualify the combined final head. [PR #9](https://github.com/ObliviousOdin/loki/pull/9) still requires a fresh successful protected CI run before merge.

Manual delivery workflows check published default source installation on Linux, macOS and Windows, stage verified unsigned native assets to an explicitly selected owned draft, and independently verify anonymous published native downloads. Their source/fixture checks have passed; actual alpha.2 publication and native build/download/installed-product execution remain pending. Dedicated provider conversation/resume, messaging delivery, credential-owner dispositions and signing/update qualification remain separate gates. See [production readiness](PRODUCTION-READINESS.md) and the eventual release's exact-commit reports; do not inherit alpha.1 results for this candidate.

---

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

An intermittent paused-mailbox test on the PR head and an intermittent Windows update-marker test on the merged source passed existing retries. Neither historical failure has an established cause or fix at this published source. The additional lean public-network install into default macOS arm64 paths and installed CLI/TUI startup passed on October 20; the [measured report](https://github.com/ObliviousOdin/loki/releases/download/v0.1.0-alpha.1/LOKI-MACOS-SOURCE-VERIFICATION.json) retains scope and earlier acceptance-script failures. Real provider conversation/resume and messaging remain untested with dedicated credentials.

Choose a provider and model with `loki setup` before starting the TUI; a blank model can report `storage_unavailable`. Browser/computer-use, OAuth, hosted-service and wake-word behavior require their own configuration and acceptance. Native packages, signing/notarization, quarantined-download trust and native installation/update flows remain unqualified. Packaged automatic updates are disabled. Full functional parity is not established.

Stable promotion requires the evidence in [production readiness](PRODUCTION-READINESS.md), including fresh checks after the mailbox and Windows fixture corrections, real integration acceptance and qualified signing/update infrastructure for each claimed native platform. Future changes use protected `main`, new release versions and [history-preserving upstream integration](MAINTENANCE.md).
