#!/data/data/com.termux/files/usr/bin/bash
# Verify the signed repository with the same non-root APT used on a phone.
set -euo pipefail
export PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
export PATH="$PREFIX/bin:$PATH"
suite="${1:?APT suite required}"
expected="${2:?expected package version required}"
repository="${3:-file:/apt}"
previous_deb="${4:-/previous.deb}"
package=obliviousodin-loki-agent
if [ -f "$previous_deb" ] && [ "$(dpkg-deb --field "$previous_deb" Package)" != "$package" ]; then
    printf 'Refusing to install a foreign package: %s\n' "$previous_deb" >&2
    exit 1
fi
ctmp=/tmp  # no-tmp: ok — where the caller mounts validate_installed.py inside this container
mkdir -p "$PREFIX/tmp"
work="$(mktemp -d "$PREFIX/tmp/loki-apt-proof.XXXXXX")"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/lists/partial" "$work/archives/partial"
printf 'deb [signed-by=/apt/key.asc by-hash=force] %s %s main\n' "$repository" "$suite" > "$work/sources.list"
apt_options=(
    -o "Dir::Etc::sourcelist=$work/sources.list"
    -o "Dir::Etc::sourceparts=-"
    -o "Dir::State::lists=$work/lists"
    -o "Dir::Cache::archives=$work/archives"
    -o "DPkg::Options::=--force-not-root"
    -o "DPkg::Options::=--force-script-chrootless"
)
mkdir -p "$work/state"
printf 'user data survives package replacement\n' > "$work/state/sentinel"
export LOKI_HOME="$work/state"
if [ -f "$previous_deb" ]; then
    dpkg --force-not-root --force-script-chrootless --install "$previous_deb"
    previous="$(dpkg-query -W -f='${Version}' "$package")"
    dpkg --compare-versions "$expected" gt "$previous"
fi
apt-get "${apt_options[@]}" update
apt-get "${apt_options[@]}" --yes install "$package"
actual="$(dpkg-query -W -f='${Version}' "$package")"
[ "$actual" = "$expected" ]
[ "$(cat "$work/state/sentinel")" = 'user data survives package replacement' ]
root="$PREFIX/lib/loki-agent"
export LD_LIBRARY_PATH="$root/tools/python$PREFIX/lib:$root/tools/node$PREFIX/lib:$root/tools/ffmpeg$PREFIX/lib:$root/runtime-libs/lib:$PREFIX/lib"
export PYTHONPATH="$root/app"
"$root/venv/bin/python" "$ctmp/validate_installed.py"
printf 'SIGNED_APT_INSTALL_OK %s\n' "$actual"
if [ -f "$previous_deb" ]; then
    printf 'SIGNED_APT_UPGRADE_OK %s -> %s\n' "$previous" "$actual"
fi
