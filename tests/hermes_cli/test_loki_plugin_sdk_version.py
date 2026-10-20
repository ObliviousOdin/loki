"""Loki's own version must not disable compatibility with the retained Hermes SDK."""
import pytest

from hermes_cli.plugins_manifest import requires_hermes_error
from hermes_cli.version_info import _reset_version_info_cache, get_version_info
from loki_identity import VERSION


@pytest.mark.parametrize("spec", [">=0.19", ">=0.21", ">=0.22.2"])
def test_retained_sdk_plugins_remain_admissible(spec):
    _reset_version_info_cache()
    before = get_version_info()
    assert before.base_version == VERSION
    assert requires_hermes_error({"requires_hermes": spec}) is None
    assert get_version_info() == before


@pytest.mark.parametrize("spec", [">=0.23", ">=99", "<0.22"])
def test_incompatible_future_or_older_sdk_still_refused(spec):
    assert requires_hermes_error({"requires_hermes": spec}) is not None
