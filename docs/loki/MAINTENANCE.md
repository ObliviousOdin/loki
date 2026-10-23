# Maintaining Loki

`origin` is the Loki repository. `upstream` is `https://github.com/NousResearch/hermes-agent.git`, with its push URL disabled locally. The full pinned upstream history is preserved, and `docs/loki/UPSTREAM.json` identifies the admitted baseline. Do not push upstream tags wholesale as Loki releases.

## Branch and release policy

`main` is the single long-lived integration branch. Start short-lived `codex/` branches from current `main`; do not add a parallel `core` branch. Rebase a change onto current `main` before its final checks and merge it through a protected pull request using a merge commit. Required `Loki verification` is bound to GitHub Actions, must be current, and applies to administrators. Resolve review conversations before merging. With one maintainer, the required human approval count is zero; Code Owners route attention rather than implying an independent approval.

Delete a PR branch only after its work has landed or its exact tip has a recorded recovery archive and disposition. Keep unmerged work and unrelated local worktrees intact. GitHub automatically deletes future merged PR branches. Published version tags, software assets and their checksum manifests are immutable; corrections use a new version. Development on `main` does not change the exact commit qualified by an existing release.

The active release-tag ruleset blocks updates and deletion of `v*` tags without bypass actors. It permits new version tags; it does not attest to artifact signing or platform qualification.

Repository controls and product release acceptance are separate. [Production readiness](PRODUCTION-READINESS.md) records the stable-release gates; [preview status](PREVIEW-STATUS.md) identifies the published source and its measured scope.

## Incorporating upstream changes

Owned dependency rebuilds live under `vendor/` with their source, license, provenance, reviewable patch and deterministic archive guard. The browser harness keeps its complete official source archive and changes only package-version and Pillow requirement metadata; its browser implementation is unchanged. Prefer a qualified upstream release that admits the fixed Pillow version, then remove the local source mapping. Until then, preserve both source archives in Git, source releases and Docker build inputs, update the root pin and lock through PM, and run archive, snapshot and actual consumer checks with a fresh environment. Never restamp an existing private archive version.

At each release or dependency change, review official advisories for both the supplier baseline and private version of each local fork (`braces`, `htmlparser2`, `browser-harness`). Registry audits may omit a local archive or classify its private version differently. Correlate affected code with the retained supplier hashes, reviewed patch and behavior tests, and record the evidence and limitations. Audit zero does not close a supplier advisory, and an owned mitigation does not update external advisory metadata. Never change a version merely to evade a finding.

The optional Honcho compatibility provider lives under `optional-plugins/honcho`, with its upstream source commit, original file hashes and license in that directory. It stays optional and installs through the normal catalog path from this repository. For an update, compare the exact upstream plugin revision, preserve notices, and reapply the small namespace/configuration/OAuth changes. Run the owned-home, foreign-canary, profile-rename and normal installer tests. Commit the provider first, then pin the catalog entry to that actual project commit; an upstream catalog or cache must never replace this project-owned pin.

Source update admission reads the target identity and packaging declarations as data without executing target code. Preserve the literal product, command, distribution and repository declarations in `loki_identity.py`, the `loki.py` main entry point, and the `loki:main` package script. Future product versions and upstream baseline SHAs may change without weakening this ownership check. Run both Git and archive update tests, including refusal before stash/rescue or overlay, when changing these contracts.

For an update:

1. Fetch upstream `main` without tags: `git fetch --no-tags upstream main`. Inspect its release notes, license/notices and source changes before selecting an exact SHA. Record that source's `get_version_info().base_version` as `sdk_base_version` in `UPSTREAM.json` and `UPSTREAM_SDK_VERSION` in `loki_identity.py`; plugin `requires_hermes` gates use this inherited SDK version while Loki keeps its own release sequence.
2. Create an isolated integration branch from current Loki `main`. Merge the selected upstream commit, preserving history. Resolve branding and environment boundaries around the small Loki identity modules; keep engine module/protocol names compatible.
3. Review every incoming workflow, installer, update URL, OAuth client, telemetry default and external publication destination. Retain upstream ownership guards and do not activate upstream jobs or paid runner labels. Review package/application naming collisions before adding a new public identity.
4. Run the pristine upstream baseline and Loki tests separately. Record inherited failures. Run all blocking lint, JS checks/builds, Linux Python tests and applicable native installation tests. Test a real provider and messaging flow with explicitly configured credentials before claiming those integrations.
5. Update provenance, parity evidence, third-party notices and Loki release notes. Increment Loki's own version sequence independently of Hermes. Open a PR; merge only after required `Loki verification` passes on the current head and conversations are resolved. No administrator bypass, fake review approval or spending increase.
6. Build exact-commit preview artifacts, verify checksums, download them from the published release and repeat installation. Stable promotion requires owned signing/notarization and native acceptance; a skipped native test is not qualification.

The inherited 56 workflows are retained as reference, guarded in source against execution in Loki, and disabled in GitHub. Loki has its own CI. No inherited GitHub Apps, cloud memberships, site deployments, R2 stores, release channels, signing identities or credentials are transferred.

Preview workflow builds use standard hosted runners and leave optional CI artifact retention off by default. Retention requires available storage within the existing budget; never increase spending to retrieve a preview. Publish verified source and native binaries as this project's release assets after protected merge, then download and install them for acceptance. Release assets and temporary Actions artifacts are separate distribution paths.
