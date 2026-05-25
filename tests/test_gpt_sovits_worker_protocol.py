from __future__ import annotations

import io
import json
from typing import Any

from KGTS.core.tts_service import _PersistentGptSovitsWorker


class _FakeWorkerStdin(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flushed = False

    def flush(self) -> None:
        self.flushed = True


class _FakeWorkerStdout:
    def __init__(self, stdin: _FakeWorkerStdin) -> None:
        self._stdin = stdin
        self._lines: list[str] = [
            "GPT-SoVITS noisy stdout\n",
            json.dumps({"id": "previous-request", "success": True}) + "\n",
        ]

    def readline(self) -> str:
        if self._lines:
            return self._lines.pop(0)
        request = json.loads(self._stdin.getvalue().splitlines()[-1])
        return json.dumps({"id": request["id"], "success": True}) + "\n"


class _FakeWorkerProcess:
    def __init__(self) -> None:
        self.stdin = _FakeWorkerStdin()
        self.stdout = _FakeWorkerStdout(self.stdin)

    def poll(self) -> None:
        return None


def test_persistent_worker_skips_stale_protocol_output(monkeypatch: Any) -> None:
    worker = _PersistentGptSovitsWorker()
    process = _FakeWorkerProcess()

    monkeypatch.setattr(worker, "_ensure_started_locked", lambda _python: process)
    monkeypatch.setattr(worker, "_stop_locked", lambda: None)

    worker.synthesize("python", {"output_path": "unused"})

    assert process.stdin.flushed

