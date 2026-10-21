"""Declared core dependency archives must survive PM's isolated build snapshot."""

import io
import json
import tarfile

import pytest

from pm.package import InstallError
from pm.workspace import _generate_pyproject


def write_project(source, archive_path, *, packages=('fixture_core',)):
    source.mkdir()
    (source / 'pyproject.toml').write_text(
        '[project]\nname = "snapshot-fixture"\nversion = "1.0.0"\n'
        '[tool.setuptools.packages.find]\ninclude = ' + json.dumps(list(packages)) + '\n'
        '[tool.uv.sources]\nfixture-dep = { path = ' + json.dumps(archive_path) + ' }\n',
        encoding='utf-8',
    )


def test_local_source_archive_survives_isolated_core_snapshot(tmp_path):
    source = tmp_path / 'source'
    relative = 'vendor/Dependency With Spaces.tar.gz'
    write_project(source, relative)
    archive = source / relative
    archive.parent.mkdir()
    with tarfile.open(archive, 'w:gz') as bundle:
        content = b'[project]\nname = "fixture-dep"\nversion = "1.0.0"\n'
        member = tarfile.TarInfo('fixture_dep-1.0.0/pyproject.toml')
        member.size = len(content)
        bundle.addfile(member, io.BytesIO(content))
    original = archive.read_bytes()
    target = tmp_path / 'owned generation'

    _generate_pyproject([], target, source=source)

    assert (target / relative).read_bytes() == original
    assert archive.read_bytes() == original
    assert not (target / relative).is_symlink()


@pytest.mark.parametrize('absolute', [False, True])
def test_local_archive_cannot_escape_the_core_source(tmp_path, absolute):
    source = tmp_path / 'source'
    outside = tmp_path / 'outside.tar.gz'
    outside.write_bytes(b'foreign archive must not be copied')
    declared = str(outside) if absolute else '../outside.tar.gz'
    write_project(source, declared)
    target = tmp_path / 'owned generation'

    with pytest.raises(InstallError, match='local dependency archive'):
        _generate_pyproject([], target, source=source)

    assert outside.read_bytes() == b'foreign archive must not be copied'
    assert not (target / 'outside.tar.gz').exists()


def test_existing_directory_source_keeps_its_snapshot_behavior(tmp_path):
    source = tmp_path / 'source'
    relative = 'fixture_dep'
    write_project(source, relative, packages=('*',))
    dependency = source / relative
    dependency.mkdir()
    declaration = '[project]\nname = "fixture-dep"\nversion = "1.0.0"\n'
    (dependency / 'pyproject.toml').write_text(declaration, encoding='utf-8')
    target = tmp_path / 'owned generation'

    _generate_pyproject([], target, source=source)

    assert (target / relative / 'pyproject.toml').read_text(encoding='utf-8') == declaration


@pytest.mark.parametrize('name', [
    'C:dep.whl', 'C:/dep.whl', r'\rooted\dep.whl',
    r'\\server\share\dep.whl', r'vendor\..\dep.whl',
])
def test_portable_archive_declarations_reject_anchored_or_parent_paths(name):
    from pm.workspace_inputs import _relative_archive_path

    with pytest.raises(InstallError, match='local dependency archive'):
        _relative_archive_path(name)
