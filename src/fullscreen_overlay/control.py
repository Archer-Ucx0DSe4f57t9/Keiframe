"""Small, Qt-free control mailbox shared with the Game Bar client.

Only complete, atomically renamed JSON files are consumed. Commands are
claimed before execution; a crash may leave their outcome unknown, never
silently replay a non-idempotent toggle.
"""
import json
import math
import os
import re
import time
from pathlib import Path

HEARTBEAT_FILE = "overlay.heartbeat"
LEASE_SECONDS = 3.0
COMMAND_SECONDS = 5.0
_ID = re.compile(r"^[0-9a-f]{32}$")


def _read_json(path):
    if path.stat().st_size > 4096:
        raise ValueError("oversized control message")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("invalid control message")
    return value


def _fresh(value, now, duration):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= now - value <= duration)


def live_session(folder, now=None):
    if folder is None:
        return None
    now = time.time() if now is None else now
    try:
        data = _read_json(Path(folder) / HEARTBEAT_FILE)
        session = data.get("session", "")
        if (data.get("version") == 1 and isinstance(session, str)
                and _ID.fullmatch(session)
                and _fresh(data.get("updated_at"), now, LEASE_SECONDS)):
            return session
    except (OSError, ValueError, TypeError):
        pass
    return None


def atomic_json(path, data):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, path)


def process_commands(folder, execute, now=None):
    """Run fresh commands once and acknowledge the actual synchronous result."""
    if folder is None or not Path(folder).is_dir():
        return
    folder = Path(folder)
    now = time.time() if now is None else now
    session = live_session(folder, now)
    for path in sorted(folder.glob("overlay.command.*.json"))[:32]:
        command_id = path.name[len("overlay.command."):-len(".json")]
        if not _ID.fullmatch(command_id):
            continue
        ack = folder / ("overlay.ack." + command_id + ".json")
        claimed = path.with_suffix(".processing")
        try:
            # Rename, rather than read/delete, so a complete publication cannot
            # race with a consumer reading an in-progress file.
            os.replace(path, claimed)
        except OSError:
            continue
        try:
            if ack.exists():
                continue
            data = _read_json(claimed)
            if (data.get("version") != 1 or data.get("id") != command_id
                    or not session or data.get("session") != session
                    or not _fresh(data.get("created_at"), now, COMMAND_SECONDS)
                    or data.get("action") != "toggle_lock"):
                raise ValueError("expired or invalid command")
            execute()
            result = {"id": command_id, "ok": True}
        except Exception as exc:
            result = {"id": command_id, "ok": False, "error": str(exc)}
        finally:
            try:
                claimed.unlink(missing_ok=True)
            except OSError:
                pass  # A claimed file is never replayed.
        try:
            atomic_json(ack, result)
        except OSError:
            # Execution cannot safely be retried when only acknowledgment failed.
            pass
