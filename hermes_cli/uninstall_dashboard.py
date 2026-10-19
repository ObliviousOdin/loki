"""Ownership admission for destructive dashboard/serve LaunchAgent cleanup."""
from pathlib import Path


def dashboard_launchd_job_owned(label: str, argv: list[str], environment) -> bool:
    """Inventory may include Hermes; mutation needs Loki launch and declared home proof.

    A stopped job has no live PID/ledger witness. An absent or relative home cannot
    establish which install it will run on, so preserve that plist instead of guessing.
    """
    from hermes_cli.dashboard_procs import _backend_launch_kind, _profile_flag_value
    from hermes_cli.main_dashboard import _backend_service_home_owned, _foreign_backend_service
    from hermes_cli.profiles import normalize_profile_name, profile_root_for_env_home

    if _foreign_backend_service(label) or not isinstance(environment, dict):
        return False
    env = {key: value for key, value in environment.items() if isinstance(value, str)}
    if _backend_launch_kind(argv, env) in {"foreign", "unbound"}:
        return False
    home = env.get("HERMES_HOME" if env.get("__LOKI_ENV_BOUND") == "1" else "LOKI_HOME", "").strip()
    if not home or not Path(home).is_absolute():
        return False
    if (profile := _profile_flag_value(argv)) is not None:
        try:
            name = normalize_profile_name(profile)
        except ValueError:
            return False
        root = profile_root_for_env_home(home, Path(home))
        home = str(root if name == "default" else root / "profiles" / name)
    return _backend_service_home_owned(home)
