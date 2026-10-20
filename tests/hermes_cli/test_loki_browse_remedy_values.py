"""Browse recovery copy retains explicit names, homes and schema details."""
from pathlib import Path

from hermes_state_reconcile import _owner_remedy, _repair_command


def test_browse_remedies_preserve_hermes_named_profiles_and_custom_homes(tmp_path, monkeypatch):
    named = tmp_path / "profiles" / "hermes-profile"
    custom = tmp_path / "Hermes-custom"
    default = tmp_path / "default"
    labels = {named: "hermes-profile", default: "default"}
    monkeypatch.setattr("gateway.status._profile_label_for_home", lambda home: labels.get(Path(home)))
    assert _repair_command(named) == "loki -p hermes-profile sessions repair"
    assert _owner_remedy(named) == ("hermes-profile", "loki -p hermes-profile gateway restart")
    assert _repair_command(default) == "loki sessions repair"
    unknown = _repair_command(custom)
    assert unknown.startswith("LOKI_HOME=") and str(custom) in unknown
    assert unknown.endswith(" loki sessions repair")
    assert _owner_remedy(custom) == (str(custom), "loki gateway restart")
