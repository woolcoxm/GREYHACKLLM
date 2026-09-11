#!/usr/bin/env python3
"""GreyLLM bridge daemon — an agent harness for Grey Hack (singleplayer).

The GLM model is given tools (read/write/list/run on the in-game machine) and
iterates until the task is done, Claude-Code style.

Transport: Grey Hack stores the whole singleplayer world in a SQLite database
(GreyHack_Data/GreyHackDB.db). In-game files live as rows in the Files table,
referenced by ID from the Computer.FileSystem JSON tree. The bridge talks
through that database: `agent` in the game writes prompt/status rows; this
daemon reads them, calls GLM, writes responses back. All bridge writes are
single-transaction row updates on files that already exist, so the tree is
never touched.

Setup:
    python bridge.py --db-map            (after `agent -t` in game)
    python bridge.py --check             (API key + bridge sanity)
    python bridge.py                     (watch mode — run while playing)

Other modes:
    python bridge.py --mock              watch mode with a fake LLM
    python bridge.py --demo [--mock] [--agent] [--sqlite]
                                         one-shot self test; --sqlite runs it
                                         through the real SQLite transport on
                                         a scratch database

API configuration lives in config.json; the key can also be pasted into
daemon/api_key.txt or set as ZAI_API_KEY / GLM_API_KEY. Agent mode requires
the anthropic protocol (the GLM Coding Plan endpoint supports tool use).

Uses only the Python standard library.
"""

import argparse
import json
import os
import re
import socket
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

DAEMON_DIR = Path(__file__).resolve().parent
PROJECT_DIR = DAEMON_DIR.parent
SYNTAX_CHECKER = PROJECT_DIR / "tools" / "check-syntax.mjs"
BACKUP_DIR = DAEMON_DIR / "db-backups"
HISTORY_PATH = DAEMON_DIR / "history.json"
API_KEY_FILE = DAEMON_DIR / "api_key.txt"

DEFAULT_DB_PATH = (
    r"C:\Program Files (x86)\Steam\steamapps\common\Grey Hack"
    r"\Grey Hack_Data\GreyHackDB.db"
)

DEFAULT_CONFIG = {
    "transport": "hook",
    "hook_port": 7788,
    "hook_bridge_dir": "",
    "api_style": "anthropic",
    "base_url": "https://api.z.ai/api/anthropic",
    "model": "glm-5.3",
    "api_key": "",
    "db_path": "",
    "db_file_ids": {},
    "poll_interval": 0.5,
    "max_history": 6,
    "request_timeout": 600,
    "max_tokens": 16384,
    "max_tool_rounds": 0,
    "tool_timeout": 120,
}

BRIDGE_FILES = (
    "prompt.txt",   # game-owned
    "mode.txt",     # game-owned
    "status.txt",   # game-owned ("busy <nonce>")
    "response.txt",  # daemon-owned, fixed row
    "done.txt",     # daemon-owned completion signal, fixed row
    "command.txt",   # daemon-owned, fixed row
    "payload.txt",   # daemon-owned, fixed row
    "cmdflag.txt",   # daemon-owned pending signal, fixed row
    "command_status.txt",   # game-owned ("done/error <nonce>")
    "command_result.txt",   # game-owned
)

AGENT_TOOLS = [
    {
        "name": "list_dir",
        "description": "List the files and folders of a directory on the "
        "in-game machine. Use '/' to see the whole disk.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file from the in-game machine.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a text file on the in-game "
        "machine. Write runnable programs to /home/<player>/<name> WITHOUT "
        "a file extension — .src files cannot be executed by name, /bin is "
        "not writable by regular users, and home programs run by name from "
        "the home directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "append_file",
        "description": "Append text to a file on the in-game machine.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "make_dir",
        "description": "Create a directory on the in-game machine.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "delete_file",
        "description": "Delete a file or (empty) directory on the in-game "
        "machine.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "compile_program",
        "description": "Compile GreyScript source into a runnable binary "
        "program. binary_folder is the DESTINATION FOLDER (e.g. "
        "'/home/player'), NOT a file path — the binary is created inside "
        "it, named after the source file without its .src extension. "
        "Example: compile_program(source_path='/home/player/tool.src', "
        "binary_folder='/home/player') then run_program"
        "(path='/home/player/tool'). Plain paths, no semicolons.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_path": {"type": "string"},
                "binary_folder": {"type": "string"},
            },
            "required": ["source_path", "binary_folder"],
        },
    },
    {
        "name": "run_program",
        "description": "Launch a BINARY program (made with "
        "compile_program) with optional arguments. Raw .src source files "
        "cannot be launched — compile them first. The program's terminal "
        "output is not capturable, so this tool waits ~10s and returns "
        "whatever the program appended to the bridge out.txt (sysinfo "
        "reports the bridge dir) — have your programs append results "
        "there. IMPORTANT: the launched program is a separate process — "
        "any shell or foothold it gains through exploits DIES when it "
        "exits. Design each tool as one complete unit of work (gain "
        "foothold → act → write results), or convert footholds into "
        "credentials (recorded in notes.txt) before the tool exits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "args": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "sysinfo",
        "description": "List the system programs installed on the in-game "
        "machine (/bin) and the player home directory — use this first to "
        "learn what tools exist.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "api_doc",
        "description": "Look up the OFFICIAL GreyScript API documentation for "
        "a type or method — e.g. 'router', 'net_use', 'string split', "
        "'wallet', 'include_lib'. Returns the exact signature, behavior, "
        "return values and a usage example. ALWAYS call this before using an "
        "API you have not used before: invented APIs are the #1 cause of "
        "runtime errors like 'Undefined Identifier' or 'Key Not Found'.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "load_skill",
        "description": "Load a mission playbook. Skills contain verified "
        "game techniques (recon, exploitation, opsec/log clearing, bank "
        "theft, social engineering) beyond the reference. Load the "
        "matching skill BEFORE starting that kind of work — e.g. "
        "load_skill('recon') before attacking, load_skill('opsec') before "
        "and after touching any machine you don't own.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "ask_user",
        "description": "You are BLOCKED on something only the user can fix: "
        "required software/library not installed and not obtainable "
        "in-game, missing critical target details, or an important "
        "decision. Call this ONCE with a concise question, then STOP: make "
        "no more tool calls this turn — your final message must ask the "
        "user and say exactly how to fix it. The mission resumes with "
        "full context when the user replies in the chat.",
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
]

MOCK_CHAT_REPLY = """Here is a tool that greets every user folder.

```
// greet.src — say hi to every user
main = function(params)
	comp = get_shell.host_computer
	home = comp.File("/home")
	if home == null then
		print("no /home found")
		return null
	end if
	for folder in home.get_folders
		print("hello " + folder.name)
	end for
	return null
end function

main(params)
```

(mock reply — configure your GLM API key and drop --mock for real answers)"""


# --- Small helpers ------------------------------------------------------


def load_config():
    config = dict(DEFAULT_CONFIG)
    if (DAEMON_DIR / "config.json").exists():
        try:
            config.update(
                json.loads(
                    (DAEMON_DIR / "config.json").read_text(encoding="utf-8")
                )
            )
        except (json.JSONDecodeError, OSError) as exc:
            die(f"could not parse config.json: {exc}")
    return config


