"""Explicit Loki target metadata for disposable source-update repositories/archives."""


def loki_source_files(version="1.0"):
    return {
        "loki.py": b"def main():\n    pass\n",
        "loki_identity.py": (b'PRODUCT_NAME = "Loki"\nCOMMAND = "loki"\n'
                             b'DISTRIBUTION = "obliviousodin-loki-agent"\n'
                             b'REPOSITORY = "ObliviousOdin/loki"\n'),
        "pyproject.toml": (f'[project]\nname="obliviousodin-loki-agent"\nversion="{version}"\n'
                           '[project.scripts]\nloki="loki:main"\n').encode(),
    }


def write_loki_source(root, version="1.0"):
    for name, data in loki_source_files(version).items():
        (root / name).write_bytes(data)


def archive_loki_source(archive, prefix="hermes-agent-main/", version="2.0"):
    for name, data in loki_source_files(version).items():
        archive.writestr(prefix + name, data)


def loki_git_batch(request):
    """Committed blob replies for explicitly positive fake Git transports."""
    files = loki_source_files()
    replies = []
    for item in request.decode("utf-8").splitlines():
        name = item.partition(":")[2]
        data = files.get(name)
        replies.append((b"0" * 40 + b" blob " + str(len(data)).encode() + b"\n" + data + b"\n")
                       if data is not None else item.encode() + b" missing\n")
    return b"".join(replies)
