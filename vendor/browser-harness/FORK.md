# Loki browser-harness package

This is a local rebuild of Browser Use's MIT-licensed `browser-harness` 0.1.13.
Loki needs Pillow 13.0.0 for its published image-decoder security fixes, but the
latest upstream harness pins Pillow 12.3.0 exactly. This rebuild keeps every
browser implementation file, asset, entry point and license byte unchanged.

The private version is `0.1.13+loki.1`. Four packaging metadata files change only
the version and Pillow requirement. The remaining dependency requirements stay
unchanged. `UPSTREAM.json` records the official PyPI source archive and every
supplier file digest. Do not publish this package to PyPI.

Both source archives contain all 28 readable supplier files. The original archive
and seven-hunk `PATCH.diff` reproduce the private sdist offline, retaining the MIT
license and copyright. `archive.py --check` verifies every original member, the
four allowed metadata changes, deterministic private archive bytes, and the root
manifest and lock binding. `archive.py --write` creates a missing archive without
overwriting an existing artifact. Runtime changes need a new private version and
review. Supplier Python modules are not imported from Loki's core source tree.

The supplier's telemetry code is unchanged. Loki's browser launcher defaults its
`ANONYMIZED_TELEMETRY` child setting to `false`; the source rebuild does not opt in
to a cloud service, telemetry destination, or provider account.

This metadata change requires actual Pillow 13 and browser consumer tests. It
does not qualify native browsers or external services. Future updates should
prefer an aged upstream release that admits the patched Pillow dependency;
remove this local source mapping once that release passes the same checks.
