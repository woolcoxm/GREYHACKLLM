# Skill: worm — epidemic bank-detail harvesting

Load for: missions like "steal bank details from everything", "spread
across the network", mass credential harvesting. The standard worm
(`~/worm.src`, daemon-managed like ~/exploit.src) does the whole cycle.

## Distributed execution (v17)

The player's machine must NOT do the epidemic's compute — every
processor death traced to exactly that. Now: when the exploit tool
holds a shell foothold, it DELEGATES the next generation — drops
worm+exploit sources on the victim, builds them there, and launches
`worm -child` ON the victim (depth-limited tree, default 3). The
victim's CPU attacks the next hosts, harvests, and writes loot to its
/tmp; when the synchronous launch returns, the parent pulls the loot
home and surfaces NEWTARGETs. CPU wear lands on the infected, where it
belongs. `-depth=` tunes the tree depth.

## The worm's cycle (per host)

The worm is the FRONTIER DRIVER — it never touches victims itself.
For each host it launches `~/exploit <ip> -u=... -w=... -g=<rootpass>
-E=<exfil> -o=<wreport> -winners=<wins> -depth=<n>`, and the exploit
runs the ASSAULT LADDER in-process while its foothold objects are
alive:

1. **Entry**: full-fire EVERY vulnerability on EVERY open port — never
   stop at the first foothold; collect all shells/computer objects and
   rank them by access (root-class > user > guest, probed by what they
   can read). Quiet `-q` mode starved the worm to zero entries once —
   never default it.
2. **Kernel**: when no root-class foothold emerged, fire port 0 too.
3. **Crack + become**: /etc/passwd readable → decipher every hash,
   connect_service as the strongest cracked account where ssh exists
   (there is NO su in this game — a network login is the only identity
   switch); re-harvest when that upgrades access.
4. **Harvest**: every readable `*bank*`/`*mail*`/`*wallet*` file in
   every `/home/*` plus the passwd table — appended to the exfil file
   right through the foothold (default `~/Desktop/bankintel.txt`).
5. **Escalate**: lacking root-class, scp THIS compiled binary +
   metaxploit.so to the victim (never build there — guests cannot) and
   run `exploit -L` on it — local /lib attacks for root.
6. **Delegation**: with depth > 0, scp the compiled worm + exploit to
   the victim and launch `worm -child -depth-1` there — the infected
   machine attacks the NEXT generation. Loot bucket-brigades home:
   each parent pulls its child's exfil file up after the synchronous
   launch returns.
7. **Stealth**: dropped artifacts deleted, victim `/var/system.log`
   wiped (best-effort — root-owned). State saved after EVERY host.

Per-host firing is budget-capped (default 120s, `-budget=`) so one
stubborn box cannot stall the frontier. WINNER lines (known-good
exploit pairs per library version) accumulate in `~/worm.wins` and
fire first on every host running the same version. The worm writes a
per-host digest to `~/Desktop/wormreport.txt` — best privilege
reached, files harvested, accounts cracked, new targets. Hosts are
DONE forever once worked (no re-attacks, operator directive).

## Driving the epidemic

```
compile_program ~/worm.src -> ~/worm        # once
~/worm <seed-ip> -auto                      # LAUNCH ONCE
```
The default run is INFINITE: infect -> harvest -> scan -> infect,
breadth-first, until killed — random public IPs keep the frontier
alive when networks are picked clean. `-auto` also installs the worm
into the PLAYER's /etc/init.d (autorun, verified in game source): the
epidemic auto-resumes at every game login. Kill with the terminal
close / process kill; state (`~/worm.state`) resumes on next launch.
Multiple terminals with different `-s=` state files = parallel
epidemics (GreyScript has no threads — instances are the parallelism).
`-fanout=N` automates it: splits the frontier across N shard state
files and prints the N launch commands to paste into N terminals;
`-install-workers=N` additionally installs N compiled launchers into
/etc/init.d so every login auto-starts N parallel workers;
`-merge` unions the shards back into ~/worm.state.
Flags: `-g=` cap cycles (0=infinite), `-t=` hosts/cycle, `-r=` random
IPs/cycle, `-depth=` infection-tree depth, `-o=` exfil, `-u/-w` creds,
`-rp=` root password.

IMPORTANT for the harness: an infinite worm blocks the serve loop
forever. When launching via run_program, ALWAYS pass a bounded -g=
(e.g. -g=3) and re-invoke for more; reserve raw infinite runs for a
terminal the player opens directly (or -auto autorun at login).

## CPU WEAR — the hard lesson

The game DEGRADES hardware under sustained process load: a processor
was lost to an unbounded run. Per operator directive the worm is now
IMMORTAL (no runtime cap, no idle shutdown — only 5s pacing and the
ping gate restrain it): run it on hardware you can afford to lose,
never your home box. The AGENT must still launch it bounded
(run_program ~/worm <ip> -g=3) — an unbounded run blocks the serve
loop forever.

## Constraints (verified)

- Binary files (metaxploit.so) move between machines ONLY via
  `shell.scp`; `get_content` refuses binaries. Sources move as text +
  compile locally (`shell.build`).
- Victims without metaxploit (and where scp fails) are harvested but
  cannot escalate or scan — the worm moves on.
- `rnd()` is deterministic; the worm mixes `time()` for per-run address
  variety.
- Every host is one pass — machines that get cleaned by admins simply
  drop out; reruns re-seed from the frontier.