def save_config(config):
    (DAEMON_DIR / "config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )


def log(message):
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp}] {message}")


def die(message, code=1):
    sys.stdout.flush()
    print(f"error: {message}", file=sys.stderr)
    sys.exit(code)


def resolve_api_key(config):
    if config.get("api_key"):
        return config["api_key"]
    for env_name in ("ZAI_API_KEY", "GLM_API_KEY", "ANTHROPIC_API_KEY"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    if API_KEY_FILE.exists():
        value = API_KEY_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    return None


API_REF_MARKER = (
    "<!-- api-reference: generated below, do not edit past this line -->"
)

SKILLS_DIR = DAEMON_DIR / "prompt_pack" / "skills"


def skill_index():
    """One-line index of available skills: name + when to load it."""
    if not SKILLS_DIR.is_dir():
        return []
    entries = []
    for p in sorted(SKILLS_DIR.glob("*.md")):
        first = ""
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("load for:"):
                first = line.split(":", 1)[1].strip()
                break
        entries.append((p.stem, first))
    return entries


def load_skill(name):
    """Return a skill playbook by (fuzzy) name."""
    if not SKILLS_DIR.is_dir():
        return False, "no skills installed under prompt_pack/skills"
    want = (name or "").strip().lower()
    if not want:
        return False, "load_skill: pass a skill name — " + ", ".join(
            n for n, _ in skill_index()
        )
    squish = lambda s: s.replace("-", "").replace("_", "").replace(" ", "")
    for p in sorted(SKILLS_DIR.glob("*.md")):
        stem = p.stem.lower()
        if want == stem or want in stem or stem in want or (
            squish(want) == squish(stem)
        ):
            return True, p.read_text(encoding="utf-8", errors="replace")
    return False, (
        f"load_skill: no skill matches {name!r}. Available: "
        + ", ".join(n for n, _ in skill_index())
    )


def build_system_prompt():
    parts = []
    for name in ("system.md", "greyscript_reference.md"):
        p = DAEMON_DIR / "prompt_pack" / name
        if not p.exists():
            print(f"warning: missing prompt pack file {p}", file=sys.stderr)
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if name == "greyscript_reference.md" and API_REF_MARKER in text:
            # the full generated API appendix (~170 KB) is searchable via the
            # api_doc tool instead of bloating every request
            text = text.split(API_REF_MARKER, 1)[0]
        parts.append(text)
    skills = skill_index()
    if skills:
        lines = ["", "## Mission skills (load_skill)", ""]
        for sname, when in skills:
            lines.append(f"- `{sname}` — {when}")
        lines.append(
            "\nLoad the matching skill with load_skill(name) BEFORE the "
            "work it covers. opsec applies to every mission that touches "
            "a machine you don't own."
        )
        parts.append("\n".join(lines))
    return "\n\n---\n\n".join(parts)


def load_api_reference():
    """Parse the generated appendix into (section, method, block) entries."""
    p = DAEMON_DIR / "prompt_pack" / "greyscript_reference.md"
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8", errors="replace")
    if API_REF_MARKER in text:
        text = text.split(API_REF_MARKER, 1)[1]
    entries = []
    section = ""
    for piece in re.split(r"(?m)^(?=- `)", text):
        piece = piece.strip("\n")
        if not piece.strip():
            continue
        m = re.match(r"- `([A-Za-z_]\w*)", piece)
        if m:
            # a section header can ride at the END of an entry's piece
            # (the split only breaks on entry lines) — cut it off and
            # let it retarget the section for the entries that follow
            h = re.search(r"(?m)^### .+$", piece)
            if h:
                section = h.group(0)[4:].strip()
                piece = piece[: h.start()].rstrip()
            entries.append((section, m.group(1), piece))
            continue
        h = re.search(r"(?m)^### (.+)$", piece)
        if h:
            section = h.group(1).strip()
    return entries


def api_doc_lookup(query):
    """Answer an api_doc tool call from the generated API reference.
    All query terms must appear in 'section.method' (case-insensitive), so
    'router' lists the router API and 'string split' finds string.split."""
    entries = load_api_reference()
    terms = [t for t in re.split(r"[\s,]+", (query or "").strip().lower()) if t]
    if not entries:
        return False, (
            "api_doc: the generated API reference is missing from the "
            "prompt pack — run tools/build-reference.mjs"
        )
    if not terms:
        return False, (
            "api_doc: pass a type or method name, e.g. 'router', 'net_use', "
            "'string split'"
        )
    hits = []
    for section, method, block in entries:
        hay = (section + "." + method).lower()
        if all(t in hay for t in terms):
            hits.append((section, block))
    if not hits:
        known = sorted({e[0] for e in entries})
        return False, (
            f"api_doc: no API matches {query!r}. Known API sections: "
            + ", ".join(known)
            + ". If your idea is not there it does not exist in GreyScript."
        )
    out = []
    last = None
    used = 0
    for section, block in hits[:20]:
        if section != last:
            out.append(f"[{section}]")
            last = section
        out.append(block)
        used += len(block) + len(section) + 4
        if used > 6000:
            out.append("(more matches truncated — narrow the query)")
            break
    return True, "\n\n".join(out)


def sanitize_reply(text):
    """Strip language tags after code fences so the in-game saveCodeBlock
    parser (which splits on plain ```) gets clean code."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") and len(stripped) > 3:
            line = line[: line.index("```") + 3]
        out.append(line)
    return "\n".join(out) + "\n"


def validate_greyscript(source):
    """Run the real GreyScript parser (greyscript-core) on a .src payload.
    Returns None when valid (or when node/the checker is unavailable),
    otherwise the parser's error message."""
    if not SYNTAX_CHECKER.exists():
        return None
    fd, tmp_name = tempfile.mkstemp(suffix=".src")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(source)
        proc = subprocess.run(
            ["node", str(SYNTAX_CHECKER), tmp_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
    if proc.returncode == 0:
        return None
    output = (proc.stderr or proc.stdout or "").strip()
    return output.splitlines()[-1] if output else "unknown syntax error"


# --- Transports ---------------------------------------------------------


def walk_fs_tree(node, path=""):
    """Yield (path, node) for every file and folder in the FileSystem JSON."""
    name = node.get("nombre", "/")
    here = path if name == "/" else path + "/" + name
    yield here, node
    for child in node.get("files", []):
        yield here + "/" + child.get("nombre", "?"), child
    for folder in node.get("folders", []):
        yield from walk_fs_tree(folder, here)


def find_bridge_folder(fs):
    """Return (path, node) of /home/<user>/llm in the FileSystem tree."""
    for path, node in walk_fs_tree(fs):
        if ".Trash" in path:
            continue
        if (
            path.endswith("/.greyllm")
            and path.startswith("/home/")
            and path.count("/") == 3
        ):
            return path, node
    return None, None


class FileTransport:
    """Plain-file bridge (used by --demo; kept for compatibility)."""

    def __init__(self, bridge_dir):
        self.bridge_dir = Path(bridge_dir)
        self.bridge_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name):
        return self.bridge_dir / name

    def read(self, name):
        try:
            return self._path(name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def write(self, name, content):
        tmp = self._path(str(name) + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(self._path(name))

    def write_many(self, pairs):
        for name, content in pairs:
            self.write(name, content)

    def exists(self, name):
        return self._path(name).exists()


class HookTransport:
    """Real-time transport through the GreyLLMHook BepInEx plugin.

    Reads and writes go straight to the game's live in-memory filesystem
    via the plugin's local TCP API — no SQLite save cadence involved.
    Speaks the same Transport interface as the SQLite bridge.
    """

    def __init__(self, host="127.0.0.1", port=7788, bridge_dir=None):
        self.host = host
        self.port = port
        self._sock = None
        self._bridge_dir = bridge_dir

    def _connect(self):
        if self._sock is None:
            self._sock = socket.create_connection(
                (self.host, self.port), timeout=10
            )
            self._sock.settimeout(330)
        return self._sock

    def _call(self, request):
        import json as _json

        payload = (_json.dumps(request) + '\n').encode("utf-8")
        for attempt in range(2):
            try:
                sock = self._connect()
                sock.sendall(payload)
                buf = b""
                while not buf.endswith(b'\n'):
                    chunk = sock.recv(65536)
                    if not chunk:
                        raise ConnectionError("hook closed the connection")
                    buf += chunk
                return _json.loads(buf.decode("utf-8"))
            except (ConnectionError, OSError, BrokenPipeError):
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None
                if attempt == 1:
                    raise ConnectionError(
                        f"cannot talk to the GreyLLM hook at "
                        f"{self.host}:{self.port} — is the game running "
                        "with the plugin loaded?"
                    )
                time.sleep(0.2)

    def _path(self, name):
        if not self._bridge_dir:
            self._discover()
        return f"{self._bridge_dir}/{name}"

    def _discover(self):
        health = self._call({"op": "health"})
        if not health.get("ok"):
            raise ConnectionError(f"hook unhealthy: {health.get('error')}")
        if not health.get("session"):
            raise ConnectionError(
                "hook has no player session — log into a singleplayer world"
            )
        listing = self._call({"op": "list", "path": "/home"})
        for entry in listing.get("entries", []):
            if entry.get("type") != "dir":
                continue
            candidate = f"/home/{entry['name']}/.greyllm"
            probe = self._call({"op": "exists", "path": candidate})
            if probe.get("exists") and probe.get("isFolder"):
                self._bridge_dir = candidate
                return
        raise ConnectionError(
            "bridge folder /home/<you>/.greyllm not found — run `agent -t` "
            "in game once"
        )

    def read(self, name):
        result = self._call({"op": "read", "path": self._path(name)})
        if not result.get("ok"):
            return None
        return result.get("content")

    def write(self, name, content):
        result = self._call(
            {"op": "write", "path": self._path(name), "content": content or ""}
        )
        if not result.get("ok"):
            raise RuntimeError(f"hook write failed: {result.get('error')}")

    def write_many(self, pairs):
        for name, content in pairs:
            self.write(name, content)

    def exists(self, name):
        result = self._call({"op": "exists", "path": self._path(name)})
        return bool(result.get("exists"))

    def close(self):
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


class SQLiteTransport:
    """Reads/writes the bridge files inside Grey Hack's GreyHackDB.db.

    The Files table is CONTENT-ADDRESSED: the row ID is the md5 hex of the
    content, and the Computer.FileSystem JSON tree points each file at the
    row holding its current content. When the game rewrites a file it
    repoints the tree at a NEW row — so a static ID map goes stale
    instantly. Therefore:

    - reads  resolve the file's CURRENT ID from the tree on every access;
    - writes UPDATE the row the tree currently points at, in place. The
      game reads content by ID without re-hashing, so daemon-written
      content is visible in-game immediately (proven by the PONG test).
    """

    def __init__(self, db_path, file_ids=None):
        self.db_path = str(db_path)
        self.file_ids = dict(file_ids or {})  # informational only

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _load_fs(self, conn):
        row = conn.execute(
            "SELECT FileSystem FROM Computer WHERE IsPlayer = 1"
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT FileSystem FROM Computer"
            ).fetchone()
        if not row:
            raise RuntimeError("no Computer row in the game database")
        return json.loads(row[0])

    def _resolve(self, name):
        """Current row ID for a bridge file, from the live FileSystem tree."""
        conn = self._connect()
        try:
            fs = self._load_fs(conn)
            _, node = find_bridge_folder(fs)
            if not node:
                raise RuntimeError(
                    "bridge folder /home/<you>/.greyllm not found — run "
                    "`agent -t` in game"
                )
            for child in node.get("files", []):
                if child.get("nombre") == name:
                    return child["ID"]
            raise RuntimeError(
                f"bridge file '{name}' not created yet — run `agent -t` "
                "(or a first task) in game first"
            )
        finally:
            conn.close()

    def read(self, name):
        fid = self._resolve(name)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT Content FROM Files WHERE ID = ?", (fid,)
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def write(self, name, content):
        self.write_many([(name, content)])

    def write_many(self, pairs):
        """Daemon-owned files are written IN PLACE at their fixed tree row.

        Ownership rules (protocol v5):
        - game-owned files (prompt/mode/status/command_status/command_result)
          are ONLY read here; the daemon never writes them, so the game's
          set_content never encounters a hash-corrupted current row.
        - daemon-owned files (response/done/command/payload/cmdflag) are
          only ever updated in place — visible to the game immediately
          (the game reads content live by row ID) — and the tree pointer
          never changes, so the game's in-memory tree stays in sync.
        """
        ids = {name: self._resolve(name) for name, _ in pairs}
        for attempt in range(3):
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                for name, content in pairs:
                    conn.execute(
                        "UPDATE Files SET Content = ? WHERE ID = ?",
                        (content or "", ids[name]),
                    )
                conn.execute("COMMIT")
                return
            except sqlite3.OperationalError as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                if "locked" not in str(exc).lower() or attempt == 2:
                    raise
                time.sleep(0.3 * (attempt + 1))
            finally:
                conn.close()

    def exists(self, name):
        return self.read(name) is not None

    def shotgun(self, glob_patterns, content):
        """Write content into EVERY row matching the glob patterns.

        The game's in-memory filesystem may watch any row it previously
        wrote for a file (its pointer does not follow our tree repoints),
        and we cannot know which one a running game session holds. All
        candidate rows are single-use nonce rows, so overwriting them is
        safe. Used to publish status/response values visibly.
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            for pattern in glob_patterns:
                conn.execute(
                    "UPDATE Files SET Content = ? WHERE Content GLOB ?",
                    (content, pattern),
                )
            conn.execute("COMMIT")
        except sqlite3.OperationalError:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    def backup(self):
        """Snapshot the DB before the daemon starts touching it."""
        BACKUP_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = BACKUP_DIR / f"GreyHackDB-{stamp}.db"
        shutil.copy2(self.db_path, target)
        # keep the last 10 backups
        backups = sorted(BACKUP_DIR.glob("GreyHackDB-*.db"))
        for old in backups[:-10]:
            old.unlink(missing_ok=True)
        return target


def make_transport(config):
    mode = (config.get("transport") or "hook").lower()
    if mode == "hook":
        return HookTransport(
            port=int(config.get("hook_port") or 7788),
            bridge_dir=config.get("hook_bridge_dir") or None,
        )
    if mode == "sqlite" and config.get("db_path"):
        return SQLiteTransport(config["db_path"], config.get("db_file_ids"))
    die(
        "bridge not configured. For the hook transport: launch Grey Hack "
        "with the GreyLLMHook plugin and run `agent -t` in game once. "
        "For sqlite: run --db-map."
    )


# --- API calls ----------------------------------------------------------


def http_json(url, body, headers, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def error_message(exc):
    """Best-effort human message from an HTTPError."""
    try:
        detail = exc.read().decode("utf-8", errors="replace")
        data = json.loads(detail)
        err = data.get("error", {})
        msg = err.get("message") if isinstance(err, dict) else None
        return msg or detail[:300]
    except Exception:  # noqa: BLE001 - fall back to the code alone
        return f"HTTP {exc.code}"


def anthropic_call(config, api_key, system_prompt, messages, tools=None):
    body = {
        "model": config["model"],
        "max_tokens": config["max_tokens"],
        "temperature": 0.3,
        "system": system_prompt,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools
    return http_json(
        config["base_url"].rstrip("/") + "/v1/messages",
        body,
        {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        config["request_timeout"],
    )


def openai_chat(config, api_key, system_prompt, prompt, history):
    data = http_json(
        config["base_url"].rstrip("/") + "/chat/completions",
        {
            "model": config["model"],
            "temperature": 0.3,
            "max_tokens": config["max_tokens"],
            "messages": [
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": prompt},
            ],
        },
        {"Authorization": f"Bearer {api_key}"},
        config["request_timeout"],
    )
    return data["choices"][0]["message"]["content"]


def extract_text(blocks):
    return "".join(
        block.get("text", "")
        for block in blocks
        if block.get("type") == "text"
    )


def load_history():
    if HISTORY_PATH.exists():
        try:
            value = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            if isinstance(value, list):
                return value
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_history(history):
    HISTORY_PATH.write_text(
        json.dumps(history[-50:], indent=2), encoding="utf-8"
    )


def make_llm_fn(config, api_key):
    """Uniform llm_fn(system, messages, with_tools) -> API response dict.

    Transient failures (timeouts, connection drops, 429/5xx) are retried
    so a network hiccup can't kill a whole mission; definitive API errors
    (4xx) raise immediately.
    """
    style = config["api_style"].lower()

    def retrying(fn, attempts=3):
        def call(system, messages, with_tools):
            for i in range(attempts):
                try:
                    return fn(system, messages, with_tools)
                except urllib.error.HTTPError as exc:
                    transient = exc.code in (408, 429) or exc.code >= 500
                    if not transient or i == attempts - 1:
                        raise
                    wait_s = 10 * (i + 1)
                    print(
                        f"[bridge] LLM HTTP {exc.code}; retry "
                        f"{i + 1}/{attempts - 1} in {wait_s}s"
                    )
                    time.sleep(wait_s)
                except (
                    urllib.error.URLError,
                    TimeoutError,
                    ConnectionError,
                    OSError,
                ) as exc:
                    if i == attempts - 1:
                        raise
                    wait_s = 10 * (i + 1)
                    print(
                        f"[bridge] LLM call failed ({exc!r}); retry "
                        f"{i + 1}/{attempts - 1} in {wait_s}s"
                    )
                    time.sleep(wait_s)
        return call

    if style == "anthropic":
        return retrying(
            lambda system, messages, with_tools: anthropic_call(
                config,
                api_key,
                system,
                messages,
                tools=AGENT_TOOLS if with_tools else None,
            )
        )

    def openai_fn(system, messages, with_tools):
        text = openai_chat(
            config, api_key, system, messages[-1]["content"], []
        )
        return {"content": [{"type": "text", "text": text}]}

    return openai_fn


# --- Tool dispatch to the in-game runtime -------------------------------


def tool_command(name, args, tag):
    """Map a tool call to the bridge command line + optional payload.
    Fields are joined with ';' — GreyScript's split() is regex-based, so the
    delimiter must have no regex meaning. The tag is always the LAST field;
    the in-game runtime echoes it in its completion marker so a stale 'done'
    from an earlier round can never satisfy this round's wait."""
    args = args or {}
    # the bridge command line is ';'-separated, so a ';' inside an argument
    # that rides it (paths, launch args) would corrupt it. File CONTENT is
    # exempt: it travels separately in payload.txt and the game runtime
    # writes it verbatim.
    for key, value in args.items():
        if key == "content":
            continue
        if isinstance(value, str) and ";" in value:
            raise ValueError(
                f"argument '{key}' must not contain ';' — pass plain paths "
                "and plain argument strings, this is a structured tool "
                "call, not a shell command line"
            )
    if name == "list_dir":
        return f"list;{args.get('path', '/')};{tag}", None
    if name == "read_file":
        return f"read;{args['path']};;{tag}", None
    if name == "write_file":
        return f"write;{args['path']};;{tag}", args.get("content", "")
    if name == "append_file":
        return f"append;{args['path']};;{tag}", args.get("content", "")
    if name == "make_dir":
        return f"mkdir;{args['path']};;{tag}", None
    if name == "delete_file":
        return f"rm;{args['path']};;{tag}", None
    if name == "run_program":
        return f"run;{args['path']};{args.get('args', '')};{tag}", None
    if name == "compile_program":
        return f"build;{args['source_path']};{args['binary_folder']};{tag}", None
    if name == "sysinfo":
        return f"sysinfo;;;{tag}", None
    raise ValueError(f"unknown tool '{name}'")


def dispatch_tool(config, transport, name, args, tag):
    """Send one tool command to the in-game runtime, wait for the result.
    The runtime echoes the tag in 'done <tag>' / 'error <tag>' — only the
    completion matching this round's tag counts. Returns (ok, output)."""
    if name == "api_doc":
        # daemon-side lookup, no in-game round-trip needed
        return api_doc_lookup((args or {}).get("query", ""))
    if name == "load_skill":
        # daemon-side playbook load, no in-game round-trip
        return load_skill((args or {}).get("name", ""))
    if name == "ask_user":
        # daemon-side: turn-ending blocker question, no in-game round-trip
        q = (args or {}).get("question", "").strip()
        log(f"ask_user: {q[:200]}")
        return True, (
            "Question delivered: \"" + q + "\"\n"
            "STOP all work now — do NOT call any more tools this turn. Your "
            "final message must be this question plus exactly what the user "
            "should do (e.g. buy/install the missing library in game, or "
            "provide the missing detail) and tell them to answer in the "
            "chat. plan.txt and notes.txt are saved; the mission continues "
            "automatically when the user replies."
        )
    line, payload = tool_command(name, args, tag)
    path = str(args.get("path", ""))
    is_program = path.endswith(".src") or path.startswith("/bin/")
    if name == "write_file" and is_program:
        syntax_error = validate_greyscript(payload or "")
        if syntax_error:
            return (
                False,
                "GreyScript syntax error — file NOT written. Fix and retry: "
                + syntax_error,
            )

    raw_status = (transport.read("status.txt") or "").strip()
    nonce = raw_status.split(" ", 1)[1] if " " in raw_status else ""
    pairs = [
        ("command.txt", line),
        ("cmdflag.txt", f"pending {nonce}".strip()),
    ]
    if payload is not None:
        pairs.append(("payload.txt", payload))
    transport.write_many(pairs)

    deadline = time.time() + config["tool_timeout"]
    while time.time() < deadline:
        status = (transport.read("command_status.txt") or "").strip()
        if status == f"done {tag}":
            transport.write("cmdflag.txt", "idle")
            result = (transport.read("command_result.txt") or "")[:8000]
            if result.startswith("unknown op"):
                return False, (
                    f"{result} — the in-game agent runtime is OUTDATED and "
                    "does not support this tool. Tell the user to re-paste "
                    "the current game/agent.src into /bin/agent, then retry. "
                    "Do NOT try to work around this by launching files."
                )
            return True, result
        if status == f"error {tag}":
            transport.write("cmdflag.txt", "idle")
            return False, (transport.read("command_result.txt") or "")[:8000]
        time.sleep(config["poll_interval"])
    return (
        False,
        "error: the in-game runtime did not execute the command. Is "
        "agent still running in the game terminal?",
    )


# --- Agent loop ---------------------------------------------------------


MISSION_STATE_FILES = ("plan.txt", "notes.txt")


def mission_state(transport):
    """Load the agent's persistent plan/notes from the bridge folder so they
    survive across rounds without relying on the model's context recall."""
    try:
        plan = (transport.read("plan.txt") or "").strip()
        notes = (transport.read("notes.txt") or "").strip()
    except Exception as exc:  # transport hiccup must never kill a round
        print(f"[bridge] mission_state read failed: {exc}")
        return ""
    if not plan and not notes:
        return ""
    parts = [
        "## Mission state (auto-loaded every round — keep these current "
        "with write_file/append_file)"
    ]
    parts.append(
        "### plan.txt (task list — mark steps [x] as you complete them)\n"
        + (plan or "(empty — write your plan here before acting)")
    )
    if notes:
        parts.append(
            "### notes.txt (facts learned: IPs, ports, services, versions, "
            "credentials, vulnerabilities)\n" + notes
        )
    return "\n\n".join(parts)


def agent_loop(config, transport, llm_fn, system_prompt, prompt, history):
    """Run the harness until the model stops calling tools.

    Rounds are unlimited by default (max_tool_rounds = 0); runaway missions
    are caught by loop detection instead of a hard budget:
    - the same (tool, arguments) call 3 times -> served the cached result
      plus a warning (identical calls cannot produce new information)
    - the 4th identical call, or 12 consecutive failed tool results ->
      the loop is closed out with one final no-tools summary
    """
    messages = list(history) + [{"role": "user", "content": prompt}]
    final = ""
    max_rounds = int(config["max_tool_rounds"] or 0)  # 0 = unlimited
    round_no = 0
    call_counts = {}
    last_results = {}
    fail_streak = 0
    call_seq = []

    def loop_handoff(reason):
        # one last no-tools turn so the player gets a usable summary
        # instead of a dead end
        messages.append(
            {
                "role": "user",
                "content": (
                    "SYSTEM: " + reason + " You may NOT call any more "
                    "tools. Reply now with your final answer: what you "
                    "achieved, the current state (plan/notes are saved), "
                    "and exactly what the user should do next."
                ),
            }
        )
        try:
            data = llm_fn(system_prompt, messages, with_tools=False)
            text = extract_text(data.get("content", [])).strip()
            return f"{reason}\n{text}" if text else reason
        except Exception as exc:
            print(f"[bridge] loop handoff LLM call failed: {exc}")
            return reason

    while True:
        round_no += 1
        if max_rounds and round_no > max_rounds:
            final = loop_handoff(
                f"(stopped after {max_rounds} tool rounds — set "
                "max_tool_rounds to 0 in config.json for unlimited)"
            )
            break
        system_this = system_prompt
        state = mission_state(transport)
        if state:
            system_this = system_prompt + "\n\n---\n\n" + state
        data = llm_fn(system_this, messages, with_tools=True)
        blocks = data.get("content", [])
        messages.append({"role": "assistant", "content": blocks})
        tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
        interim = extract_text(blocks).strip()
        if interim:
            log(f"thinking: {interim[:160]}")
        if not tool_uses:
            final = interim
            if not final:
                stop = data.get("stop_reason", "?")
                kinds = [b.get("type") for b in blocks]
                final = (
                    f"(the model returned no text — stop_reason: {stop}, "
                    f"blocks: {kinds}. If stop_reason is max_tokens, the "
                    "thinking budget consumed the limit; raise max_tokens "
                    "in config.json)"
                )
            break
        results = []
        abort_reason = None
        for call_index, call in enumerate(tool_uses):
            name = call.get("name", "?")
            args = call.get("input", {})
            key = (name, json.dumps(args, sort_keys=True))
            call_counts[key] = call_counts.get(key, 0) + 1
            call_seq.append(key)
            tag = f"{round_no}-{call_index}"
            print(
                f"[bridge] tool call {round_no}: {name}"
                f"({json.dumps(args)[:120]})"
            )
            if call_counts[key] >= 4:
                abort_reason = (
                    f"(mission stopped: loop detected — `{name}` was "
                    f"called with identical arguments "
                    f"{call_counts[key]} times)"
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": "LOOP ABORT: identical call repeated "
                        f"{call_counts[key]} times. Not executed. Wrap up.",
                        "is_error": True,
                    }
                )
                break
            if call_counts[key] == 3:
                ok_prev, out_prev = last_results.get(
                    key, (False, "(no cached result)")
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": (
                            "LOOP WARNING: this exact call has already run "
                            f"{call_counts[key] - 1} times — re-running it "
                            "identically cannot produce new information. "
                            f"Previous result ({'ok' if ok_prev else 'error'}"
                            f"): {out_prev[:3000]}\n"
                            "Change the approach, fix the underlying cause "
                            "first, or use ask_user. A further identical "
                            "repeat will abort the mission."
                        ),
                        "is_error": True,
                    }
                )
                continue
            if (
                len(call_seq) >= 12
                and call_seq[-6:] == call_seq[-12:-6]
            ):
                # the last 6 calls exactly repeat the 6 before them —
                # an A-B-A-B cycle; block this step and teach
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": (
                            "LOOP WARNING: your recent tool calls are "
                            "cycling through the same steps without "
                            "progress. Break the cycle: re-read your "
                            "plan.txt, change one thing materially, or "
                            "use ask_user."
                        ),
                        "is_error": True,
                    }
                )
                continue
            try:
                ok, output = dispatch_tool(config, transport, name, args, tag)
            except (KeyError, ValueError) as exc:
                ok, output = False, f"error: {exc}"
            last_results[key] = (ok, output)
            fail_streak = fail_streak + 1 if not ok else 0
            print(
                f"[bridge] tool result "
                f"{'ok' if ok else 'FAILED'}: {output[:120]!r}"
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": output,
                    "is_error": not ok,
                }
            )
        messages.append({"role": "user", "content": results})
        if abort_reason:
            final = loop_handoff(abort_reason)
            break
        if fail_streak >= 12:
            final = loop_handoff(
                "(mission stopped: 12 consecutive tool failures — the "
                "situation is not improving; the user should look at the "
                "errors above)"
            )
            break
    return final


