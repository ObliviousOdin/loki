# Loki infrastructure boundary

Every inherited workflow job is guarded by exact repository ownership
`NousResearch/hermes-agent`. They are retained as upstream reference and cannot
execute in `ObliviousOdin/loki`, including reusable workflows and jobs with
`always()`. Loki CI and preview publication have their own workflows. A skipped
inherited job is never Loki qualification evidence.

The first push contains these guards. The new private repository has no inherited
secrets, variables, environments, GitHub Apps, or signing configuration. No Fabric
membership, Google Cloud, website, or release provider is connected. CI uses only
standard GitHub-hosted runners within the account's existing budget; no larger
runners or spending-limit changes are authorized.

Preview publication is restricted to this repository's GitHub Releases. No PyPI,
npm, DockerHub, R2, Microsoft Store, Vercel, or upstream GitHub destination is
published. Unsigned artifacts must be labeled unsigned. Stable publication needs
separately owned credentials and native qualification.

On upstream integration, review new or changed workflows before they become
active. Never remove these guards while copying an upstream workflow. Review
runtime update feeds, OAuth clients, auto-adopted credentials, telemetry and
installer URLs in the same change.
