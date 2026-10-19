"""Directories where tools install outside PATH, grouped by the ecosystem that owns them.

Every table in Hermes lives here. A directory literal outside this module fails the ratchet in
`tests/test_managed_runtime_resolution.py`. Each table is empty on an OS where the ecosystem
does not install there, so callers compose tables without OS branches.
"""

from __future__ import annotations

import sys

_POSIX = sys.platform != "win32"
_WIN = sys.platform == "win32"


def homebrew_dirs() -> tuple[str, ...]:
    return ("/opt/homebrew/bin", "/usr/local/bin") if sys.platform == "darwin" else ()


def user_local_bin() -> tuple[str, ...]:
    return ("~/.local/bin",) if _POSIX else ("%USERPROFILE%/.local/bin",)


def rust_tool_dirs() -> tuple[str, ...]:
    return ("~/.cargo/bin",) if _POSIX else ("%USERPROFILE%/.cargo/bin",)


def node_tool_dirs() -> tuple[str, ...]:
    return ("~/.npm-global/bin", "~/.bun/bin", "~/.volta/bin") if _POSIX else ("%APPDATA%/npm", "%USERPROFILE%/.bun/bin", "%LOCALAPPDATA%/Volta/bin")


def hermes_vendored_dirs() -> tuple[str, ...]:
    return ("~/.loki/bin",) if _POSIX else ("%LOCALAPPDATA%/loki/bin",)


def machine_marker_files() -> tuple[str, ...]:
    """Where Hermes records that this OS user has used it. No Hermes data-dir setting moves these.
    The first entry is the one written; the rest are read too (Windows: MSIX builds that ran with
    filesystem virtualisation wrote under the package's LocalCache)."""
    if _WIN:
        return ("%LOCALAPPDATA%/Loki/.machine",
                "%LOCALAPPDATA%/Packages/ObliviousOdin.Loki*_*/LocalCache/Local/Loki/.machine")
    if sys.platform == "darwin":
        return ("~/Library/Application Support/Loki/.machine",)
    return ("$XDG_STATE_HOME/loki/.machine", "~/.local/state/loki/.machine")


def hermes_home_globs() -> tuple[str, ...]:
    """Every place a Hermes data root can sit by default: suffixed channel roots, the legacy Windows
    root, and the per-package roots of MSIX builds that ran with filesystem virtualisation."""
    if _WIN:
        return ("%LOCALAPPDATA%/loki*", "%USERPROFILE%/.loki",
                "%LOCALAPPDATA%/Packages/ObliviousOdin.Loki*_*/LocalCache/Local/loki*")
    return ("~/.loki*",)


def gateway_service_definition_globs() -> tuple[str, ...]:
    """This OS user's gateway service definitions, each naming the HERMES_HOME it serves."""
    if _WIN:
        return ("%APPDATA%/Microsoft/Windows/Start Menu/Programs/Startup/Loki_Gateway*",)
    if sys.platform == "darwin":
        return ("~/Library/LaunchAgents/com.obliviousodin.loki.gateway*.plist",)
    return ("$XDG_CONFIG_HOME/systemd/user/loki-gateway*.service", "~/.config/systemd/user/loki-gateway*.service")


def system_gateway_service_definition_globs() -> tuple[str, ...]:
    """Machine-wide gateway services. Each runs as the account its ``User=`` names (root when none)."""
    return ("/etc/systemd/system/loki-gateway*.service",) if _POSIX and sys.platform != "darwin" else ()


def mac_privacy_protected_dirs() -> tuple[str, ...]:
    """Folders macOS guards with a permission prompt (TCC); opening anything inside raises it."""
    if sys.platform != "darwin":
        return ()
    return ("~/Documents", "~/Desktop", "~/Downloads", "~/Library/Mobile Documents")  # windows-footgun: ok — macOS only


def windows_user_program_dirs() -> tuple[str, ...]:
    if not _WIN:
        return ()
    return (
        "%LOCALAPPDATA%/Programs",
        "%USERPROFILE%/scoop/shims",
        "%LOCALAPPDATA%/Microsoft/WinGet/Links",
    )


def mac_application_dirs() -> tuple[str, ...]:
    return ("/Applications", "~/Applications") if sys.platform == "darwin" else ()


def flatpak_export_dirs() -> tuple[str, ...]:
    """Where flatpak links each installed app's launcher, named by its app id (system, then per-user)."""
    return ("/var/lib/flatpak/exports/bin", "~/.local/share/flatpak/exports/bin") if sys.platform.startswith("linux") else ()


def snap_bin_dirs() -> tuple[str, ...]:
    return ("/snap/bin",) if sys.platform.startswith("linux") else ()
