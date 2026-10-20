"""Shared host temp directories never overwrite or sweep Hermes audio/results."""

import os
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_voice_recording_cleanup_preserves_foreign_audio(tmp_path, monkeypatch):
    from tools import voice_mode

    assert Path(voice_mode._TEMP_DIR).name == "loki_voice"
    own = tmp_path / "loki_voice"
    foreign = tmp_path / "hermes_voice"
    own.mkdir()
    foreign.mkdir()
    name = "recording_20240101_000000.wav"
    (own / name).write_bytes(b"owned expired audio")
    (foreign / name).write_bytes(b"foreign expired audio")
    old = time.time() - 7200
    for directory in (own, foreign):
        os.utime(directory / name, (old, old))
    monkeypatch.setattr(voice_mode, "_TEMP_DIR", str(own))
    assert voice_mode.cleanup_temp_recordings(max_age_seconds=3600) == 1
    assert not (own / name).exists()
    assert (foreign / name).read_bytes() == b"foreign expired audio"
    paths = [voice_mode._new_recording_path("wav") for _ in range(2)]
    assert len(set(paths)) == 2
    assert all(Path(path).parent == own for path in paths)


@pytest.mark.parametrize("surface", ["tui", "cli"])
def test_voice_synthesis_paths_are_owned_and_unique(tmp_path, monkeypatch, surface):
    from hermes_cli import voice
    from hermes_cli.cli_voice_mixin import CLIVoiceMixin
    from tools import tts_tool

    paths = []

    def synthesize(**kwargs):
        paths.append(Path(kwargs["output_path"]))
        return '{"success": false}'

    monkeypatch.setattr(voice.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(tts_tool, "text_to_speech_tool", synthesize)
    # A failed mocked synthesis never plays audio or imports an audio device backend.
    obj = SimpleNamespace(_voice_tts=True, _voice_tts_done=threading.Event())
    for _ in range(2):
        if surface == "tui":
            voice._speak_whole_file("fixture")
        else:
            CLIVoiceMixin._voice_speak_response(obj, "fixture")
    assert len(paths) == len(set(paths)) == 2
    assert all(path.parent == tmp_path / "loki_voice" for path in paths)


def test_gateway_voice_path_is_owned(tmp_path, monkeypatch):
    from gateway.platforms import base

    monkeypatch.setattr(base.tempfile, "gettempdir", lambda: str(tmp_path))
    path = Path(base.build_auto_tts_output_path("telegram"))
    assert path.parent == tmp_path / "loki_voice"
    assert path.suffix == ".ogg"


def test_result_default_fallback_is_owned():
    from tools.tool_result_storage import STORAGE_DIR

    assert Path(STORAGE_DIR).name == "loki-results"


@pytest.mark.platforms("posix")
def test_result_fallback_preserves_foreign_same_id(tmp_path, monkeypatch):
    from tools import tool_result_storage as storage

    foreign = tmp_path / "hermes-results" / "same-tool-id.txt"
    foreign.parent.mkdir()
    foreign.write_text("foreign result", encoding="utf-8")

    def execute(command, *, stdin_data=None, timeout=None):
        result = subprocess.run(["bash", "-c", command], input=stdin_data, text=True,
                                capture_output=True, timeout=timeout, check=False)
        return {"returncode": result.returncode, "output": result.stdout + result.stderr}

    env = SimpleNamespace(get_temp_dir=lambda: str(tmp_path), execute=execute)
    monkeypatch.setattr(storage, "_write_to_spillover", lambda *_args: None)
    result = storage.maybe_persist_tool_result("owned result", "fixture", "same-tool-id", env=env, threshold=0)
    own = tmp_path / "loki-results" / "same-tool-id.txt"
    assert own.read_text(encoding="utf-8") == "owned result"
    assert str(own) in result
    assert foreign.read_text(encoding="utf-8") == "foreign result"
    assert storage.expired_archive_fields(str(own))["expired"] is True
    assert storage.expired_archive_fields(str(foreign))["expired"] is True