# --- Request handling ---------------------------------------------------


def handle_request(config, transport, prompt, mode, mock):
    if prompt == "PING" and mode == "chat":
        return "PONG — bridge is alive. Now give the agent a task."

    system_prompt = build_system_prompt()
    history = load_history()[-config["max_history"] :]

    if mock:
        llm_fn = mock_llm_factory(mode)
    else:
        api_key = resolve_api_key(config)
        if not api_key:
            raise RuntimeError(
                f"no API key — paste your GLM key into {API_KEY_FILE}"
            )
        if mode == "agent" and config["api_style"].lower() != "anthropic":
            raise RuntimeError(
                "agent mode needs api_style 'anthropic' in config.json"
            )
        llm_fn = make_llm_fn(config, api_key)

    if mode == "agent":
        reply = agent_loop(
            config, transport, llm_fn, system_prompt, prompt, history
        )
    else:
        data = llm_fn(
            system_prompt,
            history + [{"role": "user", "content": prompt}],
            with_tools=False,
        )
        reply = extract_text(data.get("content", []))

    new_history = history + [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": reply},
    ]
    save_history(new_history)
    return sanitize_reply(reply)


def run_cycle(config, transport, mock):
    """Process one busy request if present. Returns True if one was handled."""
    status = transport.read("status.txt")
    if status is None or not status.strip().startswith("busy"):
        return False

    # debounce: the game flushes each in-game write to the DB separately, so
    # status can land before prompt/mode — re-read after a beat
    time.sleep(max(0.5, config["poll_interval"]))
    if not (transport.read("status.txt") or "").strip().startswith("busy"):
        return False

    raw_status = (transport.read("status.txt") or "").strip()
    nonce = raw_status.split(" ", 1)[1] if " " in raw_status else ""
    if (transport.read("done.txt") or "").strip() == f"done {nonce}":
        # already answered this exact request — status is game-owned and
        # never cleared, so without this guard the daemon replays it forever
        return False
    prompt = (transport.read("prompt.txt") or "").strip()
    mode = (transport.read("mode.txt") or "chat").strip()
    if not prompt:
        # empty prompt means the tree/rows are mid-transition — clear the
        # flag rather than sending an empty request to the API
        print("[bridge] busy flag with empty prompt — resetting")
        transport.write("done.txt", "")
        return False
    log(f"request ({mode}): {prompt[:120]!r}")
    try:
        reply = handle_request(config, transport, prompt, mode, mock)
        transport.write_many(
            [("response.txt", reply), ("done.txt", f"done {nonce}")]
        )
        log(f"replied ({len(reply)} chars)")
    except urllib.error.HTTPError as exc:
        msg = error_message(exc)
        hint = {
            401: " — check your API key",
            403: " — this key may not cover that endpoint/plan",
            404: f" — unknown model '{config['model']}'? check config.json",
        }.get(exc.code, "")
        msg = f"error: API {msg}{hint}"
        transport.write_many(
            [("response.txt", msg), ("done.txt", f"done {nonce}")]
        )
        print(f"[bridge] {msg}")
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None) or exc
        msg = (
            f"error: cannot reach {config['base_url']} ({reason}). "
            "Check your internet connection."
        )
        transport.write_many(
            [("response.txt", msg), ("done.txt", f"done {nonce}")]
        )
        print(f"[bridge] {msg}")
    except Exception as exc:  # noqa: BLE001 - surfaced to the in-game client
        transport.write_many(
            [("response.txt", f"error: {exc}"), ("done.txt", f"done {nonce}")]
        )
        print(f"[bridge] error: {exc}")
    return True


