# Browser harness source archive

Read `FORK.md` and `UPSTREAM.json` before editing this directory. The official and
private sdists contain the complete readable MIT supplier source. Keep the
supplier implementation, assets, entry points and license byte-identical; do not
refactor supplier code to satisfy Loki's core conventions.

The only admitted differences in private `0.1.13+loki.1` are its package version
and Pillow 13.0.0 requirement in four metadata files. `PATCH.diff` must match those
seven hunks exactly. Changed source or archive bytes require a new private version,
official provenance review and qualification; never restamp an existing archive.
Do not publish this local package to a registry.

`archive.py --check` verifies official source, allowed patch, deterministic private
archive, root pin, relative source mapping and lock digest. After an approved
metadata change, use the normal PM lock workflow. Local source archives have no
PyPI release timestamp; the admitted supplier and registry dependencies must still
meet the release-age policy. Keep the global policy unchanged.

Run `scripts/run_tests.sh tests/vendor/test_browser_harness_archive.py` for the
artifact boundary. Actual Pillow and browser consumers need a fresh PM-owned
environment with the new bytes. Preserve Loki's default telemetry-off child
setting and all browser features. Never use live user browser state for tests.
