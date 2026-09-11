# GreyLLM — an AI agent that lives inside Grey Hack

GreyLLM turns your **Grey Hack singleplayer** world into the workspace of a
real coding agent. You give it goals — *"build and test a port scanner"*,
*"root the machine at 192.168.1.1"* — and it works autonomously on your
in-game computer: it inspects the machine, writes GreyScript programs,
compiles them, runs them, reads the results, remembers what it learned, and
iterates until the goal is actually met. If it hits a blocker only you can
fix (missing software, missing facts), it stops and asks you, then resumes
with full context when you answer.

It works like Claude Code / pi / opencode — except the "computer" the agent
operates is the simulated one inside the game, and the "terminal" is your
in-game terminal. Round trips are ~2–10 seconds per tool call.

```
in-game terminal                     your real PC
──────────────                       ─────────────────────────────────────
agent            ← interactive chat  .\bridge.cmd   (watch daemon)
you> root 192.168.1.1                    │
        │ writes /home/<you>/.greyllm/*  │      GLM API  api.z.ai
        │ (live bridge files)            │      (Anthropic-compatible,
        │ ──── GreyLLMHook TCP ─────▶    │       tool calling)
        │      (127.0.0.1:7788)          │
        │ ◀── tool commands ─────────────│  model: "list_dir /lib"
[tool executes in your terminal]         │  model: "write_file pscan.src"
        │ ...rounds in seconds...        │  model: "compile_program"
        ◀── reply: "rooted. proof: ..."  │  model: "run_program"
```

Three pieces make this work, and each has to be installed once:

| Piece | Where it lives | What it does |
|---|---|---|
| **GreyLLMHook** (BepInEx plugin) | Inside the game folder | Real-time bridge: exposes the game's live filesystem over loopback TCP so the daemon can read/write files in milliseconds instead of scraping the save DB |
| **In-game program** (`agent`) | On your in-game machine | Interactive chat + one-shot missions: submits requests, executes the model's tool commands, streams its thoughts, prints replies |
| **Watch daemon** (`bridge.py`) | On your PC | The agent harness: talks to the model (GLM), dispatches its tool calls into the game, injects prompts/memory, guards the protocol |

---

## Requirements

- **Grey Hack** (Steam), played in **singleplayer** (multiplayer is
  unsupported by design — the plugin refuses to operate there).
- **Windows** (the plugin and paths are Windows-oriented; the daemon itself
  is plain Python and runs anywhere).
- **Python 3.12+** — runs the daemon.
- **Node.js 18+** — used by the GreyScript syntax validator and tests
  (`npm install` pulls the real GreyScript parser).
- **A GLM API key** — e.g. from a Z.ai international coding plan. The daemon
  talks to the Anthropic-compatible endpoint `https://api.z.ai/api/anthropic`
  with tool calling. Any Anthropic-protocol provider works if you change
  `base_url`/`model` in the config.

---

## Installation

Do these three parts in order. Part 1 and 2 happen once; part 3 once per PC.

### Part 1 — Install the game plugin (one time)

The plugin needs BepInEx 5, the standard Unity mod loader.

1. Find your game folder. On Steam it defaults to:
   ```
   C:\Program Files (x86)\Steam\steamapps\common\Grey Hack
   ```
   (In Steam: right-click Grey Hack → Manage → Browse local files.)