def watch(config, mock):
    if mock:
        print("[bridge] watch mode with MOCK llm (no real API calls)")
    transport = make_transport(config)
    if isinstance(transport, SQLiteTransport):
        backup = transport.backup()
        print(f"[bridge] database backed up to {backup}")
    try:
        transport.read("status.txt")
    except Exception as exc:  # noqa: BLE001 - config problem
        die(f"cannot read bridge files: {exc}")
    if isinstance(transport, HookTransport):
        try:
            runtime = transport._call({"op": "read", "path": "/bin/agent"})
            body = runtime.get("content") or ""
            missing = [
                op for op in ('op == "build"', "nextNonce")
                if op not in body
            ]
            if missing:
                print(
                    "[bridge] WARNING: /bin/agent in game is OUTDATED "
                    f"(missing: {missing}). Re-paste the current "
                    "game/agent.src into /bin/agent — tool calls will fail "
                    "with 'unknown op' until then."
                )
        except Exception:  # noqa: BLE001 - advisory only
            pass
    print(
        "[bridge] watching game save. In game: agent <task>  |  "
        "llm <question>  (Ctrl+C to stop)"
    )
    try:
        while True:
            run_cycle(config, transport, mock)
            time.sleep(config["poll_interval"])
    except KeyboardInterrupt:
        print("\n[bridge] stopped")


