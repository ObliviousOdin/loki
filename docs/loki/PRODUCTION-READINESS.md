# Repository and stable-release policy

`main` is Loki's single long-lived integration branch. Release `v0.1.0-alpha.1` is an unsigned source preview; [delivery status](PREVIEW-STATUS.md) identifies the exact published source and measured scope. New commits on `main` require their own checks and do not inherit that release's qualification.

## Repository controls

Changes use short-lived branches and protected pull requests. The required `Loki verification` check is bound to GitHub Actions, must be current, and applies to administrators. Review conversations must be resolved. Force pushes and deletion of `main` are disabled. Merge commits preserve fork and contributor history; published tags and software/checksum assets are immutable.

The sole-maintainer approval requirement is zero. Code Owners route changes for attention without claiming an independent approval or allowing fabricated self-approval. Delete branches after landing their work, or after recording an exact-tip recovery archive and disposition for unmerged work. Preserve unrelated local branches and worktrees. See [maintenance](MAINTENANCE.md#branch-and-release-policy).

Private vulnerability reporting, dependency alerts, public secret scanning and secret push protection are enabled. Follow [SECURITY.md](../../SECURITY.md) for private reports. Review dependency alerts and update affected pins through PM/lockfile tooling and protected CI. Scheduled version-update PRs remain paused; automatic fixes and automatic merges are not enabled. Actions default to read-only permissions, and inherited publishing workflows remain guarded and disabled. The required verification includes a Linux amd64 image build and the real Docker suite, with skipped tests rejected. This uses a standard public runner without registry publication; other image architectures and the optional desktop-image variant require separate qualification. Existing spending limits stay unchanged.

## Evidence required before stable promotion

- **Security triage:** resolve or document evidence-based dispositions for dependency advisories and credential-scanning findings through the private reporting process. Current dependency remediation and retained-history credential-owner review are incomplete. Keep unresolved alerts open; do not infer safety from a development dependency label, fixture name or upstream origin.
- **Reliable checks:** establish and fix the cause of both observed intermittent failures: paused-mailbox receipt settlement and the Windows update-marker test. Retain failure/retry history and meaningful regression tests; a successful retry is not resolution.
- **Published installation:** repeat public-network installation, owned state/update paths, persistence and installed CLI/TUI startup at the final release candidate. The additional default-path macOS arm64 acceptance passed for the exact published preview, as recorded in [delivery status](PREVIEW-STATUS.md). Ordinary public-default Linux and Windows installation remains unqualified; the controlled three-OS installs remain separate evidence. Later commits do not inherit the preview's qualification.
- **Real integrations:** use dedicated Loki credentials for a real provider conversation and resume, plus actual messaging delivery for claimed adapters. Qualify OAuth, hosted services and optional capabilities before claiming them. Synthetic sessions and mocked adapters do not establish delivery.
- **Native distribution:** build the exact admitted release commit, retain required source/notices, and test downloaded installation, startup, persistence and update behavior on each claimed OS/architecture. Skipped native tests and cross-builds do not qualify that platform. Obtain and qualify owned signing/notarization and an authenticated update feed before enabling packaged automatic updates.
- **Release custody:** require protected CI on the final source, reviewed provenance and infrastructure boundaries, immutable software hashes, anonymous published-download verification and accurate installation instructions. Re-run affected checks for later changes; publish corrections under a new version.

Until these gates have evidence, retain preview labeling and the explicit limitations. [Verification](VERIFICATION.md) distinguishes inherited capability, historical diagnostics, tested behavior and externally configured services.
