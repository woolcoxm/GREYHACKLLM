#!/usr/bin/env python3
"""Live observer for the GreyLLM bridge inside GreyHackDB.db.

Snapshots the bridge-relevant state (tree pointers + candidate row
contents) every 250ms and logs only changes. Run this while playing to
record exactly how the game reads/writes the bridge files.

Usage: python tools/watch-bridge.py [seconds]
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "daemon"))
from bridge import load_config, find_bridge_folder  # noqa: E402

BRIDGE_NAMES = [
    "prompt.txt", "mode.txt", "status.txt", "response.txt",
    "command.txt", "payload.txt", "command_status.txt",
    "command_result.txt", "out.txt",
]


def snapshot(conn):
    fs = json.loads(
        conn.execute(
            "SELECT FileSystem FROM Computer WHERE IsPlayer = 1"
        ).fetchone()[0]
    )
    _, node = find_bridge_folder(fs)
    state = {}
    if node:
        for child in node.get("files", []):
            name = child.get("nombre")
            if name in BRIDGE_NAMES:
                row = conn.execute(
                    "SELECT Content FROM Files WHERE ID = ?",
                    (child["ID"],),
                ).fetchone()
                state[f"tree:{name}"] = (
                    f"{child['ID'][:8]}:" + repr((row[0] if row else None) or "")[:48]
                )
    # candidate rows the game may be watching
    for rid, content in conn.execute("SELECT ID, Content FROM Files"):
        c = content or ""
        if (
            c.startswith("busy")
            or c.startswith("pending")
            or (c.startswith(" ") and len(c) < 40)
            or c in ("done", "chat", "agent", "PING", "")
            or c.startswith("error")
        ):
            state[f"row:{rid[:8]}"] = repr(c)[:52]
    return state


def main():
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 180
    db = load_config()["db_path"]
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    conn.execute("PRAGMA busy_timeout=5000")

    print(f"watching {db} for {duration:.0f}s — send messages in game now")
    prev = {}
    started = time.time()
    while time.time() - started < duration:
        try:
            cur = snapshot(conn)
        except sqlite3.Error as exc:
            print(f"[{time.time()-started:7.1f}] read error: {exc}")
            time.sleep(0.25)
            continue
        for key in sorted(set(prev) | set(cur)):
            if prev.get(key) != cur.get(key):
                print(
                    f"[{time.time()-started:7.1f}] {key}: "
                    f"{prev.get(key)} -> {cur.get(key)}"
                )
        prev = cur
        time.sleep(0.25)
    print("watch window ended")


if __name__ == "__main__":
    main()
