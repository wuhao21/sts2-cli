"""
Game logging — saves every state + action per run as JSONL for debugging.

Log files are stored in <project_root>/logs/ with auto-cleanup of old files.
"""

import json
import os
import time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "logs")

# Default: keep logs for 7 days
LOG_RETENTION_DAYS = 7


def cleanup_old_logs(max_age_days=LOG_RETENTION_DAYS):
    """Remove log files older than max_age_days."""
    if not os.path.isdir(LOG_DIR):
        return
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for fname in os.listdir(LOG_DIR):
        if not fname.endswith(".jsonl"):
            continue
        fpath = os.path.join(LOG_DIR, fname)
        if os.path.getmtime(fpath) < cutoff:
            os.remove(fpath)
            removed += 1
    if removed:
        print(f"  [log] Cleaned up {removed} old log file(s)")


class GameLogger:
    """Logs every game step (state received + action sent) to a JSONL file."""

    def __init__(self, character: str, seed: str, enabled: bool = True):
        self.enabled = enabled
        self._step = 0
        self._file = None
        if not enabled:
            return

        os.makedirs(LOG_DIR, exist_ok=True)
        cleanup_old_logs()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_seed = str(seed).replace("/", "_")
        filename = f"{ts}_{character}_{safe_seed}.jsonl"
        self._path = os.path.join(LOG_DIR, filename)
        self._file = open(self._path, "w", encoding="utf-8")

    def log_state(self, state: dict):
        """Log a state/decision point received from the simulator."""
        if not self.enabled or not self._file:
            return
        self._step += 1
        entry = {
            "step": self._step,
            "ts": datetime.now().isoformat(),
            "type": "state",
            "data": state,
        }
        self._file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._file.flush()

    def log_action(self, action: dict):
        """Log an action/command sent to the simulator."""
        if not self.enabled or not self._file:
            return
        entry = {
            "step": self._step,
            "ts": datetime.now().isoformat(),
            "type": "action",
            "data": action,
        }
        self._file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._file.flush()

    def close(self):
        if self._file:
            self._file.close()
            self._file = None

    @property
    def path(self):
        return getattr(self, "_path", None)
