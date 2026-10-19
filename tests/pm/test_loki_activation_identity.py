"""Source activation binds its home before selecting any installed dependency store."""

import os


def test_activation_cannot_borrow_an_ambient_hermes_store(tmp_path, monkeypatch):
    from pm import environments, install, registry, testenv

    env = {"HOME": str(tmp_path), "HERMES_HOME": str(tmp_path / "foreign"),
           "HERMES_RUNTIME_DIR": str(tmp_path / "foreign-tools"), "PATH": "/bin"}
    monkeypatch.setattr(os, "environ", env)
    observed = []

    def compose(*_packages):
        observed.append(dict(os.environ))
        return dict(os.environ)

    monkeypatch.setattr(install, "env_for", compose)
    monkeypatch.setattr(registry, "all_packages", list)
    monkeypatch.setattr(environments, "committed_venv", lambda _root: None)
    monkeypatch.setattr(testenv, "testenv_python", lambda _root: None)
    activation = environments.activation_environment(tmp_path / "checkout")
    assert observed[0]["HERMES_HOME"].endswith("loki")
    assert "HERMES_RUNTIME_DIR" not in observed[0]
    assert activation["LOKI_HOME"] == activation["HERMES_HOME"]
    assert activation["__LOKI_ENV_BOUND"] == "1"
