"""Prevent duplicate gateway processes for the same Resume Detective data."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QLockFile, pyqtSignal

import paths


_LOCAL_URL = re.compile(r"^http://127\.0\.0\.1:\d{1,5}$")


class GatewayControlBridge(QObject):
    """Queue HTTP-thread control requests onto the Qt application thread."""

    requested = pyqtSignal(str)

    def __init__(self, handler, parent: QObject | None = None):
        super().__init__(parent)
        self.requested.connect(handler)

    def submit(self, action: str) -> None:
        self.requested.emit(action)


class GatewayInstance:
    """A process lock plus a small activation record for the running gateway."""

    def __init__(self, data_dir: Path | None = None, state_dir: Path | None = None):
        data_root = (data_dir or paths.DATA_DIR).resolve()
        digest = hashlib.sha256(str(data_root).casefold().encode("utf-8")).hexdigest()[:20]
        base = state_dir or (Path(tempfile.gettempdir()) / "ResumeDetective")
        base.mkdir(parents=True, exist_ok=True)
        self._lock = QLockFile(str(base / f"gateway-{digest}.lock"))
        self._lock.setStaleLockTime(30_000)
        self._info_path = base / f"gateway-{digest}.json"
        self._owned = False

    def try_acquire(self) -> bool:
        self._owned = self._lock.tryLock(0)
        if self._owned:
            self._remove_info()
        return self._owned

    def publish(self, url: str) -> None:
        if not self._owned:
            raise RuntimeError("Cannot publish a gateway address without owning the lock.")
        if not _LOCAL_URL.fullmatch(url):
            raise ValueError(f"Refusing to publish a non-local gateway URL: {url}")
        temporary = self._info_path.with_name(
            f"{self._info_path.name}.{os.getpid()}.tmp"
        )
        try:
            temporary.write_text(
                json.dumps({"pid": os.getpid(), "url": url}, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary.replace(self._info_path)
        finally:
            temporary.unlink(missing_ok=True)

    def existing_url(self, fallback: str, timeout: float = 1.5) -> str:
        """Read the current instance address, waiting briefly during startup."""
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            try:
                payload = json.loads(self._info_path.read_text(encoding="utf-8"))
                url = str(payload.get("url") or "")
                if _LOCAL_URL.fullmatch(url):
                    return url
            except (FileNotFoundError, OSError, TypeError, json.JSONDecodeError):
                pass
            if time.monotonic() >= deadline:
                return fallback
            time.sleep(0.05)

    def release(self) -> None:
        if not self._owned:
            return
        self._remove_info()
        self._lock.unlock()
        self._owned = False

    def _remove_info(self) -> None:
        try:
            self._info_path.unlink(missing_ok=True)
        except OSError:
            # A stale activation record is harmless; the process lock remains
            # the authoritative single-instance guard.
            pass