# --- Mock LLM (for tests without a key or the game) ---------------------


def mock_llm_factory(mode):
    """Returns an llm_fn with a scripted agent episode for --mock runs."""
    if mode != "agent":
        def chat_fn(system, messages, with_tools):
            return {"content": [{"type": "text", "text": MOCK_CHAT_REPLY}]}

        return chat_fn

    episodes = [
        (
            "Let me see what's on the machine.",
            [
                {
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "sysinfo",
                    "input": {},
                }
            ],
        ),
        (
            "I'll write the greeting tool.",
            [
                {
                    "type": "tool_use",
                    "id": "call_2",
                    "name": "write_file",
                    "input": {
                        "path": "/home/guest/greet.src",
                        "content": "// greet.src — say hi\n"
                        "main = function(params)\n\tprint(\"hello\")\n"
                        "\treturn null\nend function\n\nmain(params)\n",
                    },
                }
            ],
        ),
        (
            "Now run it.",
            [
                {
                    "type": "tool_use",
                    "id": "call_3",
                    "name": "run_program",
                    "input": {"path": "/home/guest/greet.src"},
                }
            ],
        ),
    ]

    state = {"round": 0}

    def agent_fn(system, messages, with_tools):
        if state["round"] < len(episodes):
            text, calls = episodes[state["round"]]
            state["round"] += 1
            return {"content": [{"type": "text", "text": text}, *calls]}
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Built and ran the greeting tool.\n\n```\n// "
                    "greet.src — final version is on your machine\n```\n\n"
                    "(mock agent episode finished)",
                }
            ]
        }

    return agent_fn


