# Loki infrastructure boundary

Every inherited workflow job is guarded by exact repository ownership
`NousResearch/hermes-agent`. They are retained as upstream reference and cannot
execute in `ObliviousOdin/loki`, including reusable workflows and jobs with
`always()`. Loki CI and manual preview packaging have their own workflows. A skipped
inherited job is never Loki qualification evidence.

These guards were present before the first push. `ObliviousOdin/loki` is public;
the separate archive remains private. Inherited credentials, GitHub Apps, cloud
memberships, website deployments and signing providers are not connected. CI
uses standard GitHub-hosted runners within the existing budget; no larger
runners or spending-limit changes are authorized. The default Actions token is
read-only and cannot approve pull requests.

Protected `main` requires a pull request, current `Loki verification` from the
GitHub Actions application, and resolved conversations, including for
administrators. Merge commits preserve source history. Code ownership routes
review; it does not claim a mandatory independent approval when the project has
one maintainer. See [repository and release policy](../docs/loki/PRODUCTION-READINESS.md).

Private vulnerability reporting, dependency alerts, public secret scanning and
secret push protection are enabled. Dependency fixes are reviewed through the
pinned PM/lockfile workflow; scheduled version-update PRs remain paused. These
settings do not establish a completed vulnerability audit or product acceptance.

Preview publication is restricted to this repository's GitHub Releases. No PyPI,
npm, DockerHub, R2, Microsoft Store, Vercel, or upstream GitHub destination is
published. Unsigned artifacts must be labeled unsigned. Stable publication needs
separately owned credentials and native qualification.

On upstream integration, review new or changed workflows before they become
active. Never remove these guards while copying an upstream workflow. Review
runtime update feeds, OAuth clients, auto-adopted credentials, telemetry and
installer URLs in the same change.
