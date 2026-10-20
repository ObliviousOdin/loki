"""The real Docker context filter must ship icon inputs without runtime state."""
from pathlib import Path
import shutil
import subprocess


def test_filtered_build_context_preserves_icon_sources_and_excludes_state(tmp_path):
    root = Path(__file__).resolve().parents[2]
    context = tmp_path / 'context'
    context.mkdir()
    shutil.copyfile(root / '.dockerignore', context / '.dockerignore')
    art = (
        'loki-mark-black.svg', 'loki-mark-white.svg',
        'nous-girl-black.svg', 'nous-girl-white.svg', 'dmg-volume.png',
    )
    (context / 'assets').mkdir()
    for name in art:
        shutil.copyfile(root / 'assets' / name, context / 'assets' / name)
    shutil.copytree(root / 'assets/backgrounds', context / 'assets/backgrounds')
    for name in ('.env', 'data/fixture-state.json', 'assets/private-fixture.txt'):
        path = context / name
        path.parent.mkdir(exist_ok=True)
        path.write_text('synthetic excluded state', encoding='utf-8')
    (context / 'Dockerfile').write_text('FROM scratch\nCOPY . /context/\n', encoding='utf-8')
    output = tmp_path / 'filtered'
    build = subprocess.run([
        'docker', 'build', '--network=none', '--pull=false',
        '--output', f'type=local,dest={output}', str(context),
    ], capture_output=True, text=True, timeout=60, check=False)
    assert build.returncode == 0, build.stdout + build.stderr
    for name in art:
        target = output / 'context/assets' / name
        assert target.is_file(), f'Icon source omitted from Docker build context: {name}'
        assert target.read_bytes() == (root / 'assets' / name).read_bytes()
    for source in (root / 'assets/backgrounds').iterdir():
        if source.is_file():
            assert (output / 'context/assets/backgrounds' / source.name).read_bytes() == source.read_bytes()
    for name in ('.env', 'data/fixture-state.json', 'assets/private-fixture.txt'):
        assert not (output / 'context' / name).exists()