# --- Subcommands --------------------------------------------------------


def call_llm_simple(config, system_prompt, prompt):
    api_key = resolve_api_key(config)
    if config["api_style"].lower() == "anthropic":
        data = anthropic_call(
            config,
            api_key,
            system_prompt,
            [{"role": "user", "content": prompt}],
        )
        return extract_text(data.get("content", []))
    return openai_chat(config, api_key, system_prompt, prompt, [])


def cmd_check(config):
    print(f"checking {config['base_url']} ({config['api_style']} protocol) ...")
    if not resolve_api_key(config):
        die(
            "no API key found. Get one from the Z.ai console (your GLM Coding "
            "Plan page), then paste it into daemon/api_key.txt"
        )
    started = time.time()
    try:
        reply = call_llm_simple(
            config, "You are a ping responder.", "Reply with exactly: OK"
        )
    except urllib.error.HTTPError as exc:
        die(f"API rejected the test call: {error_message(exc)}")
    except urllib.error.URLError as exc:
        die(
            f"cannot reach {config['base_url']} "
            f"({getattr(exc, 'reason', exc)})"
        )
    latency = time.time() - started
    print(f"model {config['model']} answered: {reply.strip()[:40]!r} "
          f"in {latency:.1f}s")

    mode = (config.get("transport") or "hook").lower()
    if mode == "hook":
        try:
            transport = make_transport(config)
            status = transport.read("status.txt")
            print(
                "bridge (hook): "
                + ("reachable" if status is not None else "no bridge files — run `agent -t` in game")
            )
        except Exception as exc:  # noqa: BLE001
            print(f"bridge (hook): NOT reachable — {exc}")
    else:
        bridge_ready = bool(config.get("db_path"))
        print(f"bridge (sqlite): {'configured' if bridge_ready else 'NOT configured — run --db-map'}")


