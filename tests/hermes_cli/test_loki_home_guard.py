"""Sandbox declarations must retain real Loki, Hermes and custom-home guards."""

from pathlib import Path

import pytest

from tests import conftest as suite_conftest
from tests.home_io_guard import HomeIOGuard


def _homes(tmp_path, monkeypatch):
    user = tmp_path / "operator"
    appdata = tmp_path / "appdata"
    defaults = [user / ".loki", user / ".hermes", appdata / "loki", appdata / "hermes"]
    for home in defaults:
        home.mkdir(parents=True)
        (home / "canary").write_bytes(b"Operator state; preserve exact bytes.\n")
    monkeypatch.setattr(Path, "home", lambda: user)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "test-session"))
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))
    monkeypatch.setattr(suite_conftest, "_PRE_SANDBOX_HERMES_HOME", "")
    monkeypatch.delenv("HERMES_TEST_SANDBOX_HOME", raising=False)
    return defaults


def _assert_canaries_guarded(roots, homes, monkeypatch):
    targets = [home / "canary" for home in homes]
    original = {target: target.read_bytes() for target in targets}
    with monkeypatch.context() as patcher:
        HomeIOGuard(lambda: roots).install(patcher)
        for target in targets:
            with pytest.raises(AssertionError, match="REAL hermes home"):
                target.read_bytes()
            with pytest.raises(AssertionError, match="REAL hermes home"):
                target.write_bytes(b"Clobber must be refused.")
            with pytest.raises(AssertionError, match="REAL hermes home"):
                target.unlink()
    assert {target: target.read_bytes() for target in targets} == original


def test_both_loki_and_hermes_defaults_remain_guarded(tmp_path, monkeypatch):
    homes = _homes(tmp_path, monkeypatch)

    roots = suite_conftest._capture_real_hermes_root()

    _assert_canaries_guarded(roots, homes, monkeypatch)


def test_custom_operator_home_is_guarded_alongside_defaults(tmp_path, monkeypatch):
    homes = _homes(tmp_path, monkeypatch)
    custom = tmp_path / "custom operator state"
    custom.mkdir()
    (custom / "canary").write_bytes(b"Custom operator state must survive.\n")
    monkeypatch.setattr(suite_conftest, "_PRE_SANDBOX_HERMES_HOME", str(custom))

    roots = suite_conftest._capture_real_hermes_root()

    _assert_canaries_guarded(roots, [*homes, custom], monkeypatch)


def test_owned_session_sandbox_does_not_exempt_operator_defaults(tmp_path, monkeypatch):
    homes = _homes(tmp_path, monkeypatch)
    sandbox = tmp_path / "runner" / "loki-home"
    sandbox.mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(suite_conftest, "_PRE_SANDBOX_HERMES_HOME", str(sandbox))
    monkeypatch.setenv("HERMES_TEST_SANDBOX_HOME", str(sandbox))

    roots = suite_conftest._capture_real_hermes_root()

    with monkeypatch.context() as patcher:
        HomeIOGuard(lambda: roots).install(patcher)
        cache = sandbox / "cache" / "generated"
        cache.mkdir(parents=True)
        (cache / "image.png").write_bytes(b"Owned generated-media fixture.")
        assert (cache / "image.png").read_bytes() == b"Owned generated-media fixture."
    _assert_canaries_guarded(roots, homes, monkeypatch)


@pytest.mark.parametrize("index", [0, 2], ids=["loki-home", "loki-localappdata"])
def test_marker_cannot_exempt_a_native_loki_default(tmp_path, monkeypatch, index):
    homes = _homes(tmp_path, monkeypatch)
    monkeypatch.setattr(suite_conftest, "_PRE_SANDBOX_HERMES_HOME", str(homes[index]))
    monkeypatch.setenv("HERMES_TEST_SANDBOX_HOME", str(homes[index]))

    roots = suite_conftest._capture_real_hermes_root()

    _assert_canaries_guarded(roots, homes, monkeypatch)


def test_unrelated_marker_cannot_exempt_custom_operator_state(tmp_path, monkeypatch):
    homes = _homes(tmp_path, monkeypatch)
    custom = tmp_path / "custom operator state"
    custom.mkdir()
    (custom / "canary").write_bytes(b"Custom operator state must survive.\n")
    monkeypatch.setattr(suite_conftest, "_PRE_SANDBOX_HERMES_HOME", str(custom))
    monkeypatch.setenv("HERMES_TEST_SANDBOX_HOME", str(tmp_path / "unrelated sandbox"))

    roots = suite_conftest._capture_real_hermes_root()

    _assert_canaries_guarded(roots, [*homes, custom], monkeypatch)


@pytest.mark.parametrize("index", [0, 2], ids=["unresolved-loki-home", "unresolved-loki-localappdata"])
def test_one_unresolvable_root_keeps_other_operator_homes_guarded(tmp_path, monkeypatch, index):
    homes = _homes(tmp_path, monkeypatch)
    custom = tmp_path / "custom operator state"
    custom.mkdir()
    (custom / "canary").write_bytes(b"Custom operator state must survive.\n")
    monkeypatch.setattr(suite_conftest, "_PRE_SANDBOX_HERMES_HOME", str(custom))
    original_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        if path == homes[index]:
            raise OSError("Disposable fixture simulates an unresolvable Loki root")
        return original_resolve(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "resolve", resolve)
        roots = suite_conftest._capture_real_hermes_root()

    _assert_canaries_guarded(roots, [home for home in homes if home != homes[index]] + [custom], monkeypatch)
