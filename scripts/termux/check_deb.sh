#!/data/data/com.termux/files/usr/bin/bash
# Install and test the real package in a fresh, offline Termux rootfs.
set -euo pipefail
export PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
export PATH="$PREFIX/bin:$PATH"
mkdir -p "$PREFIX/tmp"
ctmp=/tmp  # no-tmp: ok — where build_deb.sh mounts the inputs inside this container
package_file="${1:-$ctmp/pkg.deb}"
package=obliviousodin-loki-agent
[ "$(dpkg-deb --field "$package_file" Package)" = "$package" ] || {
    printf 'Refusing to install a foreign package: %s\n' "$package_file" >&2
    exit 1
}
# Termux runs without root. The image already owns the writable prefix.
dpkg --force-not-root --force-script-chrootless --install "$package_file"
root="$PREFIX/lib/loki-agent"
export LD_LIBRARY_PATH="$root/tools/python$PREFIX/lib:$root/tools/node$PREFIX/lib:$root/tools/ffmpeg$PREFIX/lib:$root/runtime-libs/lib:$PREFIX/lib"
export PYTHONPATH="$root/app"
"$root/venv/bin/python" "$ctmp/validate_installed.py"
# Reinstall exercises maintainer-script idempotence without changing user state.
dpkg --force-not-root --force-script-chrootless --install "$package_file"
[ "$(readlink "$PREFIX/bin/loki")" = ../lib/loki-agent/bin/loki ]
printf 'DEB_INSTALL_AND_REINSTALL_OK\n'