def cmd_heal(config):
    """Repair the bridge inside GreyHackDB.db.

    Two operations:
    1. Restore known protocol values in their canonical rows (rows whose
       ID is md5(value) must contain exactly that value).
    2. Repoint any bridge file whose current row is hash-corrupted (or
       shared) at a fresh, distinct, consistent row. Game-owned files are
       NEVER written in place — that is what corrupts them.
    The game must be restarted afterwards so its in-memory filesystem
    picks up the repaired tree.
    """
    import hashlib

    transport = make_transport(config)
    if isinstance(transport, SQLiteTransport):
        transport.backup()
        db_path = transport.db_path
    else:
        die("--heal is for the SQLite transport")

    protocol_values = [
        "", "busy", "done", "chat", "agent", "PING",
        "idle", "pending", "error",
    ]
    repaired = []
    conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for value in protocol_values:
            vid = hashlib.md5(value.encode("utf-8")).hexdigest()
            row = conn.execute(
                "SELECT Content FROM Files WHERE ID = ?", (vid,)
            ).fetchone()
            if row and row[0] != value:
                conn.execute(
                    "UPDATE Files SET Content = ? WHERE ID = ?",
                    (value, vid),
                )
                repaired.append(
                    f"canonical md5({value!r}) row restored "
                    f"(held {row[0][:30]!r})"
                )
        # repoint every bridge file at a fresh distinct consistent row
        fs = json.loads(
            conn.execute(
                "SELECT FileSystem FROM Computer WHERE IsPlayer = 1"
            ).fetchone()[0]
        )
        _, node = find_bridge_folder(fs)
        if node:
            for index, child in enumerate(node.get("files", [])):
                filler = f"greyllm-repair-{index}"
                fid = hashlib.md5(filler.encode("utf-8")).hexdigest()
                conn.execute(
                    "INSERT INTO Files (ID, Content, refCount) "
                    "VALUES (?, ?, 1) "
                    "ON CONFLICT(ID) DO UPDATE SET Content = ?",
                    (fid, filler, filler),
                )
                child["ID"] = fid
            conn.execute(
                "UPDATE Computer SET FileSystem = ?",
                (json.dumps(fs),),
            )
            repaired.append(
                f"all {len(node.get('files', []))} bridge files repointed "
                "at fresh consistent rows"
            )
        conn.execute("COMMIT")
    finally:
        conn.close()
    for line in repaired:
        print("  " + line)
    print("repair complete — RESTART Grey Hack so the game reloads the "
          "repaired filesystem, then run: agent -t")


def cmd_db_map(config, db_path=None):
    db_path = db_path or config.get("db_path") or DEFAULT_DB_PATH
    if not Path(db_path).exists():
        die(
            f"database not found at {db_path}. Pass the path to "
            "GreyHackDB.db explicitly: python bridge.py --db-map "
            "--db-path \"C:\\path\\to\\GreyHackDB.db\""
        )
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        computers = conn.execute(
            "SELECT rowid, FileSystem FROM Computer WHERE IsPlayer = 1"
        ).fetchall()
        if not computers:
            computers = conn.execute(
                "SELECT rowid, FileSystem FROM Computer"
            ).fetchall()
        if not computers:
            die("no computers found in the database")
        if len(computers) > 1:
            print(f"note: {len(computers)} computers found, using the first")

        fs = json.loads(computers[0][1])
        bridge_dir_path, node = find_bridge_folder(fs)
        file_ids = {}
        if node:
            for child in node.get("files", []):
                file_ids[child["nombre"]] = child["ID"]
        if not bridge_dir_path:
            die(
                "no /home/<you>/.greyllm folder found in the game database. Run "
                "`agent -t` in the game first (it creates the bridge "
                "files), then re-run --db-map"
            )

        missing = [n for n in BRIDGE_FILES if n not in file_ids]
        for name in list(file_ids):
            row = conn.execute(
                "SELECT Content FROM Files WHERE ID = ?", (file_ids[name],)
            ).fetchone()
            if row is None:
                missing.append(name + " (no Files row)")

        config["db_path"] = str(db_path)
        config["db_file_ids"] = file_ids
        save_config(config)
        print(f"bridge folder: {bridge_dir_path}")
        for name in sorted(file_ids):
            print(f"  {name} -> {file_ids[name]}")
        if missing:
            print(
                f"note: {', '.join(sorted(set(missing)))} not present yet — "
                "they are created the first time they are needed"
            )
        print("wrote db_path + db_file_ids into config.json")
        print("next: python bridge.py --check   then: python bridge.py")
    finally:
        conn.close()


