"""Execution Checkpoints and Resumption Engine for DESK.
Enables safe recovery from interruptions without repeating expensive computations.
Zero external dependencies.
"""
import os
import json
import time
import hashlib
from typing import Dict, List, Optional, Any

class CheckpointManager:
    """Manages atomic checkpoints of engineering state and execution progress."""

    @staticmethod
    def _checkpoint_dir(project_dir: str) -> str:
        d = os.path.join(project_dir, "state", "checkpoints")
        os.makedirs(d, exist_ok=True)
        return d

    @classmethod
    def save_checkpoint(cls, project_dir: str, stage: str, state_data: Dict[str, Any], max_history: int = 10) -> str:
        d = cls._checkpoint_dir(project_dir)
        ts = time.time()
        raw = json.dumps(state_data, sort_keys=True, default=str)
        chk_hash = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        filename = f"chk_{int(ts * 1000)}_{stage}_{chk_hash}.json"
        filepath = os.path.join(d, filename)

        payload = {
            "checkpoint_id": filename,
            "stage": stage,
            "timestamp": ts,
            "state_hash": chk_hash,
            "data": state_data
        }

        # Write to temporary file then atomic replace
        tmp_path = filepath + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, filepath)

        # Prune oldest checkpoints
        cls._prune_old_checkpoints(d, max_history)
        return filename

    @classmethod
    def load_latest_checkpoint(cls, project_dir: str, stage: Optional[str] = None) -> Optional[Dict[str, Any]]:
        d = cls._checkpoint_dir(project_dir)
        files = [f for f in os.listdir(d) if f.startswith("chk_") and f.endswith(".json")]
        if not files:
            return None

        # Sort descending by timestamp in filename
        files.sort(reverse=True)
        for fname in files:
            if stage and f"_{stage}_" not in fname:
                continue
            fpath = os.path.join(d, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
        return None

    @classmethod
    def _prune_old_checkpoints(cls, checkpoint_dir: str, max_history: int):
        files = [f for f in os.listdir(checkpoint_dir) if f.startswith("chk_") and f.endswith(".json")]
        if len(files) > max_history:
            files.sort()  # Oldest first
            for f in files[:-max_history]:
                try:
                    os.remove(os.path.join(checkpoint_dir, f))
                except OSError:
                    pass
