from __future__ import annotations

import wave

import pytest

from KGTS.core.tts_service import validate_wav_audio_file


def _write_wav(path, *, frames: int = 160) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\0\0" * frames)


def test_validate_wav_audio_file_accepts_playable_wav(tmp_path) -> None:
    path = tmp_path / "ok.wav"
    _write_wav(path)

    assert validate_wav_audio_file(path) == path


@pytest.mark.parametrize("content", [b"", b"not a wav response"])
def test_validate_wav_audio_file_rejects_missing_or_invalid_audio(tmp_path, content: bytes) -> None:
    path = tmp_path / "bad.wav"
    path.write_bytes(content)

    with pytest.raises(RuntimeError):
        validate_wav_audio_file(path, label="test audio")


def test_validate_wav_audio_file_rejects_header_without_frames(tmp_path) -> None:
    path = tmp_path / "silent.wav"
    _write_wav(path, frames=0)

    with pytest.raises(RuntimeError, match="empty or incomplete|no playable audio frames"):
        validate_wav_audio_file(path, label="test audio")