2. Download **BepInEx 5.4.23.2 x64** from
   <https://github.com/BepInEx/BepInEx/releases/tag/v5.4.23.2> and extract
   the zip **into the game folder** (so you get `Grey Hack\BepInEx\`,
   `Grey Hack\winhttp.dll`, etc.).

3. Build the plugin (or drop in a prebuilt `GreyLLMHook.dll` if you have
   one):
   ```
   cd GreyLLMHook
   dotnet build -c Release
   copy bin\Release\GreyLLMHook.dll "..\<GameDir>\BepInEx\plugins\"
   ```
   (Requires the .NET SDK with .NET Framework 4.7.2 targeting pack. The
   repo has the C# source — `Plugin.cs`, `HookServer.cs`, `Ops.cs`,
   `Patches.cs` — so you can read exactly what it does before trusting it.)

4. Launch the game through Steam. Open
   `<GameDir>\BepInEx\LogOutput.log` and confirm the line:
   ```
   GreyLLM Hook loaded — listening on 127.0.0.1:7788
   ```

**What/why:** the plugin is what makes the system *fast*. It binds to
`127.0.0.1:7788` (loopback only — nothing leaves your machine through it)
and answers tiny JSON requests like "read `/home/you/.greyllm/prompt.txt`"
or "write this file" against the game's **live in-memory world**, with the
proper file locks and DB sync. Without it, the daemon falls back to reading
and writing the save database directly (the `sqlite` transport) — it works,
but each hop takes ~a minute because it can only see what the game has
flushed to disk.

### Part 2 — Install the in-game programs (one time, and after updates)

The two game programs are plain GreyScript source files in this repo:

| Repo file | Save in game as | Purpose |
|---|---|---|
| `game/agent.src` | `/bin/agent` | The harness: interactive chat + one-shot missions + tool execution |

To install them:

1. Launch your singleplayer world and open a terminal.
2. Open the in-game **Code Editor** (from the desktop).
3. Create a new file, paste the entire contents of `game/agent.src` from
   this repo into it, and save it as `/bin/agent` (extensionless).
   - If `/bin` is not writable in your world, save them into your home
     folder instead (`/home/<you>/agent`) — the game terminal searches the
     current directory first, so they still run by name from `~`.
4. In the terminal, run the bridge self-test:
   ```
   agent -t
   ```
   This creates the **bridge folder** `/home/<you>/.greyllm/` with the
   protocol files, prints where they live, and sends a PING through the
   whole chain.

**When do you need to redo this?** Almost never. The in-game runtime
carries `AGENT_VERSION`, and the daemon re-installs `/bin/agent` through
the hook automatically at startup (and after each mission) whenever the
repo ships a newer version — no pasting. This first paste is only needed
because a fresh world has no runtime yet.

### Part 3 — Set up the daemon (one time per PC)

```
git clone https://github.com/woolcoxm/GREYHACKLLM.git
cd GREYHACKLLM
npm install
copy daemon\config.json.example daemon\config.json
notepad daemon\config.json
```

In `daemon/config.json`, set at minimum:

```json
{
  "transport": "hook",
  "api_style": "anthropic",
  "base_url": "https://api.z.ai/api/anthropic",
  "model": "glm-5.3",
  "api_key": "<YOUR GLM API KEY>",
  "max_tokens": 16384
}
```

`config.json` is **gitignored** — your key never gets committed. You can
also put the key in `daemon/api_key.txt` or the `ZAI_API_KEY` environment
variable instead.

Check everything at once:

```
.\bridge.cmd --check
```

**Why a daemon at all?** The game's GreyScript interpreter is sandboxed:
no network, no HTTP, no way to reach an LLM API from inside the game. The
daemon is the outside half of the bridge — it watches the bridge folder for
new requests, runs the agent loop (model ↔ tools), and writes replies back
through the plugin.

---

## Running it

### Start order

1. Launch Grey Hack and load your singleplayer world (the plugin loads
   automatically; the daemon will complain "no player session" until you've
   logged in and interacted once).
2. On your PC, start the daemon and leave the window open:
   ```
   .\bridge.cmd
   ```
   It prints `[bridge] watching game save...` and logs every request,
   tool call, and reply with timestamps.
3. In a game terminal, talk to the agent (below).

Order between 1 and 2 doesn't matter — the daemon waits patiently until
the game side is ready.

### The interactive harness session (recommended)

Run `agent` with **no arguments**:

```
you@greyhack:~$ agent
[agent] interactive session. full tool access; I keep
[agent] plan.txt/notes.txt across messages. 'exit' to quit.
you> build me a port scanner, compile it, and test it
[agent] tool: sysinfo
[agent] tool: write /home/you/pscan.src
[agent] tool: build /home/you/pscan.src
[agent] tool: run /home/you/pscan
192.168.1.3 : 22  ssh 1.0.3
192.168.1.1 : 80  http 1.0.1
192.168.1.1 : 141 bank_account 1.0.1
...
Scanner built at /home/you/pscan. Full results above and in notes.
you> now find exploits on the machine at 192.168.1.1
...
you> exit
```

This is the main way to use GreyLLM. Each message continues the same
conversation: the daemon keeps chat history, the agent keeps its
`plan.txt`/`notes.txt`, and each message gets a fresh **unlimited**
tool-round budget — loops are caught by detection, not a limit. Type
`exit` (or `quit`) to close the session.

### One-shot missions

Same thing without the chat loop — send a task and get one answer:

```
agent "map the local network and list every open port"
agent "root the machine at 192.168.1.1"
agent -s pscan        # afterwards: save the last code block to ~/pscan
```

### Plain chat (no tools)

### All in-game commands

| Command | What it does |
|---|---|
| `agent` | Interactive harness session (tools, memory, missions) |
| `agent <task...>` | One-shot mission |
| `agent -t` | Bridge self-test: creates bridge files, sends a PING |
| `agent -w` | Re-attach to the current task's tool loop (if you closed the terminal) |
| `agent -r` | Print the last reply again |
| `agent -s <name>` | Save the last code block from a reply to `~/<name>` |
| `/new` (any terminal, even mid-mission) | Cancel the active mission and clear ALL context — history, plan, notes — for a fresh engagement |

### A note on missions and what to give the agent

Give it **goals, not step lists** — it plans itself. Two things to know:

- Targets need addresses. "Root the bank" alone has nothing to act on
  unless the bank's IP is already in its notes — include the IP, or tell it
  to find one on your network first.
- It stops and asks (`ask_user`) when something only you can fix is
  missing — e.g. the metaxploit library isn't installed and apt can't get
  it. Fix it in game (buy it from a software shop, install it), then just
  tell the agent "done" — it will verify and resume.

---

## How a mission works (the loop)

When you send a message, this cycle runs until the model stops calling
tools, a loop is detected, or it produces its final answer:

1. The daemon builds the system prompt: the mission doctrine, the
   GreyScript reference essentials, the full conversation history, and —
   this is the memory — the current contents of `plan.txt` and `notes.txt`
   from the bridge folder.
2. The model (GLM) thinks and either answers or emits tool calls.
3. Each tool call goes to the game: the daemon writes a command line into
   the bridge folder; the in-game `agent` serve loop picks it up, executes
   it on the in-game computer (list a folder, write a file, compile,
   launch...), and writes the result back. Daemon-side tools (`api_doc`,
   `ask_user`) answer instantly without touching the game.
4. Results feed back to the model; loop continues.
5. The final answer is written to the bridge and printed in your game
   terminal.

The **mission doctrine** (in `daemon/prompt_pack/system.md`) makes it
behave like a real harness: orient → plan (`plan.txt`) → act → **verify**
(every return value checked, every file read back) → record
(`notes.txt`) → iterate *until the goal is verifiably met* — "it compiled"
doesn't count. `run_program` waits ~10s and collects program output from
the bridge `out.txt`, so the model actually sees what its code did.

### The model's tools

| Tool | Runs where | What it does |
|---|---|---|
| `sysinfo` | game | Installed programs (/bin), home path, bridge dir |
| `list_dir` | game | List a directory |
| `read_file` / `write_file` / `append_file` | game | File I/O; `.src` writes are syntax-checked first |
| `make_dir` / `delete_file` | game | Filesystem management |
| `compile_program` | game | Source → runnable binary (`get_shell.build`) |
| `run_program` | game | Launch a binary, wait, collect its output from `out.txt` |
| `api_doc` | daemon | Search the complete GreyScript API reference (below) |
| `load_skill` | daemon | Load a mission playbook (see below) |
| `ask_user` | daemon | Blocker question: stop work, ask you, resume on reply |

**Mission skills** (`daemon/prompt_pack/skills/`) are focused playbooks the
agent loads on demand via `load_skill(name)` — the system prompt carries
only the index:

| Skill | Covers |
|---|---|
| `recon` | Profiling targets: network/port/service scans, deep
  fingerprinting, harvesting people's data for social engineering |
| `post-exploit` | Foothold → root: interpreting `overflow` results,
  cracking `/etc/passwd` hashes with the crypto lib, password-reset
  exploits, kernel attacks, persistence, proof of root |
| `opsec` | Covering tracks: how logging/tracing actually works
  (`/var/system.log`), clearing logs, attacking through hop machines
  (bounces), and the end-of-mission cleanup checklist (uploaded files,
  created users, rshells, restored system files) |
| `bank-heist` | Bank accounts and crypto wallets: password reuse,
  scripted phishing via the mail API, wallet file theft, cashing out |

The doctrine makes opsec mandatory: any mission touching someone else's
machine ends with log clearing and artifact cleanup.

**`api_doc`** searches a **complete API reference generated from the
game's own metadata** (316 entries — every type, method, signature, return
value, and official usage example; see `tools/build-reference.mjs`). The
verified essentials live in the system prompt; everything else is one
lookup away. This is why the agent doesn't guess API names (the #1 cause
of `Undefined Identifier` / `Key Not Found` runtime errors).

**Every `.src` the model writes is syntax-checked** with the real
GreyScript parser before it ever reaches the game — compile errors are
caught and fed back without wasting an in-game round trip.

---

## Configuration reference (`daemon/config.json`)

| Key | Default | Meaning |
|---|---|---|
| `transport` | `"hook"` | `"hook"` = live plugin (fast); `"sqlite"` = direct save-DB access (slow fallback, works without plugin) |
| `hook_port` | `7788` | Port the plugin listens on (must match plugin config) |
| `api_style` | `"anthropic"` | Protocol for the LLM; agent mode requires anthropic |
| `base_url` | z.ai endpoint | Any Anthropic-compatible endpoint |
| `model` | `"glm-5.3"` | Model name |
| `api_key` | — | Your key (or `daemon/api_key.txt` / `ZAI_API_KEY` env) |
| `thinking_budget` | `6000` | Per-round thinking token cap; smaller = faster rounds, `0` = unbounded (can take minutes per round) |
| `max_tokens` | `16384` | Output budget per round; thinking models need headroom |
| `max_tool_rounds` | `0` | Tool rounds per message; `0` = unlimited (default) — loop detection is the safety net |
| `tool_timeout` | `120` | Seconds to wait for the in-game runtime before failing a tool |
| `max_history` | `6` | Conversation exchanges kept across requests |
| `poll_interval` | `0.5` | Bridge poll cadence (seconds) |

---

## Updating

| What changed in repo | What you do |
|---|---|
| `daemon/*` or `daemon/prompt_pack/*` | Restart `bridge.cmd`. Prompts and reference load fresh on every request |
| `game/agent.src` | Nothing — the daemon auto-installs it into `/bin/agent` (check `daemon.log` for "installed game runtime") |
| `GreyLLMHook/*` | Rebuild + copy the DLL, restart the game |

Regenerate the API reference appendix after a Grey Hack update:
```
npm install            # refresh greyscript-meta if needed
node tools/build-reference.mjs
```

---

## Commands & tests

```
.\bridge.cmd --check            # API key + bridge sanity
.\bridge.cmd --demo --mock --agent --sqlite   # full loop, no game needed
.\bridge.cmd --heal             # repair bridge rows (sqlite transport)
npm run check                   # syntax-validate the game scripts
bash tools/test-game-scripts.sh # integration tests (mock game env)
node tools/full-loop-test.mjs   # full-loop harness (real GreyScript)
python tools/hook-client.py health  # poke the plugin manually
```

---

## Troubleshooting

- **"cannot talk to the GreyLLM hook"** — the game isn't running, or the
  plugin didn't load (check `BepInEx/LogOutput.log` for `GreyLLM Hook`).
- **"no player session"** — log into a singleplayer world and interact
  with something once.
- **"bridge folder not found"** — run `agent -t` in game once.
- **`agent` with no args shows usage** — your in-game `agent` is an old
  version; re-paste the current `game/agent.src`.
- **Tool errors say `unknown op`** — same fix: the in-game runtime predates
  that tool; re-paste `game/agent.src`.
- **"the in-game runtime did not execute the command"** — the terminal that
  started the task is closed/dead. Re-open a terminal and run `agent -w`,
  or resend the message.
- **Every prompt returns the same reply** — stale bridge state; restart the
  daemon, or run `.\bridge.cmd --heal` (sqlite transport).
- **Slow (~a minute per hop)** — you're on the sqlite fallback; switch
  `"transport": "hook"` in config (requires plugin + game running).
- **Model returns `(1 chars)` or empty** — thinking model consumed the
  token budget; raise `max_tokens` (16384 recommended).

---

## Privacy & safety

- The plugin binds to `127.0.0.1` **only** and refuses to operate outside
  singleplayer.
- Prompts go to your configured API provider — same as any coding
  assistant. Don't paste in-game passwords you care about.
- `daemon/config.json`, `daemon/api_key.txt`, and `daemon/history.json`
  hold secrets/chat logs and are gitignored — never commit them.

---

## Known limitations

- Grey Hack's `rnd()` is deterministic; the bridge uses counter-based
  nonces (see `game/agent.src`) so requests never collide.
- Scripts can only `launch` compiled binaries — raw `.src` can't run; the
  model compiles first (`compile_program`).
- Launched programs' terminal output is not directly capturable — tools
  append results to the bridge `out.txt`, which `run_program` collects.
- One mission at a time: the bridge folder is a single request/response
  channel.
- Multiplayer is unsupported by design.

---

## Repository layout

```
GreyLLMHook/        BepInEx plugin C# source (the game-side bridge)
game/agent.src      in-game harness runtime (paste as /bin/agent)
daemon/bridge.py    the watch daemon: agent loop, tools, LLM calls
daemon/prompt_pack/ system.md (mission doctrine) + greyscript_reference.md
                    (verified essentials + generated complete API appendix)
                    + skills/ (opsec, recon, post-exploit, bank-heist playbooks)
daemon/config.json.example
tools/              validator, tests, API-reference generator, debug clients
bridge.cmd          Windows launcher for the daemon
```
