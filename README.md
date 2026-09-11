# GreyLLM

An AI agent that lives inside Grey Hack (singleplayer) — a Claude-Code-style
harness where the model's shell is your in-game computer. It inspects your
machine, writes GreyScript tools, compiles them, runs them, reads the
results, and iterates until they work. Round trips are ~2–10 seconds.

```
in-game terminal                     your real PC
──────────────                       ─────────────────────────────────────
agent "build a port scanner          .\bridge.cmd  (watch daemon)
      and test it"                       │      └── GLM API  api.z.ai
        │  writes /home/<you>/.greyllm/*  │           (tool calling)
        │  (live in-memory files)         │
        │  ──── GreyLLMHook TCP ────▶     │ reads prompt, calls model
        │      (127.0.0.1:7788)           │ model: "write tool.src"
        │ ◀── writes command/response ────│
[tool executes in your terminal]         │ model: "compile_program"
        │  ...rounds in seconds...        │ model: "run_program"
        ◀──  final answer printed
```

## Components

| Path | What it is |
|---|---|
| `GreyLLMHook/` | BepInEx plugin (C# source) — the real-time bridge into the running game |
| `game/agent.src` | In-game harness runtime: submits tasks, executes the model's tool commands |
| `game/llm.src` | Lightweight one-shot chat client for quick questions |
| `daemon/bridge.py` | Watch daemon: agent loop, GLM API calls, tool dispatch |
| `daemon/config.json.example` | Copy to `daemon/config.json` and fill in your API key |
| `daemon/prompt_pack/` | System prompt + GreyScript reference fed to the model |
| `tools/check-syntax.mjs` | GreyScript syntax validator (real parser) |
| `tools/full-loop-test.mjs` | Full-loop test: real game scripts in a game-faithful interpreter |
| `tools/test-game-scripts.sh` | Integration tests for every game-script invocation |
| `tools/hook-client.py` | Manual client for the plugin's TCP API |
| `tools/watch-bridge.py` | Live bridge observer (SQLite transport debugging) |

## Setup

### 1. Prerequisites

- Grey Hack (Steam), played in **singleplayer**
- Python 3.12+
- Node.js 18+ (for the syntax validator)
- A GLM API key (coding plan keys work — Anthropic-compatible endpoint)

### 2. This repo

```
git clone <this repo>
cd GreyLLM
npm install
copy daemon\config.json.example daemon\config.json
notepad daemon\config.json     # paste your API key into "api_key"
```

### 3. Install the game plugin (one time)

BepInEx 5 + the GreyLLMHook plugin go into the game folder:

```
<GameDir> = C:\Program Files (x86)\Steam\steamapps\common\Grey Hack
```

1. Download [BepInEx 5.4.23.2 x64](https://github.com/BepInEx/BepInEx/releases/tag/v5.4.23.2)
   and extract it into `<GameDir>` (adds `BepInEx\`, `winhttp.dll`, etc.).
2. Build the plugin (or use a prebuilt `GreyLLMHook.dll`):
   ```
   cd GreyLLMHook
   dotnet build -c Release
   copy bin\Release\GreyLLMHook.dll "<GameDir>\BepInEx\plugins\"
   ```
3. Launch the game via Steam. The BepInEx console/log should show
   `GreyLLM Hook loaded — listening on 127.0.0.1:7788`.

### 4. Install the in-game programs (one time)

In the game's **Code Editor**, save the contents of `game/agent.src` as
`/bin/agent` and `game/llm.src` as `/bin/llm` (extensionless files in
`/bin`, which is on the game's PATH). Then in a terminal:

```
agent -t
```

This creates the bridge folder `/home/<you>/.greyllm/` with the bridge
files and sends a PING.

## Running

With the game running (singleplayer, logged in) and `agent -t` done once:

```
.\bridge.cmd          # leave this running — it's the daemon
```

In the game terminal:

```
llm whats the difference between lan_scan and wireless_scan
agent look at my machine and tell me what you see
agent build me a port scanner, compile it, and test it
agent -s scanner      # save the last finished program's source to home
```

The daemon window logs every request and tool call with timestamps.

## The model's tools

`sysinfo`, `list_dir`, `read_file`, `write_file`, `append_file`,
`make_dir`, `delete_file`, `compile_program` (source → runnable binary),
`run_program` (launches binaries, waits ~10s and returns whatever the
program appended to the bridge `out.txt`), and `api_doc` (searches a
complete generated GreyScript API reference — 316 entries from the game's
own metadata — so the model never has to guess an API).

The agent runs a mission doctrine: it writes a plan to the bridge
`plan.txt`, records every learned fact (IPs, ports, credentials,
vulnerabilities) in `notes.txt`, and both are re-injected into its context
every round — persistent memory across a whole task. Give it goals, not
instructions: "root the bank", "map the local network", "build and test a
port scanner". Up to 40 tool rounds per mission.

Every `.src` the model writes is syntax-checked with the real GreyScript
parser before it reaches the game.

## Commands & tests

```
.\bridge.cmd --check            # API key + bridge sanity
.\bridge.cmd --demo --mock --agent --sqlite   # full loop, no game needed
.\bridge.cmd --heal             # repair bridge rows (sqlite transport)
npm run check                   # validate the game scripts
bash tools/test-game-scripts.sh # integration tests (mock game env)
node tools/full-loop-test.mjs   # full-loop harness (real GreyScript)
python tools/hook-client.py health  # poke the plugin manually
```

## Troubleshooting

- **"cannot talk to the GreyLLM hook"** — the game isn't running, or the
  plugin didn't load (check `BepInEx/LogOutput.log` for `GreyLLM Hook`).
- **"no player session"** — log into a singleplayer world and interact once.
- **"bridge folder not found"** — run `agent -t` in game once.
- **Every prompt returns the same reply** — stale state; restart the daemon,
  or run `.\bridge.cmd --heal` (sqlite transport).
- **Model writes code that fails to run** — it knows the compile workflow;
  check it compiled (`compile_program`) before `run_program`.
- **Slow (about a minute per hop)** — you're on the sqlite fallback
  (`"transport": "sqlite"` in config); switch to `"hook"` (requires the
  plugin and the game running).

## Privacy & safety

- The plugin binds to `127.0.0.1` only and refuses to operate outside
  singleplayer.
- Prompts go to your configured API provider — same as any coding
  assistant. Don't paste in-game passwords you care about.
- `daemon/config.json` and `daemon/api_key.txt` hold secrets and are
  gitignored — never commit them.

## Known limitations

- `rnd()` in Grey Hack is deterministic; the bridge uses counter-based
  nonces (see `game/agent.src`).
- Scripts can only `launch` compiled binaries; raw `.src` cannot be
  launched — the model compiles first.
- Multiplayer is unsupported by design.
