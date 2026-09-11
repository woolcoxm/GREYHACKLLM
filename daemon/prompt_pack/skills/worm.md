# Skill: worm — epidemic bank-detail harvesting

Load for: missions like "steal bank details from everything", "spread
across the network", mass credential harvesting. The standard tool is
`~/exploit.src` (daemon-managed) — since v30 it is ONE binary: the
universal exploit AND the epidemic worm. There is no separate worm
anymore (`~/worm` is retired; `-auto` cleans stale /etc/init.d entries).

## One tool, one brain (v30)

Every assault is a REPLANNING loop, not a fixed script — after each
action the planner re-reads world state and picks the next move:

1. root shell held -> secure a durable account, harvest as root, spread
   children, clean up. Firing halts forever on that host (SWEEP-STOP).
2. root password known -> USE it: connect_service login on ssh/ftp;
   if refused, scp the binary + metaxploit.so onto the victim and run
   `exploit -L -rp=<pw>` THERE — `get_shell("root", pw)` validates the
   password on the box (the exact call `sudo -u root` wraps, verified
   in the game's command script). A successful passchange registers its
   `-g` password as the root candidate immediately.
3. /etc/passwd readable -> crack ONLY the root hash (root owns the box),
   then go to 2.
4. vulns unfired -> fire (winners first, kernel port 0 last).
5. fired out with any shell -> harvest what we can, spread depth-1,
   clean. No shell at all -> clean, verdict NONE.

Every action emits a phase heartbeat ([fire] [crack] [usepass] [secure]
[harvest] [spread] [finish]) — any crash names its phase. All dangerous
intrinsics live in a validated SAFE ZONE in the source (enforced by
tools/check-danger-calls.mjs); artifacts are tracked in a ledger and
cleaned by exact path.

## Distributed execution

When the planner holds a shell with depth > 0, it scps THIS binary
(+ metaxploit.so when the victim lacks it, + the source best-effort) to
a writable landing dir and launches `exploit -child -base=<landing>
-depth-1 -cycles=1` ON the victim. The victim's CPU attacks the next
generation; loot and new targets bucket-brigade home when the
synchronous launch returns. `-depth=` tunes the tree (default 3 under
-auto). At depth 0 the child still runs `exploit -scan` to enumerate the
victim's network (F|ip lines relayed up as NEWTARGETs).

## Driving the epidemic

```
compile_program ~/exploit.src -> ~/exploit   # once
~/exploit <seed-ip> -auto                    # LAUNCH ONCE
~/exploit <ip>                               # single-target assault
```

State (`~/worm.state`, format unchanged from the worm era: F|ip /
O|ip|user|pass / D|ip) resumes across runs; hosts are DONE forever once
worked (no re-attacks, operator directive). `-auto` installs the binary
into the PLAYER's /etc/init.d (autorun, verified in game source) so the
epidemic auto-resumes at every login. Per-host digest lands in
`~/Desktop/wormreport.txt`; WINNER lines (known-good exploit pairs per
library version) accumulate in `~/worm.wins` and fire first everywhere.

Epidemic flags: `-cycles=N` cap (0 = INFINITE; legacy `-g=N` still
accepted), `-t=` hosts/cycle, `-r=` random IPs/cycle when starved,
`-depth=`, `-o=` exfil, `-s=` state file, `-u/-w` durable creds,
`-rp=` root password. `-fanout=N` splits the frontier across N shard
state files and prints the N terminal commands; `-install-workers=N`
also installs N launchers into /etc/init.d; `-merge` unions shards back.

IMPORTANT for the harness: an infinite epidemic blocks the serve loop
forever. When launching via run_program, ALWAYS pass a bounded
`-cycles=` (e.g. -cycles=3) and re-invoke for more; reserve raw
infinite runs for a player-opened terminal (or the -auto autorun).

## CPU WEAR — the hard lesson

The game DEGRADES hardware under sustained load: a processor was lost
to an unbounded run. The epidemic is IMMORTAL by operator directive
(only 5s pacing and the ping gate restrain it): run it on hardware you
can afford to lose. Per-victim assaults run as child PROCESSES — a
crash on one host can never kill the epidemic (no verdict in the report
= host retired as "crashed", never looped).

## Constraints (verified)

- Binary files (metaxploit.so, the tool itself) move between machines
  ONLY via `shell.scp`; `get_content` refuses binaries. Never build on
  victims — guests cannot compile.
- Without the metaxploit library the tool halts the epidemic with a
  FATAL line (buy it in the software shop) instead of burning cycles.
- Victims where scp fails are harvested but cannot escalate or spread —
  the epidemic moves on.
- `rnd()` is deterministic; the tool mixes `time()` for per-run address
  variety.
- Every host is one pass — machines cleaned by admins simply drop out;
  reruns re-seed from the frontier.
