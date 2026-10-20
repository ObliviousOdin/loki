"""Remove local compiler debug provenance from staged macOS Pilk wheels before sealing."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

_MACHO = {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce",
          b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}


def _symbols(path: Path) -> tuple[str, ...]:
    result = subprocess.run(["/usr/bin/nm", "-g", "-j", str(path)], check=True,
                            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    return tuple(sorted(line for line in result.stdout.splitlines() if line and not line.endswith(":")))


def _has_debug_symbols(path: Path) -> bool:
    result = subprocess.run(["/usr/bin/nm", "-a", "-p", str(path)], check=True,
                            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    # BSD nm marks Mach-O STAB/debug entries with '-', including N_SO/N_OSO.
    return any(len(fields := line.split(maxsplit=2)) > 2 and fields[1] == "-"
               for line in result.stdout.splitlines())


def _atomic_bytes(path: Path, data: bytes) -> None:
    """Replacing the staged inode also protects any reusable-cache hard link."""
    descriptor, name = tempfile.mkstemp(prefix=".loki-symbols-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        temporary.chmod(stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _record_bytes(original: bytes, name: str, data: bytes) -> bytes:
    rows = list(csv.reader(io.StringIO(original.decode("utf-8"))))
    matches = [row for row in rows if row and row[0] == name]
    if len(matches) != 1 or len(matches[0]) != 3:
        raise ValueError("staged Pilk wheel RECORD must describe its library exactly once")
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    matches[0][1:] = ["sha256=" + digest, str(len(data))]
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    return output.getvalue().encode("utf-8")


def _record_update(library: Path, data: bytes) -> tuple[Path, bytes]:
    site = library.parent.parent
    records = list(site.glob("pilk-*.dist-info/RECORD"))
    if (len(records) != 1 or records[0].is_symlink() or not records[0].is_file()
            or not records[0].resolve().is_relative_to(site.resolve())):
        raise ValueError("staged Pilk library must have exactly one regular wheel RECORD")
    record = records[0]
    return record, _record_bytes(record.read_bytes(), library.relative_to(site).as_posix(), data)


def _stripped_bytes(library: Path) -> bytes:
    """Use the platform linker tool; retain every global import/export symbol."""
    if not _has_debug_symbols(library):
        return library.read_bytes()
    descriptor, name = tempfile.mkstemp(prefix=".loki-symbols-", suffix=".so", dir=library.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        shutil.copyfile(library, temporary)
        subprocess.run(["/usr/bin/strip", "-S", str(temporary)], check=True,
                       capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
        # strip invalidates linker signatures. Seal the staged copy explicitly;
        # '-' is local ad hoc signing and performs no identity/keychain discovery.
        subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", "--timestamp=none",
                        "--identifier", "com.obliviousodin.loki.pilk", str(temporary)],
                       check=True, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
        subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(temporary)],
                       check=True, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
        data = temporary.read_bytes()
        if data != library.read_bytes() and _symbols(library) != _symbols(temporary):
            raise ValueError("stripping debug provenance changed Pilk's global symbols")
        return data
    finally:
        temporary.unlink(missing_ok=True)


def _strip_library(library: Path) -> bool:
    data = _stripped_bytes(library)
    if data == library.read_bytes():
        return False
    record, record_bytes = _record_update(library, data)
    _atomic_bytes(library, data)
    _atomic_bytes(record, record_bytes)
    return True


def _wheel_updates(archive: zipfile.ZipFile, directory: Path) -> dict[str, bytes]:
    updates = {}
    for info in archive.infolist():
        if (info.filename.startswith("pilk/_pilk") and info.filename.endswith(".so")
                and "/" not in info.filename.removeprefix("pilk/")):
            data = archive.read(info)
            if data[:4] in _MACHO:
                library = directory / "library.so"
                library.write_bytes(data)
                stripped = _stripped_bytes(library)
                if stripped != data:
                    updates[info.filename] = stripped
    if updates:
        records = [name for name in archive.namelist()
                   if name.startswith("pilk-") and name.endswith(".dist-info/RECORD") and name.count("/") == 1]
        if len(records) != 1:
            raise ValueError("cached Pilk wheel must have exactly one RECORD")
        record = archive.read(records[0])
        for name, data in updates.items():
            record = _record_bytes(record, name, data)
        updates[records[0]] = record
    return updates


def _strip_wheel(wheel: Path) -> bool:
    with tempfile.TemporaryDirectory(prefix=".loki-wheel-symbols-", dir=wheel.parent) as directory:
        with zipfile.ZipFile(wheel) as archive:
            updates = _wheel_updates(archive, Path(directory))
            if not updates:
                return False
            temporary = Path(directory) / "normalized.whl"
            with zipfile.ZipFile(temporary, "w") as target:
                for info in archive.infolist():
                    target.writestr(info, updates[info.filename] if info.filename in updates else archive.read(info))
                target.comment = archive.comment
        temporary.chmod(stat.S_IMODE(wheel.stat().st_mode))
        os.replace(temporary, wheel)
    return True


def strip_macho_debug_symbols(payload: Path) -> dict[str, int]:
    """Normalize only owned staging copies, including wheels kept for offline rebuilds.

    Run before payload hashes/admission and final app signing. Local ad hoc library
    seals preserve loadability, without claiming a trusted signing identity.
    No installed app or original PM cache
    belongs here. Other platforms and unrelated native dependencies are unchanged.
    """
    if sys.platform != "darwin":
        return {"libraries": 0, "wheels": 0}
    payload = Path(payload).resolve(strict=True)
    libraries = []
    for library in payload.rglob("pilk/_pilk*.so"):
        if library.is_symlink() or not library.resolve().is_relative_to(payload):
            raise ValueError("Pilk normalization requires a library contained in the staged payload")
        with library.open("rb") as stream:
            if stream.read(4) in _MACHO:
                libraries.append(library)
    wheels = [p for p in payload.rglob("*.whl") if p.name.partition("-")[0].lower() == "pilk"]
    if any(p.is_symlink() or not p.resolve().is_relative_to(payload) for p in wheels):
        raise ValueError("Pilk normalization requires a wheel contained in the staged payload")
    return {"libraries": sum(_strip_library(path) for path in libraries),
            "wheels": sum(_strip_wheel(path) for path in wheels)}
