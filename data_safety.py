"""Personal-data backup, verification, and conservative restore helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from threading import Lock
import re
import shutil
import sqlite3

import paths


BACKUP_ROOT = paths.DATA_DIR.parent / f"{paths.DATA_DIR.name}-Backups"
_SCHEDULE_LOCK = Lock()


def database_health(db_path: Path | None = None) -> dict:
    target = Path(db_path or paths.DB_FILE)
    if not target.is_file():
        return {"ok": True, "message": "数据库尚未创建", "path": str(target)}
    try:
        connection = sqlite3.connect(str(target))
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        finally:
            connection.close()
        return {
            "ok": result == "ok",
            "message": "数据库检查通过" if result == "ok" else str(result),
            "schema_version": int(version),
            "path": str(target),
        }
    except sqlite3.Error as exc:
        return {"ok": False, "message": str(exc), "path": str(target)}


def _safe_label(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", value or "").strip("-")
    return cleaned[:48] or "manual"


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(label="manual") -> Path:
    """Create a verified backup outside the live data directory."""
    paths.ensure_data_directories()
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = BACKUP_ROOT / f"{timestamp}-{_safe_label(label)}"
    destination.mkdir()

    manifest = {"created_at": datetime.now().isoformat(timespec="seconds"), "files": {}}
    try:
        for source in paths.DATA_DIR.rglob("*"):
            if not source.is_file() or source.name in {"data.db-wal", "data.db-shm"}:
                continue
            relative = source.relative_to(paths.DATA_DIR)
            relative_parts = {part.lower() for part in relative.parts}
            if "reasonix" in relative_parts and relative_parts & {"cache", "runtime"}:
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() == paths.DB_FILE.resolve():
                source_connection = sqlite3.connect(str(source))
                target_connection = sqlite3.connect(str(target))
                try:
                    source_connection.backup(target_connection)
                finally:
                    target_connection.close()
                    source_connection.close()
            else:
                try:
                    shutil.copy2(source, target)
                except FileNotFoundError:
                    # Runtime tools may rotate disposable files between rglob and copy.
                    continue
            manifest["files"][relative.as_posix()] = {
                "size": target.stat().st_size,
                "sha256": _file_hash(target),
            }

        health = database_health(destination / paths.DB_FILE.name)
        if not health["ok"]:
            raise RuntimeError(f"备份数据库检查失败：{health['message']}")
        (destination / "backup-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination
    except Exception:
        if destination.is_dir():
            shutil.rmtree(destination)
        raise


def list_backups() -> list[Path]:
    if not BACKUP_ROOT.is_dir():
        return []
    return sorted(
        (item for item in BACKUP_ROOT.iterdir() if item.is_dir()),
        key=lambda item: item.name,
        reverse=True,
    )


def automatic_backup_status(now: datetime | None = None) -> dict:
    """返回自动备份是否到期；不创建、不删除任何文件。"""
    import config_manager

    preferences = config_manager.get_backup_preferences()
    now = now or datetime.now().astimezone()
    last_at = None
    if preferences["last_backup_at"]:
        try:
            last_at = datetime.fromisoformat(preferences["last_backup_at"])
            if last_at.tzinfo is None:
                last_at = last_at.astimezone()
        except ValueError:
            last_at = None
    due = bool(
        preferences["enabled"]
        and (
            last_at is None
            or now >= last_at + timedelta(days=preferences["interval_days"])
        )
    )
    return {**preferences, "due": due, "last_at": last_at}


def maybe_create_automatic_backup(now: datetime | None = None) -> Path | None:
    """仅在用户启用且间隔到期时建立验证过的备份。"""
    import config_manager

    with _SCHEDULE_LOCK:
        if not automatic_backup_status(now)["due"]:
            return None
        backup = create_backup("automatic")
        config_manager.mark_automatic_backup_completed()
        return backup


def restore_backup(backup_dir: str | Path) -> Path:
    """Restore files conservatively after making a pre-restore safety backup."""
    source_root = Path(backup_dir).resolve()
    allowed_root = BACKUP_ROOT.resolve()
    if source_root.parent != allowed_root or not source_root.is_dir():
        raise ValueError("只能恢复由 Resume Detective 创建的备份目录")
    source_db = source_root / paths.DB_FILE.name
    health = database_health(source_db)
    if not source_db.is_file() or not health["ok"]:
        raise RuntimeError(f"备份数据库不可用：{health['message']}")

    safety_backup = create_backup("before-restore")
    paths.ensure_data_directories()
    for source in source_root.rglob("*"):
        if not source.is_file() or source.name == "backup-manifest.json":
            continue
        relative = source.relative_to(source_root)
        target = paths.DATA_DIR / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() == source_db.resolve():
            source_connection = sqlite3.connect(str(source))
            target_connection = sqlite3.connect(str(target))
            try:
                source_connection.backup(target_connection)
            finally:
                target_connection.close()
                source_connection.close()
        else:
            shutil.copy2(source, target)

    restored_health = database_health()
    if not restored_health["ok"]:
        raise RuntimeError(f"恢复后数据库检查失败：{restored_health['message']}")
    return safety_backup