def cmd_demo(config, mock, agent, use_sqlite):
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config = dict(config)
        config["tool_timeout"] = 10

        fake_fs = tmp / "fs"
        (fake_fs / "home" / "guest").mkdir(parents=True)
        (fake_fs / "bin").mkdir()
        for tool in ("nmap", "sshcrack", "bankhack"):
            (fake_fs / "bin" / tool).write_text("stub", encoding="utf-8")

        if use_sqlite:
            # build a scratch database that behaves like the game's:
            # content-addressed Files rows + a FileSystem tree that repoints
            # on every game-side write
            import hashlib

            db_path = tmp / "scratch.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE Files (ID TEXT PRIMARY KEY, Content TEXT,"
                " refCount INTEGER)"
            )
            conn.execute(
                "CREATE TABLE Computer (FileSystem TEXT, IsPlayer INTEGER)"
            )
            empty_id = hashlib.md5(b"").hexdigest()
            fillers = {
                "response.txt": "r0", "done.txt": "d0", "command.txt": "c0",
                "payload.txt": "p0", "cmdflag.txt": "f0",
                "command_status.txt": "t0", "command_result.txt": "u0",
            }
            conn.executemany(
                "INSERT OR IGNORE INTO Files VALUES (?, ?, 1)",
                [
                    (hashlib.md5(v.encode()).hexdigest(), v)
                    for v in fillers.values()
                ],
            )
            bridge_files = [
                {
                    "nombre": name,
                    "ID": hashlib.md5(
                        fillers.get(name, "").encode()
                    ).hexdigest()
                    if name in fillers
                    else empty_id,
                }
                for name in BRIDGE_FILES
            ]
            fs = {
                "computerID": "demo",
                "files": [],
                "folders": [
                    {
                        "nombre": "home",
                        "files": [],
                        "folders": [
                            {
                                "nombre": "guest",
                                "files": [],
                                "folders": [
                                    {
                                        "nombre": ".greyllm",
                                        "files": bridge_files,
                                        "folders": [],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
            conn.execute(
                "INSERT INTO Files VALUES (?, ?, ?)", (empty_id, "", 9)
            )
            conn.execute(
                "INSERT INTO Computer VALUES (?, 1)", (json.dumps(fs),)
            )
            conn.commit()
            conn.close()
            transport = SQLiteTransport(db_path)
            runtime = FakeInGameRuntime(transport, fake_fs, db_path=db_path)
            print(
                "[demo] SQLiteTransport on a game-like scratch database "
                "(content-addressed rows, tree repointing)"
            )
        else:
            transport = FileTransport(tmp / "bridge")
            runtime = FakeInGameRuntime(transport, fake_fs)
            print("[demo] using FileTransport on scratch files")

        mode = "agent" if agent else "chat"
        # the game side writes via repointing (as agent would in-game)
        runtime.bridge_write("mode.txt", mode)
        runtime.bridge_write("prompt.txt", "build a program that says hello")
        runtime.bridge_write("status.txt", "busy 410928")
        if agent:
            runtime.start()
        print(f"[demo] simulated game side ({mode} mode); processing...")
        try:
            if not run_cycle(config, transport, mock):
                die("demo failed: status never read as busy")
        finally:
            runtime.stop.set()
            if runtime.is_alive():
                runtime.join(timeout=2)
        status = transport.read("done.txt")
        print(f"[demo] done signal: {status.strip()}")
        print("[demo] response:")
        print(transport.read("response.txt"))


class FakeInGameRuntime(threading.Thread):
    """Stands in for game/agent: executes bridge commands against a fake
    in-game filesystem in a temp dir. /home/<x> maps to <root>/home/<x>."""

    def __init__(self, transport, root, db_path=None):
        super().__init__(daemon=True)
        self.transport = transport
        self.root = Path(root)
        self.db_path = db_path
        self.stop = threading.Event()

    def bridge_write(self, name, content):
        """Write a bridge file the way the GAME does: new content-addressed
        row + FileSystem tree repoint. Falls back to the transport for the
        plain-file demo."""
        if not self.db_path:
            self.transport.write(name, content)
            return
        import hashlib

        new_id = hashlib.md5(content.encode("utf-8")).hexdigest()
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO Files (ID, Content, refCount) VALUES (?, ?, 1) "
                "ON CONFLICT(ID) DO UPDATE SET Content = excluded.Content",
                (new_id, content),
            )
            fs = json.loads(
                conn.execute("SELECT FileSystem FROM Computer").fetchone()[0]
            )
            _, node = find_bridge_folder(fs)
            if node:
                for child in node.get("files", []):
                    if child.get("nombre") == name:
                        child["ID"] = new_id
            conn.execute(
                "UPDATE Computer SET FileSystem = ?", (json.dumps(fs),)
            )
            conn.execute("COMMIT")
        finally:
            conn.close()

    def map(self, path):
        if not path or path == "sysinfo":
            return self.root
        rel = path.strip("/").replace("/", os.sep)
        return self.root / rel

    def execute(self, line):
        parts = line.split(";")
        op = parts[0]
        tag = parts[-1] if parts else "0"
        try:
            if op == "sysinfo":
                bins = ", ".join(
                    p.name for p in (self.root / "bin").iterdir()
                ) if (self.root / "bin").exists() else "none"
                return True, f"OS: fakeGREY 1.0\n/bin: {bins}\n"
            if op == "list":
                target = self.map(parts[1])
                if not target.is_dir():
                    return False, f"no such directory: {parts[1]}"
                rows = []
                for entry in sorted(target.iterdir()):
                    kind = "DIR " if entry.is_dir() else "FILE"
                    size = (
                        f"{entry.stat().st_size}"
                        if entry.is_file()
                        else "-"
                    )
                    rows.append(f"{kind} {size} {entry.name}")
                return True, "\n".join(rows) or "(empty)"
            if op == "read":
                target = self.map(parts[1])
                if not target.is_file():
                    return False, f"no such file: {parts[1]}"
                return True, target.read_text(encoding="utf-8")
            if op in ("write", "append"):
                target = self.map(parts[1])
                payload = self.transport.read("payload.txt") or ""
                if op == "write" or not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(payload, encoding="utf-8")
                else:
                    with target.open("a", encoding="utf-8") as fh:
                        fh.write(payload)
                return True, f"wrote {len(payload)} chars to {parts[1]}"
            if op == "mkdir":
                self.map(parts[1]).mkdir(parents=True, exist_ok=True)
                return True, parts[1]
            if op == "rm":
                target = self.map(parts[1])
                if target.exists():
                    target.unlink()
                    return True, parts[1]
                return False, f"no such file: {parts[1]}"
            if op == "run":
                target = self.map(parts[1])
                if not target.is_file():
                    return False, f"no such program: {parts[1]}"
                return True, f"exit: 0\n(simulated run of {parts[1]})"
            return False, f"unknown op {op}"
        except Exception as exc:  # noqa: BLE001 - reported to the model
            return False, f"error: {exc}"

    def run(self):
        while not self.stop.is_set():
            flag = (self.transport.read("cmdflag.txt") or "").strip()
            if flag.startswith("pending"):
                line = (self.transport.read("command.txt") or "").strip()
                ok, output = self.execute(line)
                self.bridge_write("command_result.txt", output)
                self.bridge_write(
                    "command_status.txt",
                    ("done " if ok else "error ") + tag,
                )
            time.sleep(0.1)


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(description="GreyLLM bridge daemon")
    parser.add_argument("--mock", action="store_true", help="fake LLM replies")
    parser.add_argument(
        "--agent", action="store_true",
        help="with --demo: exercise the agent harness loop"
    )
    parser.add_argument(
        "--sqlite", action="store_true",
        help="with --demo: use the SQLite transport on a scratch database"
    )
    parser.add_argument(
        "--check", action="store_true", help="check API + bridge setup"
    )
    parser.add_argument(
        "--db-map", action="store_true",
        help="map bridge files inside GreyHackDB.db into config.json"
    )
    parser.add_argument(
        "--heal", action="store_true",
        help="repair bridge rows whose content no longer matches its hash"
    )
    parser.add_argument(
        "--db-path", metavar="PATH",
        help="path to GreyHackDB.db for --db-map"
    )
    parser.add_argument(
        "--demo", action="store_true", help="one-shot self test (no game)"
    )
    args = parser.parse_args()

    config = load_config()
    if args.db_map:
        cmd_db_map(config, args.db_path)
    elif args.heal:
        cmd_heal(config)
    elif args.check:
        cmd_check(config)
    elif args.demo:
        cmd_demo(config, args.mock, args.agent, args.sqlite)
    else:
        watch(config, args.mock)


if __name__ == "__main__":
    main()
