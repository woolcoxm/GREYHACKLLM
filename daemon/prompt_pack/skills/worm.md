# Skill: worm — epidemic bank-detail harvesting

Load for: missions like "steal bank details from everything", "spread
across the network", mass credential harvesting. The standard tool is
`~/exploit.src` (daemon-managed) — since v30 it is ONE binary: the
universal exploit AND the epidemic worm. There is no separate worm
anymore (`~/worm` is retired; `-auto` cleans stale /etc/init.d entries).

## One tool, one brain (v32)

Every assault is a REPLANNING loop, not a fixed script — after each
action the planner re-reads world state and picks the next move. THE
GOAL is a launch-capable ROOT SHELL; a root computer object reads
files but cannot launch or spread, so it is a stepping stone, never
the finish line (the v31 "got root and did nothing" bug was exactly
that confusion):

1. ROOT ACCESS of any kind -> immediately secure a durable account +
   harvest (bank/mail/wallet + the passwd table). create_user and
   reading homes both work through a computer object.
2. root SHELL held -> spread children, clean up, done. Firing halts
   forever on that host (SWEEP-STOP).
3. root computer only -> NOT done: keep firing for a shell foothold
   (SWEEP-CONT), crack /etc/passwd (root reads it), log in as root
   over ssh/ftp.
4. root password known -> USE it: connect_service logins on the
   ssh/ftp port (no shell needed); if refused, scp the binary +
   metaxploit.so onto the victim and run `exploit -L -rp=<pw>` THERE —
   `get_shell("root", pw)` validates the password on the box (the
   exact call `sudo -u root` wraps, verified in the game's command
   script). A successful passchange registers its `-g` password as
   the root candidate immediately.
5. user shell -> cat /etc/passwd, crack the root hash, become root.
6. guest shell -> local privesc: the -L relay fires the victim's OWN
   /lib from inside as the guest (guest -> user -> root rung). It
   runs even with NO known password.
7. vulns unfired -> fire (winners first, kernel port 0 last).
8. fired out -> harvest what we can, spread if any shell, clean logs
   best-effort, finish.

The -L relay child that gains root STOPS there (v33 flatten): it
escalates, secures, harvests and reports — spreading is the PARENT's
job through its own shell. Before this flatten, every relay spawned a
synchronous epidemic tree inside the parent's launch call and single
hosts took minutes with no visible progress. Every action emits a
phase heartbeat ([fire] [crack] [usepass] [secure] [harvest]
[spread] [finish]) — any crash names its phase. All dangerous
intrinsics live in a validated SAFE ZONE in the source (enforced by
tools/check-danger-calls.mjs); artifacts are tracked in a ledger and
cleaned by exact path.

WORM RESEARCH APPLIED (the who/what/when/why/how of real worms):
- local-preference scanning (Code Red II) -> victim LAN enumeration
  first, random publics only when starved (children probe 8, not 20)
- hit-lists (Staniford's flash-worm paper) -> worm.wins: proven
  exploit pairs fire FIRST on every host running the same lib version;
  winners relay up the tree via W| loot lines so the whole epidemic
  learns each win
- payload staging (Slammer/Conficker) -> depth-0 children deploy the
  tiny scan stager, not the full assault
- CAMOUFLAGE / oligomorphic naming (1260/Conficker renaming) -> scp
  CANNOT rename (verified in the game's own source: the destination
  must be a folder and the file keeps its own name), so each assault
  REBUILDS itself from source under a randomized system-ish name
  (sysmon372, netd81, svchost9...) — a genuinely fresh build per host,
  never "exploit". Falls back to the plain name if no source is
  available (deployment never breaks for camouflage)
- MEMORY (v34): worm.wins = hit-list (proven exploit pairs fire
  FIRST — the file is now actually loaded back, it previously was
  only written) and worm.duds = skip-list (null results are
  deterministic per library version — known-dead vuln pairs are never
  fired again anywhere in the epidemic). Both relay up the tree
- SUMMARY census at finish of every host: shells=N (root/user/guest),
  computers=N (root), rootShell=yes/no, deployed=<name> — one line
  that cannot lie about what was actually obtained
- persistence (autorun.inf analogue) -> `-persist` (OPT-IN, evidence!)
  copies the child into the VICTIM's /etc/init.d so the infection
  auto-resumes at every game login
- self-defense -> throttling (5s pacing), single-instance lock
  (~/worm.lock, 10-min staleness, -force override) so two epidemics
  never corrupt one state file, ledger cleanup + log wipes + honest
  EVIDENCE-LEFT accounting

## Distributed execution

When the planner holds a shell with depth > 0, it scps THIS binary
(+ metaxploit.so when the victim lacks it, + the source best-effort) to
a writable landing dir and launches `exploit -child -base=<landing>
-depth-1 -cycles=1` ON the victim. The victim's CPU attacks the next
generation; loot and new targets bucket-brigade home when the
synchronous launch returns. `-depth=` tunes the tree (default 3 under
-auto). At depth 0 the child still runs `exploit -scan` to enumerate the
victim's network (F|ip lines relayed up as NEWTARGETs).

## Opsec — cleanup is mandatory, not optional (v31)

Learned the expensive way: traced runs cost the player real money.
Every attack writes entries into the victim's `/var/system.log`, and
only ROOT can erase that file. The tool therefore:

- wipes the victim log the MOMENT root is gained (mid-fire) and again
  at finish — attempted through EVERY foothold, since the finishing
  one may lack the rights;
- deletes EXACTLY the ledger of files it created, also through every
  foothold (no blind sweeps, no missed artifacts);
- keeps ALL child-generation working files (log, digest, winners,
  report, state, loot) inside the landing dir and removes them when
  the bounded child run ends — the parent's ledger deletes them too;
- wipes YOUR OWN `/var/system.log` once per epidemic cycle;
- flags every host where root never landed as **EVIDENCE-LEFT** in the
  report, the worm log, and the digest — that evidence is unremovable,
  so the player sees exactly which hosts still name them.

`-stealth` additionally skips creating the durable account everywhere
(persistence traded for a smaller footprint — the account table entry
is itself evidence that admins eventually clean anyway). Residual
risk that CANNOT be engineered away: hosts attacked without ever
gaining root keep your IP in their log until an admin cleans it. The
EVIDENCE-LEFT digest is the honest accounting of that exposure.

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
